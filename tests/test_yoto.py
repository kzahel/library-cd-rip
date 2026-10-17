import tempfile
import importlib.util
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch

import yoto_prepare as yoto


@skipUnless(importlib.util.find_spec('reportlab'), 'Install requirements-yoto.txt for Yoto tests')
class YotoTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.album = self.root / 'album'
        self.album.mkdir()
        self.plan = self.root / 'plan.json'
        self.output = self.root / 'prepared'
        yoto.write_json(self.plan, {'cards': [{'title': 'Stories', 'albums': [{'folder': 'album'}]}]})

    def tearDown(self):
        self.temp.cleanup()

    def track(self, filename):
        path = self.album / filename
        path.write_bytes(('test data for ' + filename).encode())
        return path

    def probe(self, path):
        return dict(title=path.stem, album='Album', artist='Reader', seconds=60, track_number=None)

    def test_numeric_tags_determine_upload_order_not_filenames(self):
        self.track('a.mp3')
        self.track('z.mp3')
        def reader(path):
            return dict(self.probe(path), track_number=2 if path.stem == 'a' else 1)
        cards = yoto.prepare_cards(self.plan, reader)
        self.assertEqual([t['source_name'] for t in cards[0]['tracks']], ['z.mp3', 'a.mp3'])
        self.assertEqual([t['file'] for t in cards[0]['tracks']],
                         ['card-01/001 z.mp3', 'card-01/002 a.mp3'])

    def test_untagged_tracks_sort_naturally_and_mixed_tags_stop(self):
        for name in ('10.mp3', '2.mp3', '1.mp3'):
            self.track(name)
        tracks = yoto.load_album(self.album, self.probe)
        self.assertEqual([t['source_name'] for t in tracks], ['1.mp3', '2.mp3', '10.mp3'])
        for numbers in ([1, None, 3], [1, 1, 3]):
            iterator = iter(numbers)
            with self.assertRaisesRegex(ValueError, 'Mixed or duplicate'):
                yoto.load_album(self.album, lambda p: dict(self.probe(p), track_number=next(iterator)))

    def test_track_and_card_limits_stop_before_output(self):
        self.track('1.mp3')
        with self.assertRaisesRegex(ValueError, '60 minutes'):
            yoto.build(self.plan, self.output, lambda p: dict(self.probe(p), seconds=3601))
        with patch.object(yoto, 'MAX_BYTES', 1), self.assertRaisesRegex(ValueError, 'exceeds Yoto limits'):
            yoto.build(self.plan, self.output, self.probe)
        self.assertFalse(self.output.exists())

    def test_contents_reject_gaps_overlap_and_out_of_order(self):
        yoto.validate_contents([dict(first=1, last=2, title='Two tracks')], 2)
        for rows in ([dict(first=1, last=1, title='Gap')],
                     [dict(first=1, last=2, title='All'), dict(first=2, last=2, title='Overlap')],
                     [dict(first=2, last=2, title='Second'), dict(first=1, last=1, title='First')]):
            with self.assertRaises(ValueError):
                yoto.validate_contents(rows, 2)

    def test_rerun_preserves_receipts_and_detects_same_size_corruption(self):
        source = self.track('1.mp3')
        original = source.read_bytes()
        result = yoto.build(self.plan, self.output, self.probe)
        card = result['cards'][0]
        card.update(yoto_url='https://example.invalid/existing', uploaded_order_verified=True,
                    linked_confirmation='User observed linked', offline_download_verified=False)
        yoto.write_json(self.output / 'manifest.json', result)
        repeated = yoto.build(self.plan, self.output, self.probe)
        self.assertEqual(repeated['cards'][0]['yoto_url'], card['yoto_url'])
        self.assertEqual(repeated['cards'][0]['linked_confirmation'], card['linked_confirmation'])
        target = self.output / card['tracks'][0]['file']
        target.write_bytes(b'x' * len(original))
        with self.assertRaisesRegex(ValueError, 'Existing staged file differs'):
            yoto.build(self.plan, self.output, self.probe)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(target.read_bytes(), b'x' * len(original))

    def test_changed_plan_or_nonempty_folder_is_preserved(self):
        self.track('1.mp3')
        self.output.mkdir()
        (self.output / 'keep.txt').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'not empty'):
            yoto.build(self.plan, self.output, self.probe)
        self.assertEqual((self.output / 'keep.txt').read_text(), 'keep')
        other = self.root / 'other'
        yoto.build(self.plan, other, self.probe)
        plan = yoto.read_json(self.plan)
        plan['cards'][0]['title'] = 'Changed'
        yoto.write_json(self.plan, plan)
        with self.assertRaisesRegex(ValueError, 'different plan'):
            yoto.build(self.plan, other, self.probe)

    def test_interrupted_copy_can_resume_without_claiming_completion(self):
        self.track('1.mp3')
        original_copy = yoto.copy_verified
        with patch.object(yoto, 'copy_verified', side_effect=OSError('Disconnected')):
            with self.assertRaises(OSError):
                yoto.build(self.plan, self.output, self.probe)
        self.assertFalse(yoto.read_json(self.output / 'manifest.json')['prepared'])
        with patch.object(yoto, 'copy_verified', wraps=original_copy):
            self.assertTrue(yoto.build(self.plan, self.output, self.probe)['prepared'])
