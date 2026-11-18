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
