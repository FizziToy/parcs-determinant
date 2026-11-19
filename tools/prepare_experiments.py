"""Create a new, isolated 12-configuration PARCS experiment plan."""
import argparse
import hashlib
import json
from pathlib import Path
from run_cloud_experiments import EXECUTION_MODEL, TIMING_BASELINE

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'inputs').mkdir()
    (args.out / 'outputs').mkdir()
    jobs = []
    for size in (128, 256, 512):
        for workers in (1, 2, 3, 4):
            name = 'N%d_W%d' % (size, workers)
            config = dict(size=size, workers=workers, repetitions=3, seed=2026)
            path = args.out / 'inputs' / ('input_' + name + '.json')
            path.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
            jobs.append(dict(name=name, input='inputs/' + path.name, config=config,
                             output='outputs/' + name + '.json'))
    manifest = dict(project='parcs-514519', zone='us-central1-a',
                    execution_model=EXECUTION_MODEL, timing_baseline=TIMING_BASELINE,
                    solver_sha256=hashlib.sha256((ROOT / 'solver.py').read_bytes()).hexdigest(),
                    status='prepared_not_executed', low=-9, high=9, jobs=jobs)
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Prepared 12 jobs, 36 paired measurements in', args.out)


if __name__ == '__main__':
    main()
