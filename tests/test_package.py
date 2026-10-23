import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('package', ROOT / 'scripts/package.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackageTests(unittest.TestCase):
    def test_runtime_whitelist_and_icon_dimensions(self):
        with tempfile.TemporaryDirectory() as temp:
            item = module.package('production', Path(temp))
            with zipfile.ZipFile(item['path']) as bundle:
                self.assertEqual(set(bundle.namelist()), {'manifest.json', 'Logo16.png', 'Logo32.png', 'Logo48.png', 'Logo128.png'})
                manifest = json.loads(bundle.read('manifest.json'))
                self.assertEqual(set(manifest), {'manifest_version', 'version', 'name', 'icons', 'theme'})
                self.assertEqual(manifest['manifest_version'], 3)
                self.assertEqual(manifest['version'], '1.0.1')
                for size, name in manifest['icons'].items():
                    data = bundle.read(name)
                    self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
                    self.assertEqual(struct.unpack('>II', data[16:24]), (int(size), int(size)))
                self.assertIsNone(bundle.testzip())

    def test_reproducible(self):
        with tempfile.TemporaryDirectory() as temp:
            a = module.package('production', Path(temp))
            b = module.package('production', Path(temp))
            self.assertEqual(a['sha256'], b['sha256'])

    def test_separate_dev_preserves_theme_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            item = module.package('separate', Path(temp))
            with zipfile.ZipFile(item['path']) as bundle:
                dev = json.loads(bundle.read('manifest.json'))
            production = json.loads((ROOT / 'manifest.json').read_text())
            self.assertEqual(dev['theme'], production['theme'])
            self.assertEqual(dev['version'], '1.0.1.1')
            self.assertNotIn('key', dev)
            self.assertNotIn('permissions', dev)
            self.assertIn('Development', dev['name'])

    def test_replacement_missing_identity_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'not-created'
            with self.assertRaises(ValueError):
                module.package('replacement', output)
            self.assertFalse(output.exists())

    def test_replacement_malformed_identity_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            key = Path(temp) / 'invalid-public.txt'
            key.write_text('not a public key')
            output = Path(temp) / 'not-created'
            with self.assertRaises(ValueError):
                module.package('replacement', output, key, 'a' * 32)
            self.assertFalse(output.exists())

    def test_production_rejects_identity_override(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                module.package('production', Path(temp), Path('unread'), 'a' * 32)


if __name__ == '__main__':
    unittest.main()
