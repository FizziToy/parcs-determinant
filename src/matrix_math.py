"""Exact matrix determinant: modular Gaussian elimination and CRT."""
import random

try:
    import numpy as _numpy
except ImportError:
    _numpy = None

try:
    from itertools import izip as _zip
except ImportError:
    _zip = zip

MAX_MATRIX_SIZE = 512
NUMPY_MIN_SIZE = 32
INT64_MAX = (1 << 63) - 1


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
    if not 1 <= size <= MAX_MATRIX_SIZE or low > high:
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


def det_mod_python(matrix, prime):
    """Exact Gaussian elimination using Python integers, without dependencies.

    Cache the pivot tail and update active row tails in a list comprehension.
    This avoids repeated matrix lookups in the cubic inner loop.
    """
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
        if col == size - 1:
            break
        inverse = pow(pivot, prime - 2, prime)
        pivot_tail = rows[col][col + 1:]

        for i in range(col + 1, size):
            row = rows[i]
            if row[col] == 0:
                continue
            factor = row[col] * inverse % prime
            row[col] = 0
            row[col + 1:] = [(value - factor * pivot_value) % prime
                            for value, pivot_value in _zip(row[col + 1:], pivot_tail)]

    return result % prime


def numpy_safe_prime(prime):
    """Maximum intermediate is (p-1)^2 + (p-1) = p*(p-1)."""
    return 2 <= prime and prime * (prime - 1) <= INT64_MAX


def det_mod_numpy(matrix, prime):
    """Same elimination with exact int64 outer products, never floating point.

    Each update adds a nonnegative multiple of the pivot row and immediately
    reduces modulo p. The guard proves that no multiply or add can overflow.
    Input entries are reduced as Python integers BEFORE conversion to int64.
    """
    if _numpy is None:
        raise RuntimeError('NumPy is not installed')
    if not numpy_safe_prime(prime):
        raise ValueError('Prime is too large for exact int64 elimination')
    rows = _numpy.array([[value % prime for value in row] for row in matrix],
                        dtype=_numpy.int64)
    size = len(matrix)
    workspace = _numpy.empty((size, size), dtype=_numpy.int64)
    result = 1
    for col in range(size):
        pivot_row = col
        while pivot_row < size and rows[pivot_row, col] == 0:
            pivot_row += 1
        if pivot_row == size:
            return 0
        if pivot_row != col:
            rows[[col, pivot_row], :] = rows[[pivot_row, col], :]
            result = -result
        pivot = int(rows[col, col])
        result = result * pivot % prime
        if col == size - 1:
            break
        inverse = pow(pivot, prime - 2, prime)
        # Use addition so all intermediates stay between 0 and p*(p-1).
        factors = (rows[col + 1:, col] * (prime - inverse)) % prime
        if not _numpy.any(factors):
            continue
        tail = rows[col + 1:, col + 1:]
        scratch = workspace[:size - col - 1, :size - col - 1]
        _numpy.multiply(factors[:, None], rows[col, col + 1:], out=scratch)
        _numpy.add(tail, scratch, out=tail)
        _numpy.remainder(tail, prime, out=tail)
        rows[col + 1:, col] = 0
    return result % prime


def math_backend(matrix, prime):
    """Return the selected kernel; small/unsupported cases use Python integers."""
    if (_numpy is not None and len(matrix) >= NUMPY_MIN_SIZE
            and numpy_safe_prime(prime)):
        return 'numpy_int64'
    return 'python_integer'


def det_mod(matrix, prime):
    """Compute det(A) modulo a prime, selecting an exact available kernel."""
    if math_backend(matrix, prime) == 'numpy_int64':
        return det_mod_numpy(matrix, prime)
    return det_mod_python(matrix, prime)


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


def det_exact_local(matrix, primes):
    """Offline helper for tests/local kernel benchmarks; never called by Master."""
    return crt_signed([(prime, det_mod(matrix, prime)) for prime in primes])
