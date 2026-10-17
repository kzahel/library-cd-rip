import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import json

from monitor import Monitor


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.m = Monitor(self.root,'E:')
        self.m.opened = True
        self.m.find_folder = lambda lengths: self.root
        self.m.closed = lambda f: True
        self.m.label = lambda config, files: None
        self.m.config = lambda: {}
        self.m.publish = lambda **kw: setattr(self,'status',kw)
        def query(cmd):
            if 'media present' in cmd: return 'true'
            if 'number of tracks' in cmd: return '2'
            if 'length track' in cmd: return '60000'
            raise AssertionError(cmd)
        self.m.query = query
        self.patch = patch('monitor.MP3',lambda f: SimpleNamespace(info=SimpleNamespace(length=60,sketchy=False)))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_partial_disc_never_green(self):
        (self.root/'01 Track.mp3').touch()
        self.m.tick()
        self.assertEqual(self.status['phase'],'ripping')
        self.assertEqual(self.status['progress'],50)
        self.assertFalse(self.m.done)

    def test_all_files_must_be_closed(self):
        for n in [1,2]: (self.root/f'0{n} Track.mp3').touch()
        self.m.closed = lambda f: f.name.startswith('01')
        self.m.tick()
        self.assertFalse(self.m.done)

    def test_complete_disc_requires_settle_then_records_once(self):
        for n in [1,2]: (self.root/f'0{n} Track.mp3').touch()
        self.m.tick()
        self.assertFalse(self.m.done)
        self.m.ready_since -= 5
        self.m.tick()
        self.assertTrue(self.m.done)
        self.assertEqual(self.status['phase'],'done')
        self.m.tick()
        self.assertEqual(self.m.total,1)
        self.assertEqual(len(self.m.history.read_text().splitlines()),1)

    def test_wrong_duration_does_not_pass(self):
        for n in [1,2]: (self.root/f'0{n} Track.mp3').touch()
        with patch('monitor.MP3',lambda f: SimpleNamespace(info=SimpleNamespace(length=20,sketchy=False))):
            self.m.tick()
        self.assertFalse(self.m.done)
        self.assertEqual(self.status['progress'],0)

    def test_removed_disc_clears_green(self):
        self.m.done=True
        self.m.query=lambda cmd:'false'
        self.m.tick()
        self.assertEqual(self.status['phase'],'empty')
        self.assertFalse(self.m.done)

    def test_status_file_lock_cannot_stop_updates(self):
        del self.m.publish
        with patch.object(Path,'replace',side_effect=PermissionError('File is in use')):
            self.m.publish(phase='done',progress=100)
        self.assertEqual(self.m.status['phase'],'done')
        self.assertEqual(self.m.status['progress'],100)
        self.m.publish(phase='empty')
        self.assertEqual(self.m.status['phase'],'empty')

    def test_restart_does_not_count_same_cd_twice(self):
        for n in [1,2]: (self.root/f'0{n} Track.mp3').touch()
        self.m.records=[dict(signature='60000,60000')]
        self.m.total=1
        self.m.tick()
        self.m.ready_since-=5
        self.m.tick()
        self.assertEqual(self.status['phase'],'done')
        self.assertEqual(self.m.total,1)

    def test_next_cover_advances_only_after_saved_disc(self):
        queue=[dict(title='First CD',cover='/covers/1.jpg',signature='first'),
               dict(title='Second CD',cover='/covers/2.jpg')]
        (self.root/'queue.json').write_text(json.dumps(queue))
        del self.m.publish
        self.m.publish(phase='empty')
        self.assertEqual(self.m.status['next_cover'],'/covers/1.jpg')
        self.m.records=[dict(signature='first')]
        self.m.publish(phase='done')
        self.assertEqual(self.m.status['next_cover'],'/covers/2.jpg')

    def test_queue_disc_binding_survives_restart(self):
        queue=[dict(title='First CD',cover='/covers/1.jpg'),dict(title='Second CD')]
        (self.root/'queue.json').write_text(json.dumps(queue))
        del self.m.config
        self.m.signature='new-disc'
        self.assertEqual(self.m.config()['title'],'First CD')
        self.assertEqual(self.m.config()['title'],'First CD')
        saved=json.loads((self.root/'queue.json').read_text())
        self.assertEqual(saved[0]['signature'],'new-disc')
        self.assertNotIn('signature',saved[1])

    def test_wrong_cd_cannot_skip_unfinished_queue_item(self):
        queue=[dict(title='Unfinished CD',signature='original'),dict(title='Next CD')]
        (self.root/'queue.json').write_text(json.dumps(queue))
        del self.m.config
        self.m.signature='different-disc'
        with self.assertRaisesRegex(ValueError,'unfinished CD back'):
            self.m.config()
        saved=json.loads((self.root/'queue.json').read_text())
        self.assertNotIn('signature',saved[1])

    def test_early_removal_requires_same_disc(self):
        self.m.signature='unfinished'
        self.m.done=False
        self.m.query=lambda cmd:'false'
        self.m.tick()
        self.assertIn('same CD',self.status['detail'])


if __name__ == '__main__':
    unittest.main()
