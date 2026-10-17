"""Prepare private, ordered Yoto uploads and actual-size card labels. No network I/O."""
import argparse
import hashlib
import io
import json
import math
import os
import re
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape

# Reuse the ripper's private dependencies on Windows; standalone pip also works.
if os.environ.get('LOCALAPPDATA'):
    sys.path.insert(0, str(Path(os.environ.get('LIBRARY_CD_RIP_HOME',
        str(Path(os.environ['LOCALAPPDATA']) / 'LibraryCDRip'))) / 'vendor'))

MAX_TRACKS = 100
MAX_BYTES = 500_000_000
MAX_SECONDS = 5 * 3600
MAX_TRACK_BYTES = 100_000_000
MAX_TRACK_SECONDS = 3600
ROOT = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def natural_key(value):
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r'(\d+)', str(value))]


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(value)).strip(' .')
    return value[:90].rstrip(' .') or 'Track'


def probe_mp3(path):
    from mutagen import MutagenError
    from mutagen.mp3 import MP3
    try:
        audio = MP3(path)
    except MutagenError as error:
        raise ValueError(f'Invalid MP3: {path}: {error}') from error
    if audio.info.layer != 3:
        raise ValueError(f'Not an MP3 Layer III file: {path}')
    tags = audio.tags or {}
    def tag(key):
        return str(tags.get(key, '')).strip()
    raw_number = tag('TRCK').split('/')[0].strip()
    if raw_number and (not raw_number.isdecimal() or int(raw_number) < 1):
        raise ValueError(f'Invalid track number in {path.name}: {raw_number}')
    return dict(seconds=audio.info.length, title=tag('TIT2') or path.stem,
                album=tag('TALB'), artist=tag('TPE1'),
                track_number=int(raw_number) if raw_number else None)


def load_album(folder, reader=probe_mp3):
    files = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == '.mp3'),
                   key=lambda p: natural_key(p.name)) if folder.is_dir() else []
    if not files:
        raise ValueError(f'No MP3s in album folder: {folder}')
    tracks = []
    for path in files:
        metadata = reader(path)
        seconds, size = metadata['seconds'], path.stat().st_size
        if not math.isfinite(seconds) or seconds <= 0 or seconds > MAX_TRACK_SECONDS:
            raise ValueError(f'Track must be between 0 and 60 minutes: {path}')
        if size <= 0 or size > MAX_TRACK_BYTES:
            raise ValueError(f'Track must be at most 100 MB: {path}')
        tracks.append(dict(metadata, source=str(path), source_name=path.name,
                           bytes=size, sha256=sha256(path)))
    numbers = [t['track_number'] for t in tracks]
    if any(n is not None for n in numbers):
        if None in numbers or len(set(numbers)) != len(numbers):
            raise ValueError(f'Mixed or duplicate track tags in {folder}; correct the tags first')
        tracks.sort(key=lambda t: t['track_number'])
    return tracks


def resolve_path(base, value):
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def validate_contents(rows, count):
    covered = []
    for row in rows:
        first, last = row['first'], row['last']
        if type(first) is not int or type(last) is not int or not 1 <= first <= last <= count:
            raise ValueError('Contents ranges must use valid, inclusive integer track numbers')
        if not isinstance(row['title'], str) or not row['title'].strip():
            raise ValueError('Each contents row needs a title')
        covered.extend(range(first, last + 1))
    if covered != list(range(1, count + 1)):
        raise ValueError('Contents must cover every track once, in order, without gaps or overlaps')


def prepare_cards(plan_path, reader=probe_mp3):
    plan_path = Path(plan_path).resolve()
    plan = read_json(plan_path)
    if not isinstance(plan, dict) or not isinstance(plan.get('cards'), list) or not plan['cards']:
        raise ValueError('Plan needs a nonempty cards list')
    cards = []
    for number, spec in enumerate(plan['cards'], 1):
        if not isinstance(spec.get('title'), str) or not spec['title'].strip():
            raise ValueError(f'Card {number} needs a title')
        if not spec.get('albums'):
            raise ValueError(f'Card {number} needs at least one album folder')
        tracks, ranges = [], []
        for album in spec['albums']:
            folder = resolve_path(plan_path.parent, album['folder'])
            album_tracks = load_album(folder, reader)
            first = len(tracks) + 1
            tracks.extend(album_tracks)
            ranges.append(dict(first=first, last=len(tracks),
                               title=album.get('label') or album_tracks[0]['album'] or folder.name))
        size, seconds = sum(t['bytes'] for t in tracks), sum(t['seconds'] for t in tracks)
        if len(tracks) > MAX_TRACKS or size > MAX_BYTES or seconds > MAX_SECONDS:
            raise ValueError(f'Card {number} exceeds Yoto limits: {len(tracks)} tracks, '
                             f'{size / 1e6:.1f} MB, {seconds / 60:.1f} minutes. Split its albums across cards.')
        for index, track in enumerate(tracks, 1):
            track['file'] = f'card-{number:02d}/{index:03d} {safe_name(track["title"])}.mp3'
        contents = spec.get('contents', ranges)
        validate_contents(contents, len(tracks))
        card = dict(number=number, title=spec['title'], tracks=tracks,
                    ranges=ranges, contents=contents, bytes=size, seconds=seconds)
        if spec.get('cover'):
            cover = resolve_path(plan_path.parent, spec['cover'])
            if not cover.is_file() or cover.suffix.lower() not in ('.jpg', '.jpeg', '.png'):
                raise ValueError(f'Cover must be a JPEG or PNG file: {cover}')
            card['cover'] = dict(source=str(cover), sha256=sha256(cover),
                                 file=f'card-{number:02d}/cover{cover.suffix.lower()}')
        cards.append(card)
    return cards


def labels_pdf(cards):
    import reportlab
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph

    fonts = Path(reportlab.__file__).parent / 'fonts'
    for name, filename in [('CardLabel', 'Vera.ttf'), ('CardLabelBold', 'VeraBd.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    title_style = ParagraphStyle('title', fontName='CardLabelBold', fontSize=10, leading=12)
    body_style = ParagraphStyle('body', fontName='CardLabel', fontSize=8, leading=10)
    width, height = 85.60 * mm, 53.98 * mm
    output = io.BytesIO()
    page = canvas.Canvas(output, pagesize=A4)
    page.setTitle('Yoto card contents - 85.60 x 53.98 mm - print at actual size')
    for index, card in enumerate(cards):
        slot = index % 6
        if slot == 0:
            if index:
                page.showPage()
            page.setFont('CardLabelBold', 15)
            page.drawString(15 * mm, A4[1] - 20 * mm, 'Yoto card contents')
            page.setFont('CardLabel', 9)
            page.drawString(15 * mm, A4[1] - 28 * mm, 'Print A4 at 100% / Actual size. Cut along the outlines.')
            page.drawString(15 * mm, A4[1] - 34 * mm, 'Each outline measures 85.60 x 53.98 mm.')
            page.drawString(15 * mm, 28 * mm, 'Size check: the line below must measure 50 mm.')
            page.line(15 * mm, 22 * mm, 65 * mm, 22 * mm)
            for x in (15 * mm, 65 * mm):
                page.line(x, 21 * mm, x, 23 * mm)
        x = (15 + (slot % 2) * 94) * mm
        y = A4[1] - (99 + (slot // 2) * 65) * mm
        page.setLineWidth(.4)
        page.roundRect(x, y, width, height, 2 * mm)
        inner_width = width - 8 * mm
        top = y + height - 4 * mm
        title = Paragraph(escape(f'{card["number"]}. {card["title"]}'), title_style)
        _, title_height = title.wrap(inner_width, height)
        title.drawOn(page, x + 4 * mm, top - title_height)
        top -= title_height + 12
        page.setFont('CardLabel', 7)
        page.drawString(x + 4 * mm, top, f'{len(card["tracks"])} tracks | {card["seconds"] / 60:.0f} min')
        top -= 8
        for row in card['contents']:
            interval = f'{row["first"]:02d}'
            if row['last'] != row['first']:
                interval += f'-{row["last"]:02d}'
            paragraph = Paragraph(escape(interval + '  ' + row['title']), body_style)
            _, row_height = paragraph.wrap(inner_width, height)
            if top - row_height < y + 4 * mm:
                raise ValueError(f'Contents on card {card["number"]} do not fit. Shorten its title/labels '
                                 'or use fewer contents rows; track audio is unchanged.')
            paragraph.drawOn(page, x + 4 * mm, top - row_height)
            top -= row_height + 2
    page.save()
    return output.getvalue()


def copy_verified(source, target, expected):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha256(target) != expected:
            raise ValueError(f'Existing staged file differs; preserving it: {target}')
        return
    temporary = target.with_suffix(target.suffix + '.part')
    shutil.copy2(source, temporary)
    if sha256(temporary) != expected:
        raise ValueError(f'Copy/source changed while preparing: {source}; partial copy preserved')
    temporary.replace(target)


def build(plan_path, output, reader=probe_mp3):
    output = Path(output).resolve()
    if output.is_relative_to(ROOT):
        raise ValueError('Keep private Yoto plans/output outside the source repository')
    cards = prepare_cards(plan_path, reader)
    for card in cards:
        for track in card['tracks']:
            folder = Path(track['source']).parent
            if output.is_relative_to(folder) or folder.is_relative_to(output):
                raise ValueError('Output must be separate from original album folders')
    # Render first: overflow/dependency errors must not leave a half-built batch.
    pdf = labels_pdf(cards)
    fingerprint = hashlib.sha256(json.dumps(cards, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    state_path = output / 'manifest.json'
    old = read_json(state_path) if state_path.exists() else {}
    if old and old.get('plan_sha256') != fingerprint:
        raise ValueError('This output belongs to a different plan/audio version. Choose a new output folder.')
    if not old and output.exists() and any(output.iterdir()):
        raise ValueError('Output is not empty; choose a new folder to preserve its files')
    output.mkdir(parents=True, exist_ok=True)
    if not old:
        # Claim this output before copying so interrupted runs can resume safely.
        write_json(state_path, dict(schema=1, plan_sha256=fingerprint, prepared=False, cards=[]))
    receipts = {c['number']: c for c in old.get('cards', [])}
    for card in cards:
        for track in card['tracks']:
            copy_verified(track['source'], output / track['file'], track['sha256'])
        if 'cover' in card:
            cover = card['cover']
            copy_verified(cover['source'], output / cover['file'], cover['sha256'])
        prior = receipts.get(card['number'], {})
        for key in ('yoto_url', 'uploaded_order_verified', 'linked_confirmation', 'offline_download_verified'):
            card[key] = prior.get(key, '' if key in ('yoto_url', 'linked_confirmation') else False)
    (output / 'card-labels.pdf').write_bytes(pdf)
    manifest = dict(schema=1, plan_sha256=fingerprint, prepared=True, cards=cards)
    write_json(state_path, manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True, help='Private JSON plan; see examples/yoto-plan.json')
    parser.add_argument('--output', type=Path, required=True, help='Private output folder outside this repository')
    args = parser.parse_args()
    try:
        result = build(args.plan, args.output)
    except (ValueError, OSError, KeyError, TypeError, ImportError) as error:
        parser.exit(1, f'Preparation stopped: {error}\n')
    for card in result['cards']:
        print(f'Card {card["number"]}: {len(card["tracks"])} tracks, '
              f'{card["seconds"] / 60:.1f} min, {card["bytes"] / 1e6:.1f} MB - {card["title"]}')
    print(f'Prepared locally: {args.output.resolve()}\nNo uploads, printing or physical card linking performed.')


if __name__ == '__main__':
    main()
