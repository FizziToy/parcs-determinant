# PARCS: exact matrix determinant

The program calculates an **exact integer determinant** via modular Gaussian
elimination and the Chinese Remainder Theorem (CRT).

## Parallel idea

1. **Master** creates/reads a square integer matrix and chooses enough prime moduli.
2. `split_tasks()` divides **primes**, not rows of the matrix, between workers.
3. **Map**: each worker receives the whole matrix and a *different* subset of primes;
   `mymap()` calculates `det(A) % p` for each of its primes.
4. **Reduce**: `myreduce()` checks the collected residues and uses CRT to
   reconstruct the exact signed determinant.
5. The program runs sequential and parallel implementations, verifies equality,
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
