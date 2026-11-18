# -*- coding: utf-8 -*-
"""Generated PARCS entry point. Edit src/*.py, then run build_solver.py.

Map: workers calculate determinants modulo different primes.
Reduce: master reconstructs the exact determinant with CRT.
"""
from __future__ import print_function



# ===== src/matrix_math.py =====

"""Exact matrix determinant: modular Gaussian elimination and CRT."""
import random


def integer_types():
    try:
        return (int, long)
    except NameError:
        return (int,)


def validate_matrix(matrix):
    if not isinstance(matrix, list) or not matrix:
        raise ValueError('Matrix must not be empty')
    size = len(matrix)
    for row in matrix:
        if not isinstance(row, list) or len(row) != size:
            raise ValueError('Matrix must be square')
        for number in row:
            if isinstance(number, bool) or not isinstance(number, integer_types()):
                raise ValueError('Matrix must contain integers')
    return size


def create_matrix(size, seed, low, high):
    if not 1 <= size <= 400 or low > high:
        raise ValueError('Invalid matrix parameters')
    rng = random.Random(seed)
    return [[rng.randint(low, high) for _ in range(size)]
            for _ in range(size)]


def is_prime(number):
    if number < 2:
        return False
    if number % 2 == 0:
        return number == 2
    divisor = 3
    while divisor * divisor <= number:
        if number % divisor == 0:
            return False
        divisor += 2
    return True


def required_primes(matrix):
    """Select enough primes to reconstruct a signed determinant exactly."""
    # Hadamard: |det(A)|^2 <= product of squared row lengths.
    bound_squared = 1
    for row in matrix:
        bound_squared *= sum(number * number for number in row)

    product = 1
    primes = []
    number = 1000000007
    while True:
        if is_prime(number):
            primes.append(number)
            product *= number
            if product * product > 4 * bound_squared:
                return primes
        number -= 1


def det_mod(matrix, prime):
    """Gaussian elimination computes determinant modulo a prime."""
    size = len(matrix)
    rows = [[value % prime for value in row] for row in matrix]
    result = 1

    for col in range(size):
        pivot_row = col
        while pivot_row < size and rows[pivot_row][col] == 0:
            pivot_row += 1
        if pivot_row == size:
            return 0

        if pivot_row != col:
            rows[col], rows[pivot_row] = rows[pivot_row], rows[col]
            result = -result

        pivot = rows[col][col]
        result = result * pivot % prime
        inverse = pow(pivot, prime - 2, prime)

        for i in range(col + 1, size):
            if rows[i][col] == 0:
                continue
            factor = rows[i][col] * inverse % prime
            rows[i][col] = 0
            for j in range(col + 1, size):
                rows[i][j] = (rows[i][j] - factor * rows[col][j]) % prime

    return result % prime


def crt_signed(residues):
    """Combine modular remainders into a signed integer (CRT)."""
    if not residues:
        raise ValueError('At least one residue is required')

    result = 0
    product = 1
    for prime, remainder in residues:
        if product % prime == 0:
            raise ValueError('Primes must be distinct')
        correction = ((remainder - result) *
                      pow(product % prime, prime - 2, prime)) % prime
        result += correction * product
        product *= prime

    return result - product if result > product // 2 else result



# ===== src/parallel.py =====

"""Task distribution and result collection for PARCS."""
import threading


def split_tasks(primes, worker_count):
    """Round-robin distribution: every prime goes to exactly one worker."""
    if worker_count < 1:
        raise ValueError('At least one worker is required')
    return [primes[index::worker_count] for index in range(worker_count)]


def get_result(response):
    """Unwrap a PARCS result proxy; also support immediate local test replies."""
    try:
        return response.value
    except AttributeError:
        return response


def map_tasks(workers, matrix, primes, worker_count):
    """MAP: call each remote worker concurrently with its assigned primes."""
    tasks = split_tasks(primes, worker_count)
    results = [None] * worker_count
    errors = [None] * worker_count

    def call_worker(index):
        try:
            response = workers[index].det_mod_batch(matrix, tasks[index])
            results[index] = get_result(response)
        except Exception as error:
            errors[index] = error

    # Threads overlap network calls; calculations happen on remote VMs.
    threads = []
    for index in range(worker_count):
        thread = threading.Thread(target=call_worker, args=(index,))
        thread.daemon = True
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    for index, error in enumerate(errors):
        if error is not None:
            raise RuntimeError('Worker %d failed: %s' % (index + 1, error))

    return results


def reduce_results(primes, batches):
    """REDUCE: check that no prime is lost or repeated, then apply CRT."""
    residues = {}
    for batch in batches:
        if batch is None:
            raise RuntimeError('Missing worker response')
        for prime, remainder in batch:
            if prime in residues:
                raise RuntimeError('Duplicate prime %d' % prime)
            residues[prime] = remainder

    if set(residues) != set(primes):
        raise RuntimeError('Missing or unexpected modular results')

    ordered = [(prime, residues[prime]) for prime in primes]
    return crt_signed(ordered)



# ===== src/measurements.py =====

"""Benchmark helpers and output formatting."""
import time


def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def measure(job):
    started = time.time()
    result = job()
    return result, time.time() - started


def benchmark(sequential_job, parallel_job, repetitions):
    sequential_times = []
    parallel_times = []
    answer = None

    for repetition in range(repetitions):
        # Alternating order reduces warm-up/order bias.
        jobs = [('sequential', sequential_job), ('parallel', parallel_job)]
        if repetition % 2:
            jobs.reverse()

        results = {}
        for name, job in jobs:
            result, duration = measure(job)
            results[name] = result
            if name == 'sequential':
                sequential_times.append(duration)
            else:
                parallel_times.append(duration)

        if results['sequential'] != results['parallel']:
            raise AssertionError('Sequential and parallel results differ')
        if answer is not None and results['sequential'] != answer:
            raise AssertionError('Result changed between repetitions')
        answer = results['sequential']

    return answer, sequential_times, parallel_times



# ===== src/solver_main.py =====

"""PARCS entry point: Master distributes tasks; workers calculate; Master combines."""
import json

try:
    from Pyro4 import expose
except ImportError:
    # Allows mathematical and orchestration tests without installing PARCS.
    def expose(function):
        return function


class Solver(object):
    """PARCS calls solve() on Master and det_mod_batch() on each Worker."""

    def __init__(self, workers=None, input_file_name=None, output_file_name=None):
        self.workers = workers if workers is not None else []
        self.input_file_name = input_file_name
        self.output_file_name = output_file_name

    @staticmethod
    @expose
    def mymap(matrix, primes):
        """MAP: calculate det(A) modulo each assigned prime."""
        return [(prime, det_mod(matrix, prime)) for prime in primes]

    @expose
    def det_mod_batch(self, matrix, primes):
        """Remote PARCS method: delegates the calculation to MAP."""
        return self.mymap(matrix, primes)

    @staticmethod
    def myreduce(primes, batches):
        """REDUCE: check every result and reconstruct the exact determinant."""
        return reduce_results(primes, batches)

    @staticmethod
    def split_tasks(primes, worker_count):
        """Assign different primes to workers (the matrix itself is shared)."""
        return split_tasks(primes, worker_count)

    def _parallel(self, matrix, primes, worker_count):
        batches = map_tasks(self.workers, matrix, primes, worker_count)
        return self.myreduce(primes, batches)

    @staticmethod
    def sequential(matrix, primes):
        """Same mathematics, calculated locally without remote workers."""
        batch = Solver.mymap(matrix, primes)
        return Solver.myreduce(primes, [batch])

    def solve(self):
        """MASTER: read input, run both methods, compare, and save measurements."""
        with open(self.input_file_name, 'r') as file:
            config = json.load(file)

        if 'matrix' in config:
            matrix = config['matrix']
        else:
            matrix = create_matrix(
                int(config.get('size', 64)),
                int(config.get('seed', 2026)),
                int(config.get('low', -9)),
                int(config.get('high', 9))
            )

        size = validate_matrix(matrix)
        worker_count = int(config.get('workers', 1))
        repetitions = int(config.get('repetitions', 3))

        if worker_count < 1 or not 1 <= repetitions <= 10:
            raise ValueError('Invalid workers or repetitions')
        if worker_count > len(self.workers):
            raise RuntimeError('Not enough registered workers')

        primes = required_primes(matrix)

        def run_sequential():
            return self.sequential(matrix, primes)

        def run_parallel():
            return self._parallel(matrix, primes, worker_count)

        determinant, sequential_times, parallel_times = benchmark(
            run_sequential, run_parallel, repetitions
        )

        sequential_median = median(sequential_times)
        parallel_median = median(parallel_times)
        speedup = (sequential_median / parallel_median
                   if parallel_median > 0 else None)

        output = {
            'algorithm': 'modular_gaussian_elimination_crt_exact',
            'size': size,
            'workers': worker_count,
            'registered_workers': len(self.workers),
            'prime_count': len(primes),
            'repetitions': repetitions,
            'determinant': str(determinant),
            'correct': True,
            'sequential_times_s': sequential_times,
            'parallel_times_s': parallel_times,
            'sequential_median_s': sequential_median,
            'parallel_median_s': parallel_median,
            'speedup': speedup,
            'efficiency': speedup / worker_count if speedup is not None else None,
            'matrix_config': {key: config[key] for key in ('seed', 'low', 'high')
                              if key in config}
        }

        with open(self.output_file_name, 'w') as file:
            json.dump(output, file, indent=2, sort_keys=True)

        print('Done: matrix=%d, workers=%d, correct=True' % (size, worker_count))
        return output

