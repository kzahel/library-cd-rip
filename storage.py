"""Local photo intake and durable, ordered CD batches. No cloud service needed."""
import base64
from datetime import datetime
import io
import json
import os
from pathlib import Path
import re
import uuid

from PIL import Image, ImageOps


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8') as output:
        output.write(json.dumps(value,ensure_ascii=False,indent=2))
        output.flush()
        os.fsync(output.fileno())
    temp.replace(path)


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default


def capture_time(name, exif, modified):
    for tag in (36867, 306):
        value = exif.get(tag)
        if value:
            try:
                return datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S').isoformat()
            except ValueError:
                pass
    # Pixel camera filenames survive chat exports even when EXIF is stripped.
    match = re.search(r'(20\d{6})[_-](\d{6})(\d{3})?', name)
    if match:
        try:
            dt = datetime.strptime(match[1]+match[2], '%Y%m%d%H%M%S')
            return dt.isoformat()+('.'+match[3] if match[3] else '')
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(float(modified)/1000).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        return datetime.now().isoformat()


class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.photos = self.root/'photos'
        self.batches = self.root/'batches'
        self.photos.mkdir(parents=True, exist_ok=True)
        self.batches.mkdir(exist_ok=True)

    def import_photo(self, name, encoded, modified=0):
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError('This photo could not be read.') from exc
        if len(data) > 25*1024*1024:
            raise ValueError('Please use a photo smaller than 25 MB.')
        try:
            with Image.open(io.BytesIO(data)) as original:
                original.getexif()  # Retain the timestamp before rotation strips EXIF.
                captured = capture_time(name, original.getexif(), modified)
                image = ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((1400, 1400))
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ValueError('Use a JPG, PNG or WebP photo. Export HEIC photos as JPG first.') from exc
        identity = uuid.uuid4().hex
        image.save(self.photos/f'{identity}.jpg', quality=88)
        result = dict(id=identity, name=Path(name).name, captured=captured,
                      url=f'/photos/{identity}.jpg')
        write_json(self.photos/f'{identity}.json', result)
        return result

    def draft(self):
        return read_json(self.root/'draft.json', dict(albums=[], language='en-GB'))

    def save_draft(self, draft):
        albums = draft.get('albums', [])
        if not isinstance(albums, list) or len(albums) > 100:
            raise ValueError('A mission can contain up to 100 CDs.')
        clean = []
        for album in albums:
            cover = album.get('cover', '')
            if not re.fullmatch(r'/photos/[a-f0-9]{32}\.jpg', cover) or not (self.root/cover.lstrip('/')).is_file():
                raise ValueError('Every CD needs its front-cover photo.')
            titles = album.get('titles', [])
            if not isinstance(titles, list) or len(titles) > 99:
                raise ValueError('Track names must be a list of up to 99 names.')
            back = album.get('back', '')
            if back and (not re.fullmatch(r'/photos/[a-f0-9]{32}\.jpg', back) or not (self.root/back.lstrip('/')).is_file()):
                raise ValueError('The back-cover photo is missing.')
            clean.append(dict(id=str(album.get('id', uuid.uuid4().hex))[:80],
                              title=str(album.get('title', '')).strip()[:200],
                              artist=str(album.get('artist', '')).strip()[:160],
                              cover=cover, back=back, captured=str(album.get('captured', ''))[:50],
                              titles=[str(t).strip()[:180] for t in titles],
                              year=str(album.get('year', '')).strip()[:4]))
        result = dict(albums=clean, language='de-DE' if draft.get('language')=='de-DE' else 'en-GB',
                      drive=str(draft.get('drive', ''))[:2],
                      drive_index=int(draft.get('drive_index', 0)),
                      music=str(draft.get('music', str(Path.home()/'Music'))))
        write_json(self.root/'draft.json', result)
        return result

    def create_batch(self, draft):
        draft = self.save_draft(draft)
        if not draft['albums'] or any(not a['title'] or not a['artist'] for a in draft['albums']):
            raise ValueError('Check the title and artist for every CD before starting.')
        identity = uuid.uuid4().hex
        folder = self.batches/identity
        folder.mkdir()
        write_json(folder/'queue.json', draft['albums'])
        write_json(folder/'batch.json', dict(id=identity, created=datetime.now().isoformat(),
                                            language=draft['language'], drive=draft['drive'],
                                            drive_index=draft['drive_index'], music=draft['music']))
        self.set_active(identity)
        # Keep the last batch intact; the next mission starts with new photos.
        write_json(self.root/'draft.json', dict(albums=[], language=draft['language'],
                                               drive=draft['drive'], music=draft['music']))
        return identity

    def set_active(self, identity):
        write_json(self.root/'active.json', dict(id=identity))

    def active(self):
        identity = read_json(self.root/'active.json', {}).get('id', '')
        return self.batch(identity) if identity else None

    def batch(self, identity):
        if not re.fullmatch(r'[a-f0-9]{32}', identity):
            raise ValueError('Invalid mission.')
        folder = self.batches/identity
        batch = read_json(folder/'batch.json', None)
        if batch is None:
            raise ValueError('Mission not found.')
        records = []
        if (folder/'history.jsonl').exists():
            for line in (folder/'history.jsonl').read_text(encoding='utf-8').splitlines():
                try: records.append(json.loads(line))
                except ValueError: continue
        batch['albums'] = read_json(folder/'queue.json', [])
        batch['completed'] = len(records)
        saved={r.get('signature') for r in records}
        for album in batch['albums']:
            album['saved']=bool(album.get('signature') and album['signature'] in saved)
        batch['finished'] = bool(batch['albums']) and all(
            a.get('signature') in {r.get('signature') for r in records} for a in batch['albums'])
        return batch

    def list_batches(self):
        batches = [self.batch(p.name) for p in self.batches.iterdir() if p.is_dir() and re.fullmatch(r'[a-f0-9]{32}', p.name)]
        return sorted(batches, key=lambda b: b['created'], reverse=True)
