"""Photo-first Windows CD ripping app. HTTP is loopback-only; hardware is opt-in."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get('LIBRARY_CD_RIP_HOME', str(Path(os.environ['LOCALAPPDATA'])/'LibraryCDRip')))
sys.path.insert(0, str(HOME/'vendor'))
from storage import Library, write_json, read_json
from freac_monitor import FreacMonitor
from windows import AutoPlayGuard, drives

EXE = HOME/'freac/freac-1.1.7-x64/freaccmd.exe'


def open_browser(url):
    candidates = [Path(os.environ.get('PROGRAMFILES', 'C:/Program Files'))/'Google/Chrome/Application/chrome.exe',
                  Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe']
    browser = next((p for p in candidates if p.exists()), None)
    if browser:
        subprocess.Popen([str(browser), '--new-window', '--start-fullscreen', '--app='+url])
    else:
        import webbrowser
        webbrowser.open(url)


class Application:
    def __init__(self, home):
        self.library = Library(home)
        self.guard = AutoPlayGuard(home)
        self.guard.restore()
        self.monitor = None
        self.watcher = None
        self.lock = threading.RLock()
        self._devices = None

    def devices(self, refresh=False):
        if self._devices is None or refresh:
            self._devices = drives(EXE)
        return self._devices

    def pause(self):
        if self.monitor:
            self.monitor.stop = True
            self.monitor.abort()
        if self.watcher:
            self.watcher.join(timeout=15)
            if self.watcher.is_alive():
                raise RuntimeError('The drive is still closing. Please wait and try again.')
        self.monitor = self.watcher = None
        self.guard.restore()

    def start(self, identity):
        self.pause()
        batch = self.library.batch(identity)
        if batch['finished']:
            self.library.set_active(identity)
            return
        devices = self.devices(refresh=True)
        if batch['drive'] not in devices['letters']:
            raise ValueError('Connect the USB CD drive, then check the selected drive letter.')
        if batch.get('drive_index', 0) not in [d['index'] for d in devices['encoders']]:
            raise ValueError('fre:ac cannot find the selected CD drive. Reconnect it and try again.')
        music = Path(batch['music']).expanduser()
        if not music.is_absolute():
            raise ValueError('Choose an absolute music folder, such as C:\\Users\\you\\Music.')
        music.mkdir(parents=True, exist_ok=True)
        self.guard.enable()
        try:
            (self.library.batches/identity/'command.json').unlink(missing_ok=True)
            monitor = FreacMonitor(self.library.batches/identity, batch['drive'], EXE, music, batch.get('drive_index', 0))
            watcher = threading.Thread(target=monitor.run, daemon=True)
            self.library.set_active(identity)
            self.monitor, self.watcher = monitor, watcher
            watcher.start()
        except Exception:
            self.guard.restore()
            raise

    def snapshot(self):
        batch = self.library.active()
        if not batch:
            return dict(phase='setup', completed=0, progress=0, updated=time.time())
        if batch['finished']:
            return dict(phase='finished', completed=batch['completed'], progress=100,
                        updated=time.time(), language=batch['language'], batch=batch['id'])
        if not self.monitor:
            return dict(phase='paused', completed=batch['completed'], progress=0,
                        updated=time.time(), language=batch['language'], batch=batch['id'])
        status = dict(self.monitor.status)
        if not self.watcher.is_alive() or time.time()-status.get('updated', 0)>20:
            status.update(phase='offline', detail='The copier stopped responding. Leave the CD inside and ask a grown-up.')
        status.update(language=batch['language'], batch=batch['id'])
        return status

    def defer(self):
        # Adult action: stop the encoder before allowing a troublesome CD out.
        batch = self.library.active()
        if not batch: raise ValueError('No active mission.')
        self.pause()
        batch = self.library.active()
        folder = self.library.batches/batch['id']
        records = []
        if (folder/'history.jsonl').exists():
            records = [json.loads(line) for line in (folder/'history.jsonl').read_text(encoding='utf-8').splitlines()]
        saved = {r['signature'] for r in records}
        queue = batch['albums']
        pending = [a for a in queue if a.get('signature') not in saved]
        if len(pending)<2: raise ValueError('This is the last CD. Leave it for another session, or retry it.')
        current = pending[0]
        queue.remove(current)
        queue.append(current)
        write_json(folder/'queue.json', queue)
        # Remain paused so reinserting/removing the old disc cannot restart it.
        return dict(ok=True, message='Copying stopped. Remove this CD and set it aside. Resume after the tray is empty.')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def respond(self, code, payload, kind='application/json'):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass

    def local(self, mutation=False):
        if self.headers.get('Host') != self.server.origin.removeprefix('http://'):
            self.respond(403, dict(error='Open this app using its 127.0.0.1 address.'))
            return False
        if mutation and (self.headers.get('Origin')!=self.server.origin or self.headers.get('Content-Type')!='application/json'):
            self.respond(403, dict(error='Local app requests only.'))
            return False
        return True

    def do_GET(self):
        if not self.local(): return
        app = self.server.app
        try:
            if self.path=='/api/info':
                self.respond(200, dict(app='library-cd-rip', version=1))
            elif self.path=='/api/session':
                with app.lock:
                    self.respond(200, dict(draft=app.library.draft(), active=app.library.active(),
                                           history=app.library.list_batches(), devices=app.devices(),
                                           running=bool(app.watcher and app.watcher.is_alive()),
                                           default_music=str(Path.home()/'Music')))
            elif self.path=='/api/status':
                self.respond(200, app.snapshot())
            elif re.fullmatch(r'/photos/[a-f0-9]{32}\.jpg', self.path):
                self.respond(200, (app.library.root/self.path.lstrip('/')).read_bytes(), 'image/jpeg')
            elif self.path in ('/', '/app.js', '/style.css'):
                name = 'index.html' if self.path=='/' else self.path[1:]
                kind = {'index.html':'text/html; charset=utf-8', 'app.js':'text/javascript; charset=utf-8', 'style.css':'text/css; charset=utf-8'}[name]
                self.respond(200, (ROOT/name).read_bytes(), kind)
            else:
                self.respond(404, dict(error='Not found'))
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            self.respond(400, dict(error=str(exc)))

    def do_POST(self):
        if not self.local(mutation=True): return
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0<length<36*1024*1024: return self.respond(413, dict(error='Request is too large.'))
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict): raise ValueError('Expected an object.')
            with self.server.app.lock:
                result = self.mutate(data)
            self.respond(200, result)
        except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            self.respond(400, dict(error=str(exc)))

    def mutate(self, data):
        app = self.server.app
        if self.path=='/api/photo':
            return app.library.import_photo(data['name'], data['data'], data.get('modified', 0))
        if self.path=='/api/draft':
            return app.library.save_draft(data)
        if self.path=='/api/refresh-drives':
            return app.devices(refresh=True)
        if self.path=='/api/start':
            app.pause()
            identity = app.library.create_batch(data)
            app.start(identity)
            return dict(ok=True, id=identity)
        if self.path=='/api/resume':
            identity = data.get('id') or app.library.active()['id']
            app.pause()
            batch=app.library.batch(identity)
            config=read_json(app.library.batches/identity/'batch.json',{})
            if data.get('drive'): config['drive']=str(data['drive'])[:2]
            if 'drive_index' in data: config['drive_index']=int(data['drive_index'])
            if data.get('language') in ('en-GB','de-DE'): config['language']=data['language']
            write_json(app.library.batches/identity/'batch.json',config)
            app.start(identity)
            return dict(ok=True)
        if self.path=='/api/pause':
            app.pause()
            return dict(ok=True)
        if self.path=='/api/defer':
            return app.defer()
        if self.path=='/api/retry':
            if not app.monitor: raise ValueError('Resume the mission first.')
            # Monitor consumes the command on its own thread.
            write_json(app.monitor.state_dir/'command.json', dict(action='retry'))
            return dict(ok=True)
        if self.path=='/api/edit-batch':
            app.pause()
            batch=app.library.active()
            if not batch: raise ValueError('No saved mission.')
            changes=data['albums']
            if len(changes)!=len(batch['albums']): raise ValueError('Keep the same CDs in a saved mission.')
            if any(old['id']!=new.get('id') for old,new in zip(batch['albums'],changes)):
                raise ValueError('Keep the same CD order when editing names.')
            # Reuse photo and text validation without losing the new-photo draft.
            previous=app.library.draft()
            try:
                clean=app.library.save_draft(dict(albums=changes,language=batch['language'],drive=batch['drive'],music=batch['music']))['albums']
            finally:
                write_json(app.library.root/'draft.json',previous)
            for old,new in zip(batch['albums'],clean):
                if old.get('signature'): new['signature']=old['signature']
                if old.get('saved'): new.update(old)
            write_json(app.library.batches/batch['id']/'queue.json',clean)
            return dict(ok=True)
        if self.path=='/api/quit':
            app.pause()
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return dict(ok=True)
        raise ValueError('Unknown action.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8735)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    url = f'http://127.0.0.1:{args.port}'
    try:
        with urllib.request.urlopen(url+'/api/info', timeout=1) as response:
            if json.load(response).get('app')=='library-cd-rip':
                if not args.no_browser: open_browser(url)
                return
    except (OSError, ValueError): pass
    HOME.mkdir(parents=True, exist_ok=True)
    app = Application(HOME)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.app, server.origin = app, url
    write_json(HOME/'session.json', dict(pid=os.getpid(), url=url))
    if not args.no_browser: open_browser(url)
    try:
        server.serve_forever()
    finally:
        app.pause()
        server.server_close()


if __name__=='__main__':
    try: main()
    except Exception:
        HOME.mkdir(parents=True, exist_ok=True)
        with (HOME/'error.log').open('a', encoding='utf-8') as log: traceback.print_exc(file=log)
        if sys.stderr: traceback.print_exc()
        ctypes_error = __import__('ctypes')
        ctypes_error.windll.user32.MessageBoxW(None, f'Library CD Rip could not start.\nSee {HOME / "error.log"}', 'Library CD Rip', 0x10)
