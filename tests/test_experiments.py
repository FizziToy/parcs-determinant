"""Validate experiment provenance and the real PARCS HTML/form contract locally."""
import hashlib
import io
import json
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from analyze_experiments import collect_run
from run_cloud_experiments import multipart, parse_jobs, validate_output, EXECUTION_MODEL, TIMING_BASELINE
import run_cloud_experiments


def fixture_output():
    # Deliberate test fixture in a TemporaryDirectory, never an experiment result.
    return dict(correct=True, size=128, workers=2, repetitions=3, registered_workers=4,
                execution_model=EXECUTION_MODEL, timing_baseline=TIMING_BASELINE,
                matrix_config=dict(seed=2026), prime_count=26, determinant='-2',
                sequential_times_s=[3., 2., 4.], parallel_times_s=[2., 1., 3.])


class ExperimentTests(unittest.TestCase):
    def test_submit_collect_and_resume_without_duplicate_post(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'outputs').mkdir()
            code = root / 'solver.py'
            code.write_bytes(b'# local protocol fixture only\n')
            config = dict(size=128, workers=2, repetitions=3, seed=2026)
            (root / 'input.json').write_text(json.dumps(config))
            manifest = dict(execution_model=EXECUTION_MODEL, timing_baseline=TIMING_BASELINE,
                            solver_sha256=hashlib.sha256(code.read_bytes()).hexdigest(), jobs=[
                dict(name='N128_W2', config=config, input='input.json', output='outputs/N128_W2.json')])
            (root / 'manifest.json').write_text(json.dumps(manifest))
            state = dict(name=None, posts=0)

            def fake_urlopen(request, timeout):
                path = request.full_url.replace('http://127.0.0.1:8080', '')
                if path == '/api/worker':
                    return io.BytesIO(json.dumps(dict(workers=[dict(enabled=True)]*4)).encode())
                if path == '/api/job' and request.data:
                    state['posts'] += 1
                    state['name'] = re.search(b'name="job_name"\r\n\r\n([^\r]+)', request.data)[1].decode()
                    return io.BytesIO(b'Added')
                if path == '/jobs':
                    page = '' if state['name'] is None else (
                        '<div class="job-well" data-job-id="7"><div>%s</div>'
                        '<a href="/api/job/7/output">Output</a></div>' % state['name'])
                    return io.BytesIO(page.encode())
                if path == '/api/job/7/output':
                    return io.BytesIO(json.dumps(fixture_output()).encode())
                if path == '/api/job/7/solution':
                    return io.BytesIO(code.read_bytes())
                if path == '/api/job/7/input':
                    return io.BytesIO(json.dumps(config).encode())
                raise AssertionError('Unexpected request ' + path)

            argv = ['runner', '--run', str(root), '--solver', str(code)]
            with patch.object(run_cloud_experiments, 'urlopen', fake_urlopen):
                with patch.object(sys, 'argv', argv):
                    run_cloud_experiments.main()
                payload = (root / 'outputs/N128_W2.json').read_bytes()
                with patch.object(sys, 'argv', argv + ['--resume']):
                    run_cloud_experiments.main()
            self.assertEqual(state['posts'], 1)
            self.assertEqual((root / 'outputs/N128_W2.json').read_bytes(), payload)
            summary, _ = collect_run(root)
            self.assertEqual(summary[0]['status'], 'completed')

    def test_parcs_jobs_html_ready_running_and_failed(self):
        page = '''<div class="well job-well img-rounded" data-job-id="4">
          <div><span>OPT_TEST</span></div><a href="/api/job/4/output">Output</a></div>
          <div class="well job-well" data-job-id="5"><div>Pending</div>
          <a href="/api/job/5/output" disabled>Output</a></div>
          <div class="job-well well" data-job-id="6"><div>
          <span class="error-text">FAILED [reason: test]</span></div></div>'''
        jobs = parse_jobs(page)
        self.assertEqual(set(jobs), {4, 5, 6})
        self.assertTrue(jobs[4]['output_ready'])
        self.assertFalse(jobs[5]['output_ready'])
        self.assertTrue(jobs[6]['failed'])
        self.assertIn('OPT_TEST', jobs[4]['text'])

    def test_multipart_matches_public_parcs_form_names(self):
        with tempfile.TemporaryDirectory() as folder:
            code = Path(folder) / 'solver.py'
            config = Path(folder) / 'input.json'
            code.write_bytes(b'# test code\n')
            config.write_bytes(b'{"size":128}')
            body, content_type = multipart('OPT_TEST', code, config)
            for field in (b'name="job_name"', b'name="solution_file"', b'name="input_file"'):
                self.assertIn(field, body)
            self.assertIn(code.read_bytes(), body)
            self.assertIn(config.read_bytes(), body)
            boundary = content_type.split('boundary=')[1].encode()
            self.assertTrue(body.endswith(b'--' + boundary + b'--\r\n'))

    def test_reject_wrong_configuration_and_nonfinite_times(self):
        config = dict(size=128, workers=2, repetitions=3, seed=2026)
        for key, value in [('size', 256), ('workers', 1), ('correct', False),
                           ('execution_model', 'master_computes'), ('timing_baseline', 'local_master')]:
            data = fixture_output()
            data[key] = value
            with self.assertRaises(ValueError):
                validate_output(data, config)
        for bad in (float('nan'), float('inf'), 0, -2, True):
            data = fixture_output()
            data['parallel_times_s'][0] = bad
            with self.assertRaises(ValueError):
                validate_output(data, config)

    def test_missing_data_is_empty_and_verified_data_uses_raw_medians(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = dict(size=128, workers=2, repetitions=3, seed=2026)
            manifest = dict(execution_model=EXECUTION_MODEL, timing_baseline=TIMING_BASELINE,
                            solver_sha256='fixture-code-hash', jobs=[
                dict(name='N128_W2', config=config, output='test.json')])
            (root / 'manifest.json').write_text(json.dumps(manifest))
            summary, raw = collect_run(root)
            self.assertEqual(summary[0]['status'], 'not_run')
            self.assertIsNone(summary[0]['parallel_median_s'])
            self.assertEqual(len(raw), 3)
            data = fixture_output()
            payload = json.dumps(data).encode()
            (root / 'test.json').write_bytes(payload)
            provenance = dict(config=config, solver_sha256='fixture-code-hash',
                              output_sha256=hashlib.sha256(payload).hexdigest(), source='parcs_http_api')
            (root / 'test.provenance.json').write_text(json.dumps(provenance))
            summary, raw = collect_run(root)
            self.assertEqual(summary[0]['sequential_median_s'], 3.)
            self.assertEqual(summary[0]['parallel_median_s'], 2.)
            self.assertEqual(summary[0]['speedup'], 1.5)
            self.assertEqual(summary[0]['efficiency'], .75)
            provenance['solver_sha256'] = 'old-algorithm'
            (root / 'test.provenance.json').write_text(json.dumps(provenance))
            with self.assertRaises(ValueError):
                collect_run(root)


if __name__ == '__main__':
    unittest.main()
