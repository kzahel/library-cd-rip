import json
import threading
import unittest
import urllib.error
import urllib.request
import tempfile

from fixture_server import make_server
from test_storage import jpeg


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=make_server(self.temp.name)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()
        self.url=self.server.origin

    def tearDown(self):
        self.server.shutdown();self.worker.join();self.server.server_close();self.temp.cleanup()

    def request(self,path,data=None,origin=None,host=None):
        headers={}
        if data is not None: headers.update({'Content-Type':'application/json','Origin':origin or self.url})
        if host: headers['Host']=host
        request=urllib.request.Request(self.url+path, data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(request) as response: return response.status,json.load(response)
        except urllib.error.HTTPError as exc: return exc.code,json.load(exc)

    def test_foreign_pages_and_hosts_cannot_control_ripping(self):
        self.assertEqual(self.request('/api/pause',{},origin='https://untrusted.example')[0],403)
        self.assertEqual(self.request('/api/session',host='untrusted.example')[0],403)
        self.assertEqual(self.request('/photos/../../app.py')[0],404)

    def test_photos_to_saved_mission_and_resume(self):
        code,photo=self.request('/api/photo',dict(name='PXL_20260101_120000000.jpg',data=jpeg()))
        self.assertEqual(code,200)
        draft=dict(albums=[dict(id=photo['id'],cover=photo['url'],title='Story',artist='Narrator')],drive='E:',music=self.temp.name)
        self.assertEqual(self.request('/api/draft',draft)[0],200)
        code,started=self.request('/api/start',draft)
        self.assertEqual(code,200)
        self.assertEqual(self.request('/api/status')[1]['phase'],'ready')
        self.assertEqual(self.request('/api/pause',{})[0],200)
        self.assertEqual(self.request('/api/status')[1]['phase'],'paused')
        self.assertEqual(self.request('/api/resume',dict(id=started['id']))[0],200)
        self.assertEqual(self.request('/api/status')[1]['phase'],'ready')
        self.assertEqual(self.request('/test/phase',dict(phase='finished'))[0],200)
        self.assertEqual(self.request('/api/status')[1]['phase'],'finished')

    def test_deferring_stops_and_keeps_partial_cd_binding(self):
        albums=[]
        for i in range(2):
            _,photo=self.request('/api/photo',dict(name=f'{i}.jpg',data=jpeg()))
            albums.append(dict(id=photo['id'],cover=photo['url'],title=f'Story {i}',artist='Narrator'))
        self.request('/api/start',dict(albums=albums,drive='E:',music=self.temp.name))
        folder=self.server.app.library.batches/self.server.app.library.active()['id']
        queue=json.loads((folder/'queue.json').read_text());queue[0]['signature']='unfinished'
        (folder/'queue.json').write_text(json.dumps(queue))
        self.assertEqual(self.request('/api/defer',{})[0],200)
        active=self.request('/api/session')[1]
        self.assertFalse(active['running'])
        self.assertEqual(active['active']['albums'][-1]['signature'],'unfinished')
        self.assertEqual(active['active']['albums'][0]['title'],'Story 1')
