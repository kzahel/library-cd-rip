"""Observe the physical CD and validate saved MP3 files."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import sys
import time

STATE = Path(os.environ.get('LIBRARY_CD_RIP_HOME', str(Path(os.environ['LOCALAPPDATA'])/'LibraryCDRip')))
sys.path.insert(0, str(STATE/'vendor'))
from mutagen.mp3 import MP3
from mutagen.id3 import TALB, TIT2, TPE1, TPE2, TRCK, TDRC


class Monitor:
    def __init__(self, state_dir, drive, music_root=None):
        self.state_dir, self.drive = state_dir, drive
        self.music_root = Path(music_root) if music_root else Path.home()/'Music'
        self.stop = False
        self.mci = ctypes.WinDLL('winmm').mciSendStringW
        self.mci.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HWND]
        self.mci.restype = wintypes.UINT
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self.kernel.CreateFileW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.opened = False
        self.signature = None
        self.folder = None
        self.done = False
        self.interrupted = False
        self.ready_since = None
        self.last_change = time.time()
        self.baseline_time = time.time()
        self.baseline = None
        self.last_completed = -1
        self.session_start = time.time()
        self.status = dict(phase='connecting',progress=0,completed=0,updated=time.time(),
                           detail='Connecting to the CD drive.')
        self.total = 0
        self.history = state_dir/'history.jsonl'
        self.records = []
        if self.history.exists():
            for line in self.history.read_text(encoding='utf-8').splitlines():
                try: self.records.append(json.loads(line))
                except ValueError: pass
            self.total = len(self.records)

    def query(self, command):
        result = ctypes.create_unicode_buffer(1024)
        code = self.mci(command, result, 1024, None)
        if code:
            raise OSError(f'CD drive status unavailable ({code})')
        return result.value

    def closed(self, path):
        # An exclusive read handle proves the encoder has closed its writer.
        h = self.kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0, None)
        if h == ctypes.c_void_p(-1).value:
            return False
        self.kernel.CloseHandle(h)
        return True

    def publish(self, **values):
        status = dict(phase='reading',progress=0,completed=self.total,drive=self.drive,
                      album='',tracks=0,track=0,eta=None,updated=time.time())
        status.update(values)
        saved_signatures = {r.get('signature') for r in self.records}
        queue = self.queue()
        next_disc = next((c for c in queue if c.get('signature') not in saved_signatures),None)
        if next_disc:
            status.update(next_title=next_disc['title'],next_cover=next_disc.get('cover'),
                          queue_position=queue.index(next_disc)+1,queue_total=len(queue))
        # HTTP reads this immutable snapshot. Diagnostic file locks must never
        # interrupt monitoring or make a completed CD appear to have failed.
        self.status = status
        temp = self.state_dir/'status.tmp'
        try:
            temp.write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')
            temp.replace(self.state_dir/'status.json')
        except OSError:
            pass

    def queue(self):
        try:
            return json.loads((self.state_dir/'queue.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return []

    def config(self):
        try:
            c = json.loads((self.state_dir/'album.json').read_text(encoding='utf-8'))
            if c.get('signature') == self.signature:
                return c
        except (OSError, ValueError):
            pass
        queue = self.queue()
        for c in queue:
            if c.get('signature') == self.signature:
                return c
        # The physical discs are supplied in the user's specified photo order.
        # Persist a TOC binding so a restart or reinsert cannot advance the queue.
        if self.signature and not any(r.get('signature')==self.signature for r in self.records):
            saved={r.get('signature') for r in self.records}
            next_disc=next((c for c in queue if c.get('signature') not in saved),None)
            if next_disc:
                if next_disc.get('signature'):
                    raise ValueError('Please put the unfinished CD back in: '+next_disc['title'])
                next_disc['signature']=self.signature
                path=self.state_dir/'queue.json'
                temp=path.with_suffix('.tmp')
                temp.write_text(json.dumps(queue,ensure_ascii=False,indent=2),encoding='utf-8')
                for attempt in range(10):
                    try:
                        temp.replace(path)
                        return next_disc
                    except PermissionError:
                        if attempt==9: raise
                        time.sleep(.05)
        return {}

    def find_folder(self, lengths):
        music = self.music_root
        candidates = {}
        for f in music.rglob('*.mp3'):
            if f.stat().st_mtime > self.session_start-3600:
                candidates[f.parent] = max(candidates.get(f.parent,0),f.stat().st_mtime)
        for folder in sorted(candidates, key=candidates.get, reverse=True):
            first = next((f for f in folder.glob('*.mp3') if re.match(r'^0?1\D',f.name)),None)
            if first and self.closed(first):
                try:
                    if abs(MP3(first).info.length-lengths[0]) < 2:
                        return folder
                except Exception:
                    pass
        return None

    def label(self, config, files):
        if not config.get('title'):
            return
        for i, f in sorted(files.items()):
            audio = MP3(f)
            if audio.tags is None:
                audio.add_tags()
            audio.tags.add(TALB(encoding=3,text=config['title']))
            audio.tags.add(TPE1(encoding=3,text=config.get('artist','Unknown artist')))
            audio.tags.add(TPE2(encoding=3,text=config.get('artist','Unknown artist')))
            audio.tags.add(TRCK(encoding=3,text=f'{i}/{len(files)}'))
            if config.get('year'):
                audio.tags.add(TDRC(encoding=3,text=str(config['year'])))
            title = config.get('titles',[])
            if len(title) >= i:
                audio.tags.add(TIT2(encoding=3,text=title[i-1]))
            audio.save()
        for i, f in sorted(files.items()):
            titles = config.get('titles',[])
            if len(titles) >= i:
                clean = re.sub(r'[<>:"/\\|?*]', '',titles[i-1]).rstrip('. ')
                dest = f.with_name(f'{i:02d} {clean}.mp3')
                if dest != f and not dest.exists():
                    f.rename(dest)
        def safe(value):
            value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '',value).strip().rstrip('. ')[:140]
            if not value or value in ('.', '..'): value = 'Untitled'
            if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
                value = '_'+value
            return value
        safe_title = safe(config['title'])
        dest = self.music_root/safe(config.get('artist','Unknown artist'))/safe_title
        if dest != self.folder and dest.exists():
            # Keep previous sessions and two different editions of an album.
            number = 2
            while dest.with_name(f'{safe_title} ({number})').exists(): number += 1
            dest = dest.with_name(f'{safe_title} ({number})')
        if dest != self.folder and not dest.exists():
            dest.parent.mkdir(parents=True,exist_ok=True)
            self.folder.rename(dest)
            self.folder = dest

    def tick(self):
        if (self.state_dir/'maintenance').exists():
            self.publish(phase='setup',detail='Getting the new CD ripper ready. Put the CD shown below in for its test, then leave it inside.')
            return
        if not self.opened:
            self.query(f'open {self.drive} type cdaudio alias cdmission shareable')
            self.query('set cdmission time format milliseconds')
            self.opened = True
        present = self.query('status cdmission media present').lower() == 'true'
        if not present:
            if self.signature and not self.done:
                self.interrupted=True
            self.signature=None; self.folder=None; self.done=False; self.ready_since=None
            self.publish(phase='empty',detail='That CD came out before it was saved. Put the same CD shown below back in and close the tray.' if self.interrupted else 'Put a music CD in the drive, shiny side down. Gently close the tray.')
            return
        count = int(self.query('status cdmission number of tracks'))
        if not count:
            self.publish(phase='error',detail='This is not a music CD. Ask a grown-up.')
            return
        lengths = [int(self.query(f'status cdmission length track {i}'))/1000 for i in range(1,count+1)]
        signature = ','.join(str(round(x*1000)) for x in lengths)
        if self.signature != signature:
            self.signature=signature; self.folder=None; self.done=False; self.ready_since=None
            self.interrupted=False
            self.last_change=time.time(); self.baseline=None; self.last_completed=-1
        config = self.config()
        if config.get('titles') and len(config['titles']) != count:
            raise ValueError(f"The photo lists {len(config['titles'])} track names, but this CD has {count} tracks. Pause and correct the names in the saved mission.")
        album = config.get('title', 'Music CD')
        if self.folder is None:
            self.folder = self.find_folder(lengths)
        if self.done:
            self.publish(phase='done',progress=100,album=album,tracks=count,track=count,
                         folder=str(self.folder),detail='All done! Press the drive button, take out this CD, then put in the next one.')
            return
        files={}
        if self.folder:
            for f in self.folder.glob('*.mp3'):
                m=re.match(r'^(\d+)\D',f.name)
                if m:
                    files[int(m[1])]=f
        complete={}
        for i in range(1,count+1):
            f=files.get(i)
            if f and self.closed(f):
                try:
                    audio=MP3(f)
                    if abs(audio.info.length-lengths[i-1]) < 2 and not audio.info.sketchy:
                        complete[i]=f
                except Exception:
                    pass
        seconds=sum(lengths[i-1] for i in complete)
        progress=int(seconds/sum(lengths)*100)
        if len(complete)!=self.last_completed:
            self.last_change=time.time(); self.last_completed=len(complete)
        if self.baseline is None:
            self.baseline=seconds; self.baseline_time=time.time()
        eta=None
        if seconds>self.baseline:
            eta=round((sum(lengths)-seconds)*(time.time()-self.baseline_time)/(seconds-self.baseline))
        if len(complete)==count and self.completion_allowed():
            if self.ready_since is None:
                self.ready_since=time.time()
            if time.time()-self.ready_since >= 4:
                already_saved = any(r.get('signature')==signature for r in self.records)
                if not already_saved:
                    self.label(config,complete)
                    record=dict(date=time.time(),album=album,tracks=count,folder=str(self.folder),signature=signature)
                    with self.history.open('a',encoding='utf-8') as f:
                        f.write(json.dumps(record)+'\n')
                        f.flush()
                        os.fsync(f.fileno())
                    self.records.append(record)
                    self.total+=1
                self.done=True
                return self.tick()
        else:
            self.ready_since=None
        stalled=time.time()-self.last_change>300
        self.publish(phase='error' if stalled else 'ripping',progress=min(99,progress),album=album,
                     tracks=count,track=min(count,len(complete)+1),saved=len(complete),eta=eta,
                     detail='Copying is taking a long time. Leave the CD inside and ask a grown-up.' if stalled else
                     f'Keep the CD inside. {len(complete)} of {count} songs saved.')

    def completion_allowed(self):
        return True

    def run(self):
        try:
            while not self.stop:
                try:
                    self.tick()
                    cmd=self.state_dir/'command.json'
                    if cmd.exists():
                        action=json.loads(cmd.read_text()).get('action')
                        cmd.unlink()
                        if action=='eject' and self.done:
                            self.query('set cdmission door open')
                        elif action=='retry':
                            self.last_change=time.time()
                            self.retry_requested=True
                            self.interrupted=False
                except Exception as exc:
                    self.publish(phase='error',detail='Leave the CD inside and ask a grown-up. '+str(exc))
                    if self.opened:
                        try: self.query('close cdmission')
                        except OSError: pass
                        self.opened=False
                time.sleep(1)
        finally:
            if self.opened:
                self.query('close cdmission')
