"""Isolated UI/HTTP fixture. It never calls a drive, registry or encoder API."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Application, Handler, ThreadingHTTPServer
from storage import Library, write_json


class FakeApplication(Application):
    def __init__(self, home):
        self.library=Library(home)
        self.lock=threading.RLock()
        self.monitor=self.watcher=None
        self._devices=dict(letters=['E:'],encoders=[dict(index=0,device='test',name='Test USB drive')])

    def devices(self,refresh=False): return self._devices

    def pause(self): self.monitor=self.watcher=None

    def start(self,identity):
        self.library.set_active(identity)
        self.monitor=SimpleNamespace(status={})
        self.watcher=SimpleNamespace(is_alive=lambda:True)
        self.phase('ready')

    def phase(self,phase,**extra):
        batch=self.library.active()
        album=next((a for a in batch['albums'] if not a['saved']),batch['albums'][-1])
        status=dict(phase=phase,updated=time.time(),completed=batch['completed'],progress=0,
                    album=album['title'],next_title=album['title'],next_cover=album['cover'],
                    queue_position=batch['albums'].index(album)+1,queue_total=len(batch['albums']))
        status.update(extra)
        if phase=='finished':
            queue=batch['albums']
            folder=self.library.batches/batch['id']
            for i,a in enumerate(queue): a['signature']=str(i+1000)
            write_json(folder/'queue.json',queue)
            (folder/'history.jsonl').write_text('\n'.join(json.dumps(dict(signature=a['signature'],tracks=1,folder='test')) for a in queue)+'\n')
        if self.monitor is None:
            self.monitor=SimpleNamespace(status={})
            self.watcher=SimpleNamespace(is_alive=lambda:True)
        self.monitor.status=status


class FixtureHandler(Handler):
    def mutate(self,data):
        if self.path=='/test/phase':
            self.server.app.phase(**data)
            return dict(ok=True)
        return super().mutate(data)


def make_server(home,port=0):
    server=ThreadingHTTPServer(('127.0.0.1',port),FixtureHandler)
    server.app=FakeApplication(home)
    server.origin=f'http://127.0.0.1:{server.server_port}'
    return server


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory() as home:
        server=make_server(home,args.port)
        print(server.origin,flush=True)
        try: server.serve_forever()
        finally: server.server_close()
