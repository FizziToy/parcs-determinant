# PARCS: exact matrix determinant

The program calculates an **exact integer determinant** via modular Gaussian
elimination and the Chinese Remainder Theorem (CRT).

## Parallel idea

1. **Master** reads the configuration and asks the first **Worker** to prepare
   the matrix and choose enough prime moduli. Master performs no matrix mathematics.
2. `split_tasks()` divides **primes**, not rows of the matrix, between workers.
3. **Map**: each worker receives the whole matrix and a *different* subset of primes;
   `mymap()` calculates `det(A) % p` for each of its primes.
4. **Worker Reduce**: Master calls `reduce_determinant()` on the first Worker;
   `myreduce()` checks the residues and reconstructs the exact signed determinant there.
5. The program compares one remote Worker against the requested remote Workers,
   and saves median timings, speedup and efficiency.

This is **not** block-row Gaussian elimination. It is parallelism over independent
modular determinant computations. The custom Python threads overlap the RPC
calls; the mathematical calculations execute on the remote PARCS workers.

## Files

| File | Role |
| --- | --- |
| `src/matrix_math.py` | Matrix generation, modular Gaussian elimination, CRT |
| `src/parallel.py` | Task distribution, parallel RPC dispatch, reduce |
| `src/measurements.py` | Repeat benchmark, check equality, median time |
| `src/solver_main.py` | PARCS `Solver` class: Master, Map, Reduce |
| `build_solver.py` | Bundle modules into one stand-alone file for the PARCS web uploader |
| `solver.py` | Generated file: upload to PARCS, **do not edit directly** |
| `tests/test_solver.py` | Unit tests and simulated workers |

## Build and test

```bash
python3 build_solver.py
python3 -m unittest discover -s tests -v
python3 -m py_compile solver.py
```

## PARCS input example

```json
{"size": 64, "workers": 4, "repetitions": 3, "seed": 2026}
```

Upload `solver.py` as Code and the JSON file as Input. The PARCS cluster must
have at least the requested number of workers registered.

## Optimized exact kernels and experiments

The standalone solver still works without mathematical dependencies. Its Python
kernel caches row tails and uses list comprehensions. If NumPy is installed,
matrices of size 32 or larger use exact `int64` outer-product elimination.
No floating-point determinant is used. The accelerated kernel is selected only
when `p*(p-1) <= 2**63-1`; larger primes fall back to Python integers. Matrix
entries are reduced modulo p before conversion, so arbitrarily large input
integers remain supported. Generated matrix sizes now include 512.

For a comparable cloud benchmark, install/check the SAME NumPy version on the
four workers before the series. Master does not need NumPy. The stock PARCS image uses
Python 2.7; `cloud/install_numpy_existing.sh` optionally installs NumPy 1.16.6
there. Local validation used Python 3.12 and NumPy 2.3.5; the legacy cloud
environment still needs a real smoke test. Without NumPy the Python kernel is
used automatically.

The existing `results.csv`, `outputs/` and report template are historical and
preserved. They are not results of the optimized solver.

* [Ukrainian audit](docs/OPTIMIZATION_AUDIT_UK.md)
* [Exact Cloud Shell transfer and execution commands](docs/CLOUD_RUN_UK.md)
* `experiments/local_kernels_20261118/`: actual local per-prime comparisons
* `experiments/local_exact_20261118/`: actual full local exact computations
* `experiments/workers_only_20261119/`: current 12-job plan; no new cloud results

Master only coordinates preparation, Map and Worker Reduce, measures time,
compares returned answers and writes output. The existing `sequential_*` JSON
fields now measure **one remote Worker including RPC and Worker Reduce**.
`parallel_*` uses the same path with the requested number of Workers.
Output adds `execution_model=workers_only` and a `timing_baseline` marker.
The runner/analyzer reject the older master-computed baseline. Previous plans,
reports, archives and local kernel measurements remain preserved as historical data.

New experiment tools refuse to overwrite data. Prepare a fresh directory for
each series and analyze only its verified output/provenance pairs:

```bash
python3 tools/prepare_experiments.py --out experiments/my_new_run
python3 tools/run_cloud_experiments.py --run experiments/my_new_run --check-only
python3 tools/run_cloud_experiments.py --run experiments/my_new_run
python3 tools/analyze_experiments.py --run experiments/my_new_run --out analysis/my_new_run --plots
```

`--resume` recovers a recorded remote job or preserves verified completed jobs
without posting duplicates. A lost connection after submission requires
inspection of `/jobs`; the runner never retries an ambiguous submission.

`python3 -m unittest discover -s tests -v` exercises both kernels when NumPy is
available and explicitly skips optional NumPy tests when it is absent. Simulated
RPC/HTTP tests do not count as cloud experiments.
