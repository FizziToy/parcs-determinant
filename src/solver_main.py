"""PARCS entry point: Master coordinates; Workers prepare, Map and Reduce."""
import json

try:
    from Pyro4 import expose
except ImportError:
    # Allows mathematical and orchestration tests without installing PARCS.
    def expose(function):
        return function


class Solver(object):
    """Master runs solve(); every mathematical operation runs on a Worker."""

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

    @expose
    def prepare_problem(self, config):
        """WORKER: create/validate the matrix and choose the exact CRT bound."""
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
        return {'matrix': matrix, 'size': size, 'primes': required_primes(matrix)}

    @expose
    def reduce_determinant(self, primes, batches):
        """WORKER REDUCE: validate residues and reconstruct the signed integer."""
        return self.myreduce(primes, batches)

    @staticmethod
    def myreduce(primes, batches):
        """REDUCE: check every result and reconstruct the exact determinant."""
        return reduce_results(primes, batches)

    @staticmethod
    def split_tasks(primes, worker_count):
        """Assign different primes to workers (the matrix itself is shared)."""
        return split_tasks(primes, worker_count)

    def _parallel(self, matrix, primes, worker_count):
        """MASTER: dispatch Map, then ask the first Worker to perform Reduce."""
        batches = map_tasks(self.workers, matrix, primes, worker_count)
        result = get_result(self.workers[0].reduce_determinant(primes, batches))
        if isinstance(result, bool) or not isinstance(result, integer_types()):
            raise RuntimeError('Invalid Worker Reduce result')
        return result

    def solve(self):
        """MASTER: read input, coordinate remote jobs, compare, and save output."""
        with open(self.input_file_name, 'r') as file:
            config = json.load(file)

        worker_count = int(config.get('workers', 1))
        repetitions = int(config.get('repetitions', 3))

        if worker_count < 1 or not 1 <= repetitions <= 10:
            raise ValueError('Invalid workers or repetitions')
        if worker_count > len(self.workers):
            raise RuntimeError('Not enough registered workers')

        problem = get_result(self.workers[0].prepare_problem(config))
        matrix, primes, size = problem['matrix'], problem['primes'], problem['size']

        def run_sequential():
            # The baseline uses the SAME remote path, with exactly one Worker.
            return self._parallel(matrix, primes, 1)

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
            'execution_model': 'workers_only',
            'timing_baseline': 'one_remote_worker_including_rpc_and_reduce',
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
