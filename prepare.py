"""Prepare the photo queue from files, optionally with reviewed metadata JSON."""
import argparse
import base64
import json
from pathlib import Path
import sys

from bootstrap import HOME
sys.path.insert(0, str(HOME/'vendor'))
from storage import Library


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('photos', nargs='+', type=Path, help='Front-cover photos, one per CD')
    parser.add_argument('--metadata', type=Path, help='JSON array: photo filename, title, artist, optional titles, back, year')
    parser.add_argument('--language', choices=['en-GB','de-DE'], default='en-GB')
    args=parser.parse_args()
    library=Library(HOME)
    metadata=json.loads(args.metadata.read_text(encoding='utf-8-sig')) if args.metadata else []
    by_name={entry['photo']:entry for entry in metadata}
    albums=[]
    for path in args.photos:
        photo=library.import_photo(path.name,base64.b64encode(path.read_bytes()).decode(),path.stat().st_mtime*1000)
        info=by_name.get(path.name,{})
        album=dict(id=photo['id'],cover=photo['url'],captured=photo['captured'],
                   title=info.get('title',''),artist=info.get('artist',''),titles=info.get('titles',[]),year=info.get('year',''))
        if info.get('back'):
            back=Path(info['back'])
            if not back.is_absolute(): back=args.metadata.parent/back
            album['back']=library.import_photo(back.name,base64.b64encode(back.read_bytes()).decode(),back.stat().st_mtime*1000)['url']
        albums.append(album)
    albums.sort(key=lambda a:a['captured'])
    draft=library.draft()
    if draft['albums']:
        parser.error('There is already a photo draft. Finish or clear it in the app first; it has been preserved.')
    draft.update(albums=albums,language=args.language)
    library.save_draft(draft)
    print(f'{len(albums)} CDs prepared. Open Start Library CD Rip and review the queue.')


if __name__=='__main__': main()
