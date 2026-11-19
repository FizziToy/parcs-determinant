"""Benchmark helpers and output formatting."""
import time

_clock = getattr(time, 'perf_counter', time.time)


def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def measure(job):
    started = _clock()
    result = job()
    return result, _clock() - started


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
