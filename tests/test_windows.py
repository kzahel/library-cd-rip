from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from windows import AutoPlayGuard


class FakeRegistry:
    HKEY_CURRENT_USER=0
    REG_DWORD=4
    def __init__(self): self.values={}
    @contextmanager
    def CreateKey(self,root,path): yield path
    def QueryValueEx(self,path,name):
        if (path,name) not in self.values: raise FileNotFoundError()
        return self.values[path,name]
    def SetValueEx(self,path,name,reserved,kind,value): self.values[path,name]=(value,kind)
    def DeleteValue(self,path,name): del self.values[path,name]


class AutoPlayTests(unittest.TestCase):
    def test_original_values_restore_after_restart_and_missing_values_are_removed(self):
        with tempfile.TemporaryDirectory() as folder,patch('windows.winreg',FakeRegistry()) as registry:
            key=AutoPlayGuard.SETTINGS[0][:2]
            registry.values[key]=(0,4)
            before=dict(registry.values)
            guard=AutoPlayGuard(Path(folder));guard.enable()
            self.assertEqual(registry.values[key],(1,4))
            self.assertTrue(guard.path.exists())
            restarted=AutoPlayGuard(Path(folder));restarted.restore()
            self.assertEqual(registry.values,before)
            self.assertFalse(guard.path.exists())

    def test_restore_preserves_a_newer_external_setting_change(self):
        with tempfile.TemporaryDirectory() as folder,patch('windows.winreg',FakeRegistry()) as registry:
            guard=AutoPlayGuard(Path(folder));guard.enable()
            key=AutoPlayGuard.SETTINGS[1][:2]
            registry.values[key]=(255,4)
            guard.restore()
            self.assertEqual(registry.values[key],(255,4))
