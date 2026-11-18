"""Build one self-contained solver.py for the PARCS web uploader.

Usage: python3 build_solver.py
Edit src/*.py; do not edit the generated solver.py directly.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = ['matrix_math.py', 'parallel.py', 'measurements.py', 'solver_main.py']
HEADER = '''# -*- coding: utf-8 -*-
"""Generated PARCS entry point. Edit src/*.py, then run build_solver.py.

Map: workers calculate determinants modulo different primes.
Reduce: master reconstructs the exact determinant with CRT.
"""
from __future__ import print_function

'''

sections = [HEADER]
for filename in SOURCES:
    source = (ROOT / 'src' / filename).read_text(encoding='utf-8')
    sections.append('\n\n# ===== src/%s =====\n\n%s\n' % (filename, source))

output = ROOT / 'solver.py'
output.write_text(''.join(sections), encoding='utf-8')
print('Created %s' % output)
