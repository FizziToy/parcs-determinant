# -*- coding: utf-8 -*-
"""PARCS-Python solution: exact parallel integer matrix determinant.

This *single* file is uploaded as "Solution File" in the PARCS web UI.
It supports Python 2.7 (legacy PARCS runtime) and Python 3.x (local tests).
Only the PARCS worker RPC requires Pyro4.
"""
from __future__ import print_function

import json
import random
import threading
import time

try:
    from Pyro4 import expose
except ImportError:  # Permit offline unit tests without PARCS installed.
    def expose(function):
        return function


def is_prime(n):
    """Deterministic trial division; sufficient for our ~1e9 prime moduli."""
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    divisor = 3
    while divisor * divisor <= n:
        if n % divisor == 0:
            return False
        divisor += 2
    return True


def primes_descending(start=1000000007):
    if start < 2:
        raise ValueError('Prime search start must be >= 2')
    n = start
    while n >= 2:
        if is_prime(n):
            yield n
        n -= 1


def validate_matrix(matrix):
    if not isinstance(matrix, list) or not matrix:
        raise ValueError('Matrix must be a non-empty list')
    n = len(matrix)
    for row in matrix:
        if not isinstance(row, list) or len(row) != n:
            raise ValueError('Matrix must be square')
        for item in row:
            if isinstance(item, bool) or not isinstance(item, (int, long_type())):
                raise ValueError('Matrix entries must be integers')
    return n


def long_type():
    try:
        return long  # noqa: F821 - Python 2 type
    except NameError:
        return int


def create_matrix(n, seed, low, high):
    if n < 1 or n > 400:
        raise ValueError('Matrix size must be between 1 and 400')
    if low > high:
        raise ValueError('low must be <= high')
    rng = random.Random(seed)
    return [[rng.randint(low, high) for _ in range(n)] for _ in range(n)]


def det_mod(matrix, p):
    """Gaussian elimination in F_p, O(n^3); no floating-point errors."""
    n = len(matrix)
    a = [[value % p for value in row] for row in matrix]
    determinant = 1
    for col in range(n):
        pivot_index = col
        while pivot_index < n and a[pivot_index][col] == 0:
            pivot_index += 1
        if pivot_index == n:
            return 0
        if pivot_index != col:
            a[col], a[pivot_index] = a[pivot_index], a[col]
            determinant = -determinant
        pivot = a[col][col]
        determinant = (determinant * pivot) % p
        inverse = pow(pivot, p - 2, p)  # Fermat: p is prime.
        pivot_row = a[col]
        for row_index in range(col + 1, n):
            row = a[row_index]
            if row[col] == 0:
                continue
            factor = (row[col] * inverse) % p
            row[col] = 0
            for k in range(col + 1, n):
                row[k] = (row[k] - factor * pivot_row[k]) % p
    return determinant % p


def required_primes(matrix):
    """Find primes with product M > 2*Hadamard bound |det(A)|.

    Hadamard states det(A)^2 <= product_i sum_j(A_ij^2).
    Comparing M*M > 4*bound_squared avoids floating-point rounding.
    """
    bound_squared = 1
    for row in matrix:
        norm_squared = sum(value * value for value in row)
        bound_squared *= norm_squared
    modulus = 1
    primes = []
    for prime in primes_descending():
        primes.append(prime)
        modulus *= prime
        if modulus * modulus > 4 * bound_squared:
            break
    return primes


def crt_signed(residues):
    """Garner-style incremental Chinese Remainder Theorem reconstruction."""
    if not residues:
        raise ValueError('At least one modular residue is needed')
    x = 0
    modulus = 1
    for p, residue in residues:
        residue %= p
        if modulus % p == 0:
            raise ValueError('Moduli are not coprime')
        delta = ((residue - x) * pow(modulus % p, p - 2, p)) % p
        x += delta * modulus
        modulus *= p
    if x > modulus // 2:
        x -= modulus
    return x


def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def resolved_future(value):
    """PARCS uses Pyro4 async proxy; .value waits for the remote result."""
    try:
        return value.value
    except AttributeError:
        return value


class Solver(object):
    """Required PARCS interface: Solver(workers, input_file_name, output_file_name)."""

    def __init__(self, workers=None, input_file_name=None, output_file_name=None):
        self.workers = workers or []
        self.input_file_name = input_file_name
        self.output_file_name = output_file_name

    @expose
    def det_mod_batch(self, matrix, primes):
        """RPC endpoint executed independently on one PARCS worker."""
        return [(prime, det_mod(matrix, prime)) for prime in primes]

    def _parallel(self, matrix, primes, count):
        """Dispatch all remote RPCs concurrently, then collect results.

        PARCS-Python supplies *synchronous* Pyro4 proxies. A list of normal
        calls would run one by one and MUST NOT be reported as parallel.
        Python threads permit concurrent network-bound RPCs even on Python 2.7.
        Each thread operates on a different worker's Pyro4 proxy.
        """
        chunks = [primes[i::count] for i in range(count)]
        batches = [None] * count
        errors = [None] * count

        def run_remote(index):
            try:
                response = self.workers[index].det_mod_batch(matrix, chunks[index])
                batches[index] = resolved_future(response)
            except Exception as exc:
                errors[index] = exc

        threads = [threading.Thread(target=run_remote, args=(i,))
                   for i in range(count)]
        for thread in threads:
            thread.daemon = True
            thread.start()
        for thread in threads:
            thread.join()
        for index, error in enumerate(errors):
            if error is not None:
                raise RuntimeError('Worker %d RPC failed: %s' % (index + 1, error))

        by_prime = {}
        for batch in batches:
            if batch is None:
                raise RuntimeError('Worker returned no result')
            for p, residue in batch:
                if p in by_prime:
                    raise RuntimeError('Duplicate residue for prime %s' % p)
                by_prime[p] = residue
        if len(by_prime) != len(primes):
            raise RuntimeError('Some modular residues are missing')
        return crt_signed([(p, by_prime[p]) for p in primes])

    def solve(self):
        with open(self.input_file_name, 'r') as stream:
            config = json.load(stream)
        if 'matrix' in config:
            matrix = config['matrix']
        else:
            matrix = create_matrix(
                int(config.get('size', 64)), int(config.get('seed', 2026)),
                int(config.get('low', -9)), int(config.get('high', 9)))
        n = validate_matrix(matrix)
        requested = int(config.get('workers', 1))
        repetitions = int(config.get('repetitions', 3))
        if requested < 1 or repetitions < 1 or repetitions > 10:
            raise ValueError('workers >= 1 and repetitions in [1, 10] required')
        if len(self.workers) < requested:
            raise RuntimeError('Need %d registered workers, only %d available' %
                               (requested, len(self.workers)))
        primes = required_primes(matrix)
        seq_times, par_times = [], []
        determinant = None
        for rep in range(repetitions):
            # Alternating order reduces systematic bias from warm caches.
            def seq_job():
                start = time.time()
                residues = [(p, det_mod(matrix, p)) for p in primes]
                return crt_signed(residues), time.time() - start

            def par_job():
                start = time.time()
                result = self._parallel(matrix, primes, requested)
                return result, time.time() - start

            if rep % 2 == 0:
                seq_result, seq_sec = seq_job()
                par_result, par_sec = par_job()
            else:
                par_result, par_sec = par_job()
                seq_result, seq_sec = seq_job()
            if seq_result != par_result:
                raise AssertionError('Sequential and parallel determinants DIFFER')
            if determinant is not None and determinant != seq_result:
                raise AssertionError('Result changed between repetitions')
            determinant = seq_result
            seq_times.append(seq_sec)
            par_times.append(par_sec)
            print('repeat %d/%d: sequential %.4fs, parallel %.4fs' %
                  (rep + 1, repetitions, seq_sec, par_sec))
        t_seq, t_par = median(seq_times), median(par_times)
        result = {
            'algorithm': 'modular_gaussian_elimination_crt_exact',
            'size': n, 'workers': requested, 'registered_workers': len(self.workers),
            'prime_count': len(primes), 'repetitions': repetitions,
            'determinant': str(determinant), 'correct': True,
            'sequential_times_s': seq_times, 'parallel_times_s': par_times,
            'sequential_median_s': t_seq, 'parallel_median_s': t_par,
            'speedup': t_seq / t_par if t_par > 0 else None,
            'efficiency': t_seq / (requested * t_par) if t_par > 0 else None,
            'matrix_config': {key: config.get(key) for key in ('seed', 'low', 'high')
                              if key in config},
        }
        with open(self.output_file_name, 'w') as stream:
            json.dump(result, stream, sort_keys=True, indent=2)
        print('Done: matrix=%d, workers=%d, primes=%d, correct=True' %
              (n, requested, len(primes)))
        return result
