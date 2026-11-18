"""Run: python -m unittest discover -s tests -v"""
import json
import random
import tempfile
import threading
import unittest
from itertools import permutations
from pathlib import Path

from solver import (Solver, crt_signed, create_matrix, det_mod,
                    required_primes, validate_matrix)


def determinant_brute(matrix):
    n = len(matrix)
    result = 0
    for perm in permutations(range(n)):
        inversions = sum(perm[i] > perm[j] for i in range(n)
                         for j in range(i + 1, n))
        product = 1
        for i, j in enumerate(perm):
            product *= matrix[i][j]
        result += (-1 if inversions % 2 else 1) * product
    return result


class Immediate(object):
    def __init__(self, value):
        self.value = value


class FakeWorker(object):
    """Simulates only the RPC interface, not PARCS cloud execution."""
    def det_mod_batch(self, matrix, primes):
        return Immediate(Solver().det_mod_batch(matrix, primes))


class DeterminantTests(unittest.TestCase):
    def det_exact(self, matrix):
        return crt_signed([(p, det_mod(matrix, p)) for p in required_primes(matrix)])

    def test_one_by_one(self):
        for value in [-77, 0, 43]:
            self.assertEqual(self.det_exact([[value]]), value)

    def test_known_matrices(self):
        self.assertEqual(self.det_exact([[1, 2], [3, 4]]), -2)
        self.assertEqual(self.det_exact([[2, 7], [2, 7]]), 0)
        self.assertEqual(self.det_exact([[0, 2], [3, 4]]), -6)
        self.assertEqual(self.det_exact([[1, 2, 3], [0, 4, 5], [1, 0, 6]]), 22)
        self.assertEqual(self.det_exact([[100000, 0], [0, -100001]]), -10000100000)

    def test_random_small_against_permutation_definition(self):
        rng = random.Random(99)
        for n in range(1, 6):
            for _ in range(12):
                matrix = [[rng.randint(-10, 10) for _ in range(n)] for _ in range(n)]
                self.assertEqual(self.det_exact(matrix), determinant_brute(matrix))

    def test_row_swap_changes_sign(self):
        matrix = create_matrix(5, 2026, -3, 3)
        swapped = [list(r) for r in matrix]
        swapped[0], swapped[1] = swapped[1], swapped[0]
        self.assertEqual(self.det_exact(swapped), -self.det_exact(matrix))

    def test_invalid_matrix(self):
        with self.assertRaises(ValueError):
            validate_matrix([[1], [2]])
        with self.assertRaises(ValueError):
            validate_matrix([[True]])

    def test_solver_with_simulated_remote_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            in_path = Path(folder) / 'in.txt'
            out_path = Path(folder) / 'out.txt'
            in_path.write_text(json.dumps({'size': 7, 'seed': 2026,
                                           'workers': 3, 'repetitions': 2}), encoding='utf-8')
            result = Solver([FakeWorker() for _ in range(4)], str(in_path),
                            str(out_path)).solve()
            saved = json.loads(out_path.read_text(encoding='utf-8'))
            self.assertTrue(saved['correct'])
            self.assertEqual(saved['workers'], 3)
            self.assertEqual(len(saved['parallel_times_s']), 2)
            self.assertEqual(saved['determinant'], result['determinant'])

    def test_remote_calls_really_overlap(self):
        # If the implementation accidentally makes one RPC after another,
        # the barrier times out. All three must begin before any can finish.
        barrier = threading.Barrier(3)

        class CoordinatedWorker(object):
            def det_mod_batch(self, matrix, primes):
                barrier.wait(timeout=2.0)
                return Solver().det_mod_batch(matrix, primes)

        matrix = [[2, 1], [1, 2]]
        solver = Solver([CoordinatedWorker() for _ in range(3)])
        self.assertEqual(solver._parallel(matrix, [101, 103, 107], 3), 3)

    def test_requires_enough_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            in_path = Path(folder) / 'in.txt'
            out_path = Path(folder) / 'out.txt'
            in_path.write_text(json.dumps({'size': 2, 'workers': 2}), encoding='utf-8')
            with self.assertRaises(RuntimeError):
                Solver([FakeWorker()], str(in_path), str(out_path)).solve()


if __name__ == '__main__':
    unittest.main()


class ParallelStructureTests(unittest.TestCase):
    def test_split_tasks_when_not_divisible(self):
        from solver import split_tasks
        primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
        batches = split_tasks(primes, 4)
        self.assertEqual(batches, [[2, 11, 23], [3, 13, 29], [5, 17], [7, 19]])

    def test_reduce_rejects_missing_result(self):
        from solver import reduce_results
        with self.assertRaises(RuntimeError):
            reduce_results([101, 103], [[(101, 4)]])

    def test_reduce_rejects_duplicate_result(self):
        from solver import reduce_results
        with self.assertRaises(RuntimeError):
            reduce_results([101], [[(101, 4)], [(101, 4)]])
