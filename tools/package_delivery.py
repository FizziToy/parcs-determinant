"""Package reviewed source/data/report for Cloud Shell without Git or secrets."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report-dir', default='20261119_workers_only')
    parser.add_argument('--run', default='experiments/workers_only_20261119')
    args = parser.parse_args()
    top_files = {'.gitignore', '.gitattributes', 'README.md', 'build_solver.py', 'solver.py', 'results.csv'}
    allowed_dirs = {'src', 'tests', 'tools', 'cloud', 'docs', 'inputs', 'outputs', 'experiments'}
    records = []
    with zipfile.ZipFile(args.out, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob('*')):
            relative = path.relative_to(ROOT)
            if not path.is_file() or '__pycache__' in relative.parts:
                continue
            if relative.parts[0] == 'reports':
                if relative.parts[1] != args.report_dir or 'qa' in relative.parts:
                    continue
            elif relative.parts[0] not in allowed_dirs and relative.as_posix() not in top_files:
                continue
            if path.suffix in ('.pyc', '.zip', '.key', '.pem', '.pfx'):
                continue
            content = path.read_bytes()
            if path.suffix == '.sh':
                content = content.replace(b'\r\n', b'\n')
            name = 'parcs-determinant/' + relative.as_posix()
            archive.writestr(name, content)
            records.append(dict(path=relative.as_posix(), size=len(content),
                                sha256=hashlib.sha256(content).hexdigest()))
        archive.writestr('parcs-determinant/' + args.run.rstrip('/') + '/outputs/', b'')
        archive.writestr('parcs-determinant/DELIVERY_MANIFEST.json', json.dumps(
            dict(branch='refactor-parallel', baseline='e35ca13', execution_model='workers_only',
                 cloud_experiments_run=False,
                 files=records), indent=2))
    with zipfile.ZipFile(args.out) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Archive integrity check failed')
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    with args.out.with_suffix('.zip.sha256').open('x', encoding='ascii') as handle:
        handle.write(digest + '  ' + args.out.name + '\n')
    print('Packaged', len(records), 'files:', args.out, 'SHA256:', digest)


if __name__ == '__main__':
    main()
