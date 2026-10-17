import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from freac_monitor import FreacMonitor


class FreacTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        exe=self.root/'freac/freac-1.1.7-x64/freaccmd.exe'
        exe.parent.mkdir(parents=True)
        exe.touch()
        self.m=FreacMonitor(self.root,'E:')
        self.m.signature='60000,60000'

    def tearDown(self):
        self.temp.cleanup()

    def test_files_alone_cannot_signal_new_rip_success(self):
        self.assertFalse(self.m.completion_allowed())
        self.m.rip_complete=True
        self.assertTrue(self.m.completion_allowed())

    def test_previously_verified_disc_is_resumable(self):
        self.m.records=[dict(signature=self.m.signature)]
        self.assertTrue(self.m.completion_allowed())

    def test_failed_encoder_does_not_allow_completion(self):
        self.m.rip_signature=self.m.signature
        self.m.process=Mock()
        self.m.process.poll.return_value=1
        self.m.process.returncode=1
        self.m.index=1
        with patch('monitor.Monitor.tick'):
            self.m.tick()
        self.assertIn('exit 1',self.m.fault)
        self.assertFalse(self.m.completion_allowed())

    def test_command_never_ejects_cd(self):
        self.m.folder=self.root/'output'
        self.m.folder.mkdir()
        self.m.total_tracks=2
        self.m.lengths=[60,60]
        with patch('freac_monitor.subprocess.Popen') as popen, patch('freac_monitor.threading.Thread'):
            self.m.start_next()
        args=popen.call_args.args[0]
        self.assertNotIn('--eject',args)
        self.assertIn('--track=1',args)
        self.assertIn('CBR',args)

    def test_active_encoder_does_not_interrogate_cd_with_second_api(self):
        self.m.process=Mock()
        self.m.process.poll.return_value=None
        self.m.rip_signature=self.m.signature
        self.m.lengths=[60,60]
        self.m.total_tracks=2
        self.m.index=1
        with patch('monitor.Monitor.tick') as physical_scan:
            self.m.tick()
        physical_scan.assert_not_called()
        self.assertEqual(self.m.status['phase'],'ripping')

    def test_restart_does_not_start_encoder_for_saved_album(self):
        self.m.records=[dict(signature=self.m.signature)]
        with patch('monitor.Monitor.tick'), patch('freac_monitor.subprocess.Popen') as start:
            self.m.tick()
        start.assert_not_called()

    def test_complete_looking_file_without_success_receipt_is_not_reused(self):
        self.m.folder=self.root/'output';self.m.folder.mkdir()
        self.m.total_tracks=1;self.m.lengths=[60]
        (self.m.folder/'01 Track 1.mp3').write_bytes(b'old partial')
        with patch.object(self.m,'valid',return_value=True),patch('freac_monitor.subprocess.Popen') as start,patch('freac_monitor.threading.Thread'):
            self.m.start_next()
        start.assert_called_once()
        self.assertEqual(len(list(self.m.folder.glob('*.incomplete-*.mp3'))),1)

    def test_verified_receipt_allows_resume_without_encoder(self):
        import hashlib
        self.m.folder=self.root/'output';self.m.folder.mkdir()
        self.m.total_tracks=1;self.m.lengths=[60]
        data=b'verified audio';(self.m.folder/'01 Track 1.mp3').write_bytes(data)
        self.m.receipts={self.m.signature:{'1':hashlib.sha256(data).hexdigest()}}
        with patch.object(self.m,'valid',return_value=True),patch('freac_monitor.subprocess.Popen') as start:
            self.m.start_next()
        start.assert_not_called();self.assertTrue(self.m.rip_complete)
