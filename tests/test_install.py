import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

path = pathlib.Path(__file__).parents[1] / 'native' / 'install.py'
spec = importlib.util.spec_from_file_location('installer',path)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux installer integration')
class InstallerTests(unittest.TestCase):
    def test_per_user_install_real_launcher_and_uninstall(self):
        with tempfile.TemporaryDirectory(prefix='paperless test ') as tmp:
            root=pathlib.Path(tmp)
            with patch.object(pathlib.Path,'home',return_value=root),patch.object(sys,'argv',[str(path)]):
                installer.main()
            manifest=root/'.mozilla/native-messaging-hosts/paperless_send_api.json'
            data=json.loads(manifest.read_text())
            self.assertEqual(data['allowed_extensions'],['paperless-send@local'])
            import struct
            message=b'{"id":1,"action":"ping"}'
            proc=subprocess.run([data['path'],str(manifest),'paperless-send@local'],input=struct.pack('=I',len(message))+message,capture_output=True,check=True)
            length=struct.unpack('=I',proc.stdout[:4])[0]
            self.assertEqual(json.loads(proc.stdout[4:4+length])['version'],'2.0.0')
            unrelated=root/'document.pdf';unrelated.write_bytes(b'keep')
            with patch.object(pathlib.Path,'home',return_value=root),patch.object(sys,'argv',[str(path),'--uninstall']):
                installer.main()
            self.assertFalse(manifest.exists());self.assertEqual(unrelated.read_bytes(),b'keep')
