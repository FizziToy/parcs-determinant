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
