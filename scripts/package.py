"""Package this script-free theme without design files, caches, or signing keys."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def identity(key_file, expected_id):
    if key_file is None or not isinstance(expected_id, str) or not re.fullmatch('[a-p]{32}', expected_id):
        raise ValueError('Replacement requires the existing listing public key and exact verified item ID')
    key = ''.join(key_file.read_text().split())
    try:
        der = base64.b64decode(key, validate=True)
    except ValueError as error:
        raise ValueError('Expected base64 DER public key') from error
    if not der or len(der) > 8192:
        raise ValueError('Invalid public key size')
    checked = subprocess.run(['openssl', 'pkey', '-pubin', '-inform', 'DER', '-noout'], input=der, capture_output=True)
    if checked.returncode:
        raise ValueError('Expected existing public key, never a private key or certificate')
    actual = ''.join(chr(ord('a') + int(c, 16)) for c in hashlib.sha256(der).hexdigest()[:32])
    if actual != expected_id:
        raise ValueError('Existing public key does not match verified listing ID')
    return key


def package(mode, output_root, public_key=None, expected_id=None):
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    if set(manifest) != {'manifest_version', 'version', 'name', 'icons', 'theme'}:
        raise ValueError('Theme source must contain only its reviewed manifest fields')
    if manifest['manifest_version'] != 3:
        raise ValueError('Expected current Manifest V3 theme')
    if mode == 'replacement':
        manifest['key'] = identity(public_key, expected_id)
        manifest['version_name'] = manifest['version'] + ' development replacement'
    elif public_key is not None or expected_id is not None:
        raise ValueError('Only explicit replacement mode accepts production identity')
    if mode == 'separate':
        manifest['version'] += '.1'
        manifest['version_name'] = manifest['version'] + ' Development'
        manifest['name'] += ' Development'
    output = output_root / mode
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    files = ['manifest.json'] + list(manifest['icons'].values())
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for name in files[1:]:
        if Path(name).name != name or not name.endswith('.png'):
            raise ValueError('Unexpected icon path')
        shutil.copyfile(ROOT / name, output / name)
    archive = output_root / ('dark-purple-theme-' + mode + '-' + manifest['version'] + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, (output / name).read_bytes())
    return {'mode': mode, 'version': manifest['version'], 'path': str(archive.resolve()),
            'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'unpacked': str(output.resolve())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['production', 'separate', 'replacement'], required=True)
    parser.add_argument('--output-root', type=Path, default=ROOT / 'dist')
    parser.add_argument('--public-key-file', type=Path)
    parser.add_argument('--expected-id')
    args = parser.parse_args()
    try:
        print(json.dumps(package(args.mode, args.output_root, args.public_key_file, args.expected_id), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')
