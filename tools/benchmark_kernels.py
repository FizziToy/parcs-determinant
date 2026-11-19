"""Measure actual LOCAL kernels, not PARCS worker speedup.

The baseline is loaded from a named Git revision into memory. All timings are
for one prime, with equal inputs and equality checks against the original code.
"""
import argparse
import csv
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import solver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--baseline', default='e35ca13')
    parser.add_argument('--sizes', nargs='+', type=int, default=[128, 256, 512])
    parser.add_argument('--repetitions', type=int, default=3)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    baseline_source = subprocess.check_output(
        ['git', 'show', args.baseline + ':src/matrix_math.py'], cwd=ROOT, text=True)
    namespace = {}
    exec(compile(baseline_source, '<original matrix_math>', 'exec'), namespace)
    kernels = [('original_python', namespace['det_mod']),
               ('optimized_python', solver.det_mod_python)]
    if solver._numpy is not None:
        kernels.append(('numpy_int64', solver.det_mod_numpy))
    metadata = {
        'environment': 'local_windows_not_parcs', 'python': sys.version,
        'platform': platform.platform(), 'processor': platform.processor(),
        'numpy': getattr(solver._numpy, '__version__', None),
        'baseline_revision': args.baseline, 'seed': 2026, 'prime': 1000000007,
        'solver_sha256': hashlib.sha256((ROOT / 'solver.py').read_bytes()).hexdigest(),
        'metric': 'one_modular_determinant_including_copy_and_conversion',
    }
    (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    with (args.out / 'raw.csv').open('x', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            'environment', 'size', 'kernel', 'repetition', 'seconds', 'residue', 'correct'])
        writer.writeheader()
        for size in args.sizes:
            matrix = solver.create_matrix(size, 2026, -9, 9)
            expected = None
            durations = {name: [] for name, _ in kernels}
            for repetition in range(1, args.repetitions + 1):
                order = kernels if repetition % 2 else list(reversed(kernels))
                for name, kernel in order:
                    started = time.perf_counter()
                    residue = kernel(matrix, metadata['prime'])
                    duration = time.perf_counter() - started
                    if expected is None:
                        expected = residue
                    if residue != expected:
                        raise AssertionError('Different modular determinants')
                    writer.writerow(dict(environment=metadata['environment'], size=size,
                                         kernel=name, repetition=repetition, seconds=duration,
                                         residue=residue, correct=True))
                    handle.flush()
                    durations[name].append(duration)
                print('Completed n=%d repetition=%d' % (size, repetition), flush=True)
            print('Medians:', {k: statistics.median(v) for k, v in durations.items()}, flush=True)


if __name__ == '__main__':
    main()
