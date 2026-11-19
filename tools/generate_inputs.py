"""Make deterministic PARCS input files for the 1,2,3,4-worker experiments."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sizes', nargs='+', type=int, default=[128, 256, 512])
    parser.add_argument('--workers', nargs='+', type=int, default=[1, 2, 3, 4])
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--out', type=Path, default=Path('inputs'))
    args = parser.parse_args()
    planned = [args.out / f'n{n}_p{p}.txt' for n in args.sizes for p in args.workers]
    if any(path.exists() for path in planned):
        raise SystemExit('Input files already exist. Choose a new --out directory.')
    args.out.mkdir(parents=True, exist_ok=True)
    for n in args.sizes:
        for p in args.workers:
            payload = {'size': n, 'workers': p, 'repetitions': args.repetitions,
                       'seed': args.seed, 'low': -9, 'high': 9}
            path = args.out / f'n{n}_p{p}.txt'
            path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
            print('created:', path)


if __name__ == '__main__':
    main()
