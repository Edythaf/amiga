"""Source-only EC2 archive. Credentials and existing users/documents never enter it."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {'storage', '__pycache__', '.git', '.venv', 'node_modules', '.runtime-temp'}


def release_files(root=ROOT):
    files = []
    for folder in ('backend', 'frontend/portal', 'migrations', 'deploy/ec2'):
        for path in (root / folder).rglob('*'):
            relative = path.relative_to(root)
            if not path.is_file() or path.is_symlink() or EXCLUDED.intersection(relative.parts):
                continue
            if path.name.startswith('.env') and path.name != '.env.example':
                continue
            if folder == 'backend' and path.suffix != '.py' and path.name != 'requirements.txt':
                continue
            if path.name not in {'LICENSE', 'NOTICE'} and path.suffix.lower() not in {'.py', '.txt', '.html', '.css', '.js', '.mjs', '.json', '.sql', '.png', '.svg', '.woff2', '.pdf', '.service', '.example', '.conf'}:
                continue
            files.append(path)
    for name in ('.gitattributes', 'DEPLOY_EC2.md', 'API_TERBARU.md'):
        path = root / name
        if path.is_file():
            files.append(path)
    return sorted(files)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='.runtime-temp/amiga-ec2.tar.gz')
    parser.add_argument('--list-only', action='store_true')
    parser.add_argument('--replace', action='store_true', help='Replace only the generated archive at the explicit output path')
    args = parser.parse_args()
    files = release_files()
    if args.list_only:
        print('\n'.join(p.relative_to(ROOT).as_posix() for p in files))
        print('Source files:', len(files))
        return
    destination = (ROOT / args.output).resolve()
    if not destination.is_relative_to(ROOT) or destination.suffixes[-2:] != ['.tar', '.gz']:
        raise SystemExit('Choose a .tar.gz inside this project.')
    if destination.exists() and not args.replace:
        raise SystemExit('Archive already exists. Preserve it or choose an explicit new output path.')
    contents = {}
    for path in files:
        data = path.read_bytes()
        if path.suffix not in ('.png', '.woff2', '.pdf') and re.search(
                rb'(?:sk-[A-Za-z0-9_-]{40,}|AKIA[A-Z0-9]{16}|[0-9]{8,10}:[A-Za-z0-9_-]{35})', data):
            raise SystemExit('Possible embedded credential: ' + path.relative_to(ROOT).as_posix())
        contents[path.relative_to(ROOT).as_posix()] = data
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
    contents['RELEASE_SHA256.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('wb' if args.replace else 'xb') as output, tarfile.open(fileobj=output, mode='w:gz') as archive:
        for name, data in contents.items():
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode = len(data), 0o644
            archive.addfile(entry, io.BytesIO(data))
    print('Prepared source archive:', destination)
    print('SHA256:', hashlib.sha256(destination.read_bytes()).hexdigest())
    print('Deployment has not been performed.')


if __name__ == '__main__':
    main()
