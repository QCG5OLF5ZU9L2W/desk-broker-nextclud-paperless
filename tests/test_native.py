import importlib.util
import io
import json
import pathlib
import struct
import tempfile
import unittest

path = pathlib.Path(__file__).parents[1] / 'native' / 'paperless_helper.py'
spec = importlib.util.spec_from_file_location('helper',path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)

class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / 'Änderung #1.pdf'
        self.original = b'%PDF-1.4\n' + b'a' * 600000
        self.path.write_bytes(self.original)
        self.host = helper.Host()
    def tearDown(self):
        self.tmp.cleanup()
    def opened(self):
        return self.host.dispatch({'action':'open','path':str(self.path)})
    def test_read_chunks_and_delete_verified_file(self):
        import base64,hashlib
        x = self.opened(); data = b''
        while len(data) < x['size']:
            r = self.host.dispatch({'action':'read','ref':x['ref'],'offset':len(data)})
            data += base64.b64decode(r['data'])
        self.assertEqual(data,self.original)
        self.assertEqual(hashlib.sha256(data).hexdigest(),x['sha256'])
        self.host.dispatch({'action':'delete','ref':x['ref'],'sha256':x['sha256']})
        self.assertFalse(self.path.exists())
    def test_changed_original_retained(self):
        x=self.opened();self.path.write_bytes(b'%PDF-1.4 new')
        with self.assertRaises(ValueError):self.host.dispatch({'action':'delete','ref':x['ref'],'sha256':x['sha256']})
        self.assertTrue(self.path.exists())
    def test_replaced_original_retained(self):
        x=self.opened();self.path.unlink();self.path.write_bytes(self.original)
        with self.assertRaises(ValueError):self.host.dispatch({'action':'delete','ref':x['ref'],'sha256':x['sha256']})
        self.assertTrue(self.path.exists())
    def test_unopened_file_and_wrong_digest_never_deleted(self):
        with self.assertRaises(ValueError):self.host.dispatch({'action':'delete','ref':'unknown','path':str(self.path)})
        x=self.opened()
        with self.assertRaises(ValueError):self.host.dispatch({'action':'delete','ref':x['ref'],'sha256':'wrong'})
        self.assertTrue(self.path.exists())
    def test_released_reference_cannot_delete(self):
        x=self.opened();self.host.dispatch({'action':'release','ref':x['ref']})
        with self.assertRaises(ValueError):self.host.dispatch({'action':'delete','ref':x['ref'],'sha256':x['sha256']})
    def test_non_pdf_rejected(self):
        self.path.write_bytes(b'not pdf')
        with self.assertRaises(ValueError):self.opened()
    def test_wire_protocol_utf8_and_multiple_messages(self):
        msgs=[{'id':1,'action':'ping'},{'id':2,'action':'open','path':str(self.path)}]
        data=b''
        for m in msgs:
            b=json.dumps(m).encode();data+=struct.pack('=I',len(b))+b
        out=io.BytesIO();helper.serve(io.BytesIO(data),out);out.seek(0)
        replies=[]
        while header:=out.read(4):replies.append(json.loads(out.read(struct.unpack('=I',header)[0])))
        self.assertEqual(len(replies),2);self.assertTrue(all(r['ok'] for r in replies));self.assertEqual(replies[1]['filename'],self.path.name)
    def test_fragmented_stdin(self):
        class Fragmented(io.BytesIO):
            def read(self,size=-1):return super().read(min(size,2))
        raw=json.dumps({'id':1,'action':'ping'}).encode();out=io.BytesIO()
        helper.serve(Fragmented(struct.pack('=I',len(raw))+raw),out)
        self.assertIn(b'2.0.0',out.getvalue())
    def test_windows_linux_unc_urls(self):
        self.assertEqual(helper.parse_path('file:///C:/Users/Test/A%20%231.pdf',True),r'C:\Users\Test\A #1.pdf')
        self.assertEqual(helper.parse_path('file://server/share/A.pdf',True),r'\\server\share\A.pdf')
        self.assertEqual(helper.parse_path(self.path.as_uri(),False),str(self.path))
        with self.assertRaises(ValueError):helper.parse_path('file://server/share/A.pdf',False)

if __name__=='__main__':unittest.main()
