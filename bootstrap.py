"""Install local dependencies and the exact fre:ac build used by this app."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get('LIBRARY_CD_RIP_HOME', str(Path(os.environ['LOCALAPPDATA'])/'LibraryCDRip')))
FREAC = HOME/'freac/freac-1.1.7-x64/freaccmd.exe'
URL = 'https://github.com/enzo1982/freac/releases/download/v1.1.7/freac-1.1.7-windows-x64.zip'
SHA256 = 'ef45665aae6c1c0eb4c0ecd8ecc6bed24f02f3cddf6cfd72d8e5c9bc858bf110'


def install():
    HOME.mkdir(parents=True, exist_ok=True)
    if not FREAC.exists():
        archive = HOME/'freac.zip'
        previous = Path(os.environ['LOCALAPPDATA'])/'CDHelper/freac.zip'
        if previous.exists() and hashlib.sha256(previous.read_bytes()).hexdigest()==SHA256:
            shutil.copyfile(previous, archive)
        else:
            print('Downloading the verified fre:ac portable ripper…', flush=True)
            urllib.request.urlretrieve(URL, archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=SHA256:
            raise RuntimeError('fre:ac download checksum failed. Delete freac.zip and try again.')
        with zipfile.ZipFile(archive) as package:
            base = (HOME/'freac').resolve()
            if any(not (base/item.filename).resolve().is_relative_to(base) for item in package.infolist()):
                raise RuntimeError('Unsafe archive path')
            package.extractall(base)
    vendor = HOME/'vendor'
    marker = vendor/'library-cd-rip-requirements.txt'
    required = (ROOT/'requirements.txt').read_text()
    if not marker.exists() or marker.read_text()!=required:
        print('Installing the local photo and MP3 readers…', flush=True)
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                        '--upgrade', '--target', str(vendor), '-r', str(ROOT/'requirements.txt')], check=True)
        marker.write_text(required)
    return HOME


if __name__=='__main__':
    install()
