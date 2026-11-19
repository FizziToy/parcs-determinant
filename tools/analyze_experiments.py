"""Export only verified outputs from one optimized run; keep missing cells empty."""
import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path

from run_cloud_experiments import validate_output, EXECUTION_MODEL, TIMING_BASELINE


def collect_run(run):
    manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('execution_model') != EXECUTION_MODEL
            or manifest.get('timing_baseline') != TIMING_BASELINE):
        raise ValueError('Cannot mix the old master baseline with workers-only timings')
    summary, raw, expected = [], [], {}
    for job in manifest['jobs']:
        config = job['config']
        output_path = run / job['output']
        data = None
        if output_path.exists():
            payload = output_path.read_bytes()
            data = json.loads(payload)
            validate_output(data, config)
            provenance = json.loads(output_path.with_suffix('.provenance.json').read_text(encoding='utf-8'))
            if (provenance.get('solver_sha256') != manifest['solver_sha256']
                    or provenance.get('output_sha256') != hashlib.sha256(payload).hexdigest()
                    or provenance.get('config') != config
                    or provenance.get('source') != 'parcs_http_api'):
                raise ValueError('Unverified output provenance: ' + str(output_path))
            key = config['size']
            if key in expected and expected[key] != data['determinant']:
                raise ValueError('Different determinants for identical planned matrices')
            expected[key] = data['determinant']
        seq = statistics.median(data['sequential_times_s']) if data else None
        par = statistics.median(data['parallel_times_s']) if data else None
        speedup = seq / par if data else None
        row = dict(job=job['name'], size=config['size'], workers=config['workers'],
                   repetitions=config['repetitions'], seed=config['seed'],
                   status='completed' if data else 'not_run',
                   source='optimized_parcs' if data else 'missing',
                   timing_baseline=TIMING_BASELINE,
                   prime_count=data['prime_count'] if data else None,
                   sequential_median_s=seq, parallel_median_s=par,
                   speedup=speedup, efficiency=speedup / config['workers'] if data else None,
                   correct=True if data else None)
        summary.append(row)
        for repetition in range(config['repetitions']):
            raw.append(dict(job=job['name'], size=config['size'], workers=config['workers'],
                            seed=config['seed'], repetition=repetition + 1,
                            status=row['status'],
                            sequential_s=data['sequential_times_s'][repetition] if data else None,
                            parallel_s=data['parallel_times_s'][repetition] if data else None))
    return summary, raw


def write_csv(path, rows):
    with path.open('x', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_results(summary, out):
    # Optional on the user's Cloud Shell; report assets are prepared separately.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    complete = [row for row in summary if row['status'] == 'completed']
    for metric, label, filename in [
        ('parallel_median_s', 'Parallel time, s', 'time.png'),
        ('speedup', 'T_1_remote / T_parallel', 'speedup.png'),
        ('efficiency', 'Speedup / workers', 'efficiency.png'),
    ]:
        fig, ax = plt.subplots(figsize=(7, 4))
        for size in (128, 256, 512):
            points = sorted((r for r in complete if r['size'] == size), key=lambda r:r['workers'])
            if points:
                ax.plot([r['workers'] for r in points], [r[metric] for r in points],
                        marker='o', label='n=%d' % size)
        if complete:
            ax.legend()
        else:
            ax.text(.5, .5, 'No optimized PARCS measurements yet',
                    transform=ax.transAxes, ha='center')
        ax.set(xlabel='Workers', ylabel=label, xticks=[1, 2, 3, 4],
               title='Optimized solver only')
        ax.grid(alpha=.25)
        fig.tight_layout()
        fig.savefig(out / filename, dpi=180)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plots', action='store_true', help='Requires matplotlib')
    args = parser.parse_args()
    summary, raw = collect_run(args.run)
    args.out.mkdir(parents=True, exist_ok=False)
    write_csv(args.out / 'summary.csv', summary)
    write_csv(args.out / 'raw.csv', raw)
    if args.plots:
        plot_results(summary, args.out)
    print('Completed:', sum(r['status'] == 'completed' for r in summary),
          'Missing:', sum(r['status'] != 'completed' for r in summary))


if __name__ == '__main__':
    main()
