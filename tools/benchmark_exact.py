"""Time full exact determinants locally; never label these as cloud timings."""
import argparse
import csv
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import solver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if solver._numpy is None:
        raise SystemExit('Use an environment with NumPy for this large local benchmark.')
    args.out.mkdir(parents=True, exist_ok=False)
    metadata = dict(environment='local_windows_not_parcs', python=sys.version,
                    numpy=solver._numpy.__version__, platform=platform.platform(),
                    solver_sha256=hashlib.sha256((ROOT / 'solver.py').read_bytes()).hexdigest(),
                    seed=2026, repetitions=3, low=-9, high=9,
                    metric='full_sequential_modular_elimination_and_crt_excluding_preparation')
    (args.out / 'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    with (args.out / 'raw.csv').open('x', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            'environment', 'size', 'prime_count', 'repetition', 'seconds',
            'determinant', 'consistent', 'extra_prime_verified'])
        writer.writeheader()
        for n in (128, 256, 512):
            matrix = solver.create_matrix(n, 2026, -9, 9)
            primes = solver.required_primes(matrix)
            expected = None
            # A different modulus and the independent original Python-style kernel
            # provide an additional check. This is not the CRT stopping criterion.
            extra_prime = 1000000009
            extra_residue = solver.det_mod_python(matrix, extra_prime)
            for repetition in range(1, 4):
                started = time.perf_counter()
                determinant = solver.det_exact_local(matrix, primes)
                duration = time.perf_counter() - started
                if expected is not None and determinant != expected:
                    raise AssertionError('Determinant changed')
                if determinant % extra_prime != extra_residue:
                    raise AssertionError('Extra modular check failed')
                expected = determinant
                writer.writerow(dict(environment=metadata['environment'], size=n,
                                     prime_count=len(primes), repetition=repetition,
                                     seconds=duration, determinant=str(determinant),
                                     consistent=True, extra_prime_verified=True))
                handle.flush()
                print('Exact LOCAL n=%d k=%d repeat=%d seconds=%.4f' %
                      (n, len(primes), repetition, duration), flush=True)


if __name__ == '__main__':
    main()
