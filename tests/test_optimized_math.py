"""Independent correctness checks for both exact kernels and large inputs."""
import copy
import math
import random
import unittest
from unittest.mock import patch

import solver


def determinant_bareiss(matrix):
    """Fraction-free integer elimination, independent of modular Gaussian/CRT."""
    rows = copy.deepcopy(matrix)
    sign, previous = 1, 1
    for col in range(len(rows) - 1):
        pivot_row = next((i for i in range(col, len(rows)) if rows[i][col]), None)
        if pivot_row is None:
            return 0
        if pivot_row != col:
            rows[col], rows[pivot_row] = rows[pivot_row], rows[col]
            sign = -sign
        pivot = rows[col][col]
        for i in range(col + 1, len(rows)):
            for j in range(col + 1, len(rows)):
                numerator = rows[i][j] * pivot - rows[i][col] * rows[col][j]
                quotient, remainder = divmod(numerator, previous)
                assert remainder == 0
                rows[i][j] = quotient
            rows[i][col] = 0
        previous = pivot
    return sign * rows[-1][-1]


class OptimizedMathTests(unittest.TestCase):
    def test_python_against_bareiss_and_crt(self):
        for size in (2, 8, 17, 32):
            matrix = solver.create_matrix(size, 2026, -99, 99)
            expected = determinant_bareiss(matrix)
            residues = [(p, solver.det_mod_python(matrix, p))
                        for p in solver.required_primes(matrix)]
            self.assertEqual(solver.crt_signed(residues), expected)

    def test_prime_selection_has_strict_integer_bound(self):
        for matrix in ([[0]], [[-10**200]], solver.create_matrix(32, 2026, -9, 9)):
            primes = solver.required_primes(matrix)
            bound_squared = math.prod(sum(x*x for x in row) for row in matrix)
            self.assertGreater(math.prod(primes)**2, 4 * bound_squared)
            self.assertEqual(len(set(primes)), len(primes))
            self.assertTrue(all(solver.is_prime(p) for p in primes))
            if len(primes) > 1:
                self.assertLessEqual(math.prod(primes[:-1])**2, 4 * bound_squared)

    def test_generator_accepts_512_and_rejects_larger(self):
        matrix = solver.create_matrix(512, 2026, -9, 9)
        self.assertEqual(solver.validate_matrix(matrix), 512)
        self.assertEqual(matrix, solver.create_matrix(512, 2026, -9, 9))
        with self.assertRaises(ValueError):
            solver.create_matrix(513, 2026, -9, 9)

    def test_512_triangular_negative_determinant_full_crt(self):
        # Nonzero upper triangle; 512 dimensions and many reconstruction primes.
        n = 512
        matrix = [[(3 if i == j else (1 if j > i else 0))
                   for j in range(n)] for i in range(n)]
        matrix[0][0] = -3
        self.assertEqual(solver.det_exact_local(matrix, solver.required_primes(matrix)),
                         -(3**n))

    def test_no_numpy_fallback_and_input_not_modified(self):
        matrix = solver.create_matrix(32, 2026, -9, 9)
        original = copy.deepcopy(matrix)
        with patch.object(solver, '_numpy', None):
            self.assertEqual(solver.math_backend(matrix, 101), 'python_integer')
            self.assertEqual(solver.det_mod(matrix, 101), determinant_bareiss(matrix) % 101)
        self.assertEqual(matrix, original)

    def test_singular_mod_prime_can_have_nonzero_integer_determinant(self):
        matrix = [[101, 0], [0, 103]]
        self.assertEqual(solver.det_mod(matrix, 101), 0)
        self.assertEqual(solver.det_exact_local(matrix, solver.required_primes(matrix)),
                         10403)

    def test_reduce_rejects_noncanonical_residues(self):
        for remainder in (-1, 101, 1.5, True, '4'):
            with self.assertRaises(RuntimeError):
                solver.reduce_results([101], [[(101, remainder)]])

    @unittest.skipIf(solver._numpy is None, 'NumPy optional backend unavailable')
    def test_numpy_against_bareiss_small_fields_and_row_swaps(self):
        rng = random.Random(987)
        for n in (1, 2, 5, 17, 32):
            matrix = [[rng.randint(-10, 10) for _ in range(n)] for _ in range(n)]
            matrix[0][0] = 0
            expected = determinant_bareiss(matrix)
            for p in (2, 3, 5, 101, 1000000007, 3037000493):
                self.assertTrue(solver.is_prime(p))
                self.assertEqual(solver.det_mod_numpy(matrix, p), expected % p)
            singular = copy.deepcopy(matrix)
            singular[-1] = singular[0][:]
            if n > 1:
                self.assertEqual(solver.det_mod_numpy(singular, 1000000007), 0)

    @unittest.skipIf(solver._numpy is None, 'NumPy optional backend unavailable')
    def test_numpy_huge_inputs_reduced_before_casting(self):
        huge = 10**100
        matrix = [[huge + 2, -huge], [huge, huge + 3]]
        original = copy.deepcopy(matrix)
        expected = determinant_bareiss(matrix)
        residues = [(p, solver.det_mod_numpy(matrix, p))
                    for p in solver.required_primes(matrix)]
        self.assertEqual(solver.crt_signed(residues), expected)
        self.assertEqual(matrix, original)

    @unittest.skipIf(solver._numpy is None, 'NumPy optional backend unavailable')
    def test_int64_guard_and_unsafe_prime_fallback(self):
        matrix = solver.create_matrix(32, 2026, -9, 9)
        self.assertTrue(solver.numpy_safe_prime(3037000500))
        self.assertFalse(solver.numpy_safe_prime(3037000501))
        unsafe_prime = 4294967291
        self.assertEqual(solver.math_backend(matrix, unsafe_prime), 'python_integer')
        self.assertEqual(solver.det_mod(matrix, unsafe_prime),
                         determinant_bareiss(matrix) % unsafe_prime)
        with self.assertRaises(ValueError):
            solver.det_mod_numpy(matrix, unsafe_prime)


if __name__ == '__main__':
    unittest.main()
