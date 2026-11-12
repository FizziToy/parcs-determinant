"""Summarize actual PARCS output files; never generates fake cloud results."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, default=Path('outputs'))
    parser.add_argument('--out', type=Path, default=Path('results.csv'))
    args = parser.parse_args()
    rows = []
    expected = {}
    for path in sorted(args.inputs.glob('*.txt')):
        data = json.loads(path.read_text(encoding='utf-8'))
        if not data['correct']:
            raise RuntimeError('A run reported incorrect result: ' + str(path))
        n = data['size']
        if n in expected and expected[n] != data['determinant']:
            raise RuntimeError('Different determinants for same size: ' + str(path))
        expected[n] = data['determinant']
        rows.append({
            'file': path.name, 'n': n, 'workers': data['workers'],
            'primes': data['prime_count'], 'T_seq_s': round(data['sequential_median_s'], 4),
            'T_parallel_s': round(data['parallel_median_s'], 4),
            'speedup': round(data['speedup'], 4),
            'efficiency': round(data['efficiency'], 4), 'correct': data['correct']})
    if not rows:
        raise SystemExit('No .txt output files in outputs/. Download them from PARCS first.')
    cols = ['file', 'n', 'workers', 'primes', 'T_seq_s', 'T_parallel_s',
            'speedup', 'efficiency', 'correct']
    with args.out.open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
    print('Saved', args.out, 'from', len(rows), 'genuine experiment files')
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print('Optional charts: pip install matplotlib')
        return
    for metric, label, filename in [
        ('T_parallel_s', 'Parallel execution time, s', 'times.png'),
        ('speedup', 'Speedup T_seq / T_parallel', 'speedup.png'),
        ('efficiency', 'Efficiency = speedup / workers', 'efficiency.png')]:
        fig, ax = plt.subplots(figsize=(8, 5))
        for size in sorted({r['n'] for r in rows}):
            points = sorted((r for r in rows if r['n'] == size), key=lambda r: r['workers'])
            ax.plot([p['workers'] for p in points], [p[metric] for p in points],
                    marker='o', label=f'n = {size}')
        ax.set_xlabel('Number of workers')
        ax.set_ylabel(label)
        ax.set_xticks(sorted({r['workers'] for r in rows}))
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(filename, dpi=180)
        plt.close(fig)
        print('Saved', filename)


if __name__ == '__main__':
    main()
