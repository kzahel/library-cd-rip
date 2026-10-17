import base64
import io
import json
from pathlib import Path
import tempfile
import unittest

import bootstrap
import sys
sys.path.insert(0,str(bootstrap.HOME/'vendor'))
from PIL import Image
from storage import Library, capture_time


def jpeg():
    output=io.BytesIO()
    Image.new('RGB',(120,160),'teal').save(output,format='JPEG')
    return base64.b64encode(output.getvalue()).decode()


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.library=Library(self.temp.name)
        self.photo=self.library.import_photo('PXL_20261017_124259354.jpg',jpeg())

    def tearDown(self): self.temp.cleanup()

    def album(self):
        return dict(id=self.photo['id'],title='A story',artist='A narrator',cover=self.photo['url'],titles=[])

    def test_camera_time_survives_exif_stripping(self):
        self.assertEqual(self.photo['captured'],'2026-10-17T12:42:59.354')
        self.assertEqual(capture_time('anything.jpg',{36867:'2024:01:02 03:04:05'},0),'2024-01-02T03:04:05')

    def test_upload_cannot_choose_a_destination_path(self):
        photo=self.library.import_photo('../../escape.jpg',jpeg())
        self.assertTrue((self.library.root/photo['url'].lstrip('/')).is_file())
        self.assertFalse((self.library.root.parent/'escape.jpg').exists())

    def test_bad_photo_and_external_cover_are_rejected(self):
        with self.assertRaises(ValueError): self.library.import_photo('not.jpg',base64.b64encode(b'bad').decode())
        album=self.album();album['cover']='../../some.jpg'
        with self.assertRaises(ValueError): self.library.save_draft(dict(albums=[album]))

    def test_draft_and_binding_survive_restart(self):
        draft=dict(albums=[self.album()],drive='E:',music=str(self.library.root/'music'))
        self.library.save_draft(draft)
        identity=self.library.create_batch(draft)
        restarted=Library(self.library.root)
        self.assertEqual(restarted.active()['id'],identity)
        self.assertEqual(restarted.active()['albums'][0]['title'],'A story')
        self.assertEqual(restarted.draft()['albums'],[])
        self.assertFalse(restarted.active()['finished'])

    def test_only_durable_record_finishes_batch(self):
        identity=self.library.create_batch(dict(albums=[self.album()],drive='E:'))
        folder=self.library.batches/identity
        queue=json.loads((folder/'queue.json').read_text())
        queue[0]['signature']='60000'
        (folder/'queue.json').write_text(json.dumps(queue))
        self.assertFalse(self.library.active()['finished'])
        (folder/'history.jsonl').write_text(json.dumps(dict(signature='60000',folder='music',tracks=1))+'\n')
        self.assertTrue(self.library.active()['finished'])

    def test_title_review_is_required(self):
        album=self.album();album['title']=''
        with self.assertRaises(ValueError): self.library.create_batch(dict(albums=[album]))
