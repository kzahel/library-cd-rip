"""Drive discovery and reversible AutoPlay suppression during a mission."""
import ctypes
import json
import re
import subprocess
import winreg

from storage import write_json, read_json


def drives(exe):
    optical = [f'{chr(letter)}:' for letter in range(65, 91)
               if ctypes.windll.kernel32.GetDriveTypeW(f'{chr(letter)}:\\')==5]
    result = subprocess.run([str(exe), '--list-drives'], capture_output=True,
                            text=True, errors='replace', timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    entries = []
    for line in result.stdout.splitlines():
        match = re.match(r'\s*(\d+)\s+(\S+)\s+(.+)', line)
        if match:
            entries.append(dict(index=int(match[1]), device=match[2], name=match[3].strip()))
    return dict(letters=optical, encoders=entries)


class AutoPlayGuard:
    # This prevents Explorer and WMP from opening over the child screen.
    SETTINGS = [
        (r'Software\Microsoft\Windows\CurrentVersion\Explorer\AutoplayHandlers', 'DisableAutoplay', lambda old: 1),
        (r'Software\Microsoft\Windows\CurrentVersion\Policies\Explorer', 'NoDriveTypeAutoRun', lambda old: (old if isinstance(old,int) else 0x91)|0x20),
        (r'Software\Microsoft\MediaPlayer\Preferences', 'AutoEjectCD', lambda old: 0),
        (r'Software\Microsoft\MediaPlayer\Preferences', 'AutoCopyCDWin7', lambda old: 0),
    ]

    def __init__(self, root):
        self.path = root/'autoplay-restore.json'

    def restore(self):
        saved = read_json(self.path, [])
        for record in reversed(saved):
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, record['path']) as key:
                try: current, _ = winreg.QueryValueEx(key, record['name'])
                except FileNotFoundError: current = None
                if current != record['applied']: continue
                if record['exists']:
                    winreg.SetValueEx(key, record['name'], 0, record['type'], record['value'])
                else:
                    try: winreg.DeleteValue(key, record['name'])
                    except FileNotFoundError: pass
        self.path.unlink(missing_ok=True)

    def enable(self):
        self.restore()  # Also repairs an interrupted previous launch.
        saved = []
        try:
            for path, name, transform in self.SETTINGS:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
                    try:
                        old, kind = winreg.QueryValueEx(key, name)
                        exists = True
                    except FileNotFoundError:
                        old, kind, exists = None, winreg.REG_DWORD, False
                    applied = transform(old)
                    saved.append(dict(path=path, name=name, exists=exists, value=old, type=kind, applied=applied))
                    write_json(self.path, saved)  # Journal before changing the setting.
                    winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, applied)
        except OSError:
            self.restore()
            raise RuntimeError('Windows could not pause AutoPlay. Close other CD apps and try again.')
