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
