"""Submit and collect PARCS jobs through an existing local SSH tunnel.

Uses the public routes/form fields in Hummer12007/parcs-python at 00c5399.
No VM creation, deletion, worker enabling/disabling, or job cancellation.
"""
import argparse
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

EXECUTION_MODEL = 'workers_only'
TIMING_BASELINE = 'one_remote_worker_including_rpc_and_reduce'


class JobsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.jobs = {}
        self.current = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if tag == 'div':
            if self.current is None and 'job-well' in classes:
                self.current = dict(id=int(attrs['data-job-id']), text='',
                                    failed=False, output_ready=False)
                self.depth = 0
            if self.current is not None:
                self.depth += 1
        if self.current is not None:
            if 'error-text' in classes:
                self.current['failed'] = True
            if tag == 'a' and attrs.get('href', '').endswith('/output'):
                self.current['output_ready'] = 'disabled' not in attrs

    def handle_endtag(self, tag):
        if tag == 'div' and self.current is not None:
            self.depth -= 1
            if self.depth == 0:
                self.jobs[self.current['id']] = self.current
                self.current = None

    def handle_data(self, data):
        if self.current is not None:
            self.current['text'] += data + ' '


def parse_jobs(page):
    parser = JobsParser()
    parser.feed(page)
    return parser.jobs


def multipart(job_name, solver_path, input_path):
    boundary = 'parcs-' + uuid.uuid4().hex
    parts = []
    for name, filename, content in [
        ('job_name', None, job_name.encode()),
        ('solution_file', 'solver.py', solver_path.read_bytes()),
        ('input_file', input_path.name, input_path.read_bytes()),
    ]:
        header = '--' + boundary + '\r\nContent-Disposition: form-data; name="' + name + '"'
        if filename:
            header += '; filename="' + filename + '"'
        parts.extend([header.encode() + b'\r\n\r\n', content, b'\r\n'])
    parts.append(('--' + boundary + '--\r\n').encode())
    return b''.join(parts), 'multipart/form-data; boundary=' + boundary


def validate_output(data, config):
    if (data.get('execution_model') != EXECUTION_MODEL
            or data.get('timing_baseline') != TIMING_BASELINE):
        raise ValueError('Output uses a different execution model or timing baseline')
    if data.get('correct') is not True:
        raise ValueError('PARCS did not confirm correct=True')
    for key in ('size', 'workers', 'repetitions'):
        if data.get(key) != config[key]:
            raise ValueError('Output configuration mismatch: ' + key)
    if data.get('registered_workers', 0) < config['workers']:
        raise ValueError('Insufficient registered workers in output')
    if data.get('matrix_config', {}).get('seed') != config['seed']:
        raise ValueError('Output seed differs')
    for key in ('sequential_times_s', 'parallel_times_s'):
        values = data.get(key, [])
        if len(values) != config['repetitions']:
            raise ValueError('Wrong repetition count')
        if any(isinstance(v, bool) or not isinstance(v, (float, int))
               or not 0 < v < float('inf') for v in values):
            raise ValueError('Invalid timing')
    int(data['determinant'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--solver', type=Path, default=Path('solver.py'))
    parser.add_argument('--url', default='http://127.0.0.1:8080')
    parser.add_argument('--timeout', type=float, default=21600,
                        help='Per job in seconds; timeout leaves remote job untouched')
    parser.add_argument('--poll', type=float, default=5)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--resume', action='store_true',
                        help='Verify saved outputs and recover recorded submissions without resubmitting')
    args = parser.parse_args()
    manifest = json.loads((args.run / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('execution_model') != EXECUTION_MODEL
            or manifest.get('timing_baseline') != TIMING_BASELINE):
        raise SystemExit('Prepare a fresh workers-only plan; the old baseline is incompatible.')
    code_hash = hashlib.sha256(args.solver.read_bytes()).hexdigest()
    if code_hash != manifest['solver_sha256']:
        raise SystemExit('solver.py differs from the frozen manifest. Prepare a new run directory.')
    base = args.url.rstrip('/')

    def request(path, data=None, content_type=None):
        headers = {'Content-Type': content_type} if content_type else {}
        with urlopen(Request(base + path, data=data, headers=headers), timeout=30) as response:
            return response.read()

    workers = json.loads(request('/api/worker'))['workers']
    print('PARCS endpoint reachable; worker records:', len(workers), flush=True)
    if sum(w.get('enabled', False) for w in workers) < 4:
        raise SystemExit('This 12-job plan requires four enabled registered workers. Check /workers.')
    if args.check_only:
        return
    recorded_names = []
    if args.resume:
        for path in (args.run / 'outputs').glob('*.submission.json'):
            recorded_names.append(json.loads(path.read_text(encoding='utf-8'))['job_name'])
    if any(not j['failed'] and not j['output_ready']
           and not any(name in j['text'] for name in recorded_names)
           for j in parse_jobs(request('/jobs').decode('utf-8')).values()):
        raise SystemExit('A PARCS job is already pending/running. Wait before starting this plan.')
    for spec in manifest['jobs']:
        output_path = args.run / spec['output']
        provenance_path = output_path.with_suffix('.provenance.json')
        submission_path = output_path.with_suffix('.submission.json')
        if output_path.exists():
            if not args.resume:
                raise SystemExit('Output exists; preserved: %s. Use --resume or a new run directory.' % output_path)
            payload = output_path.read_bytes()
            validate_output(json.loads(payload), spec['config'])
            provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
            if (provenance.get('solver_sha256') != code_hash
                    or provenance.get('output_sha256') != hashlib.sha256(payload).hexdigest()
                    or provenance.get('config') != spec['config']
                    or provenance.get('source') != 'parcs_http_api'):
                raise RuntimeError('Saved output provenance differs from this plan')
            print('Preserved verified result', spec['name'], flush=True)
            continue
        if submission_path.exists() and not args.resume:
            raise SystemExit('Submission already exists: %s. Recover that job manually before rerunning.' %
                             submission_path)
        if submission_path.exists():
            submission = json.loads(submission_path.read_text(encoding='utf-8'))
            if submission['solver_sha256'] != code_hash or submission['config'] != spec['config']:
                raise RuntimeError('Recorded submission differs from this plan')
            token = submission['job_name']
        else:
            token = 'DET_' + spec['name'][1:]
            submission = dict(job_name=token, config=spec['config'], solver_sha256=code_hash,
                              submitted_utc=datetime.now(timezone.utc).isoformat(),
                              status='submission_intent_recorded')
            # Record intent BEFORE POST. Never retry an ambiguous POST automatically.
            with submission_path.open('x', encoding='utf-8') as handle:
                json.dump(submission, handle, indent=2)
            body, content_type = multipart(token, args.solver, args.run / spec['input'])
            request('/api/job', body, content_type)
        jobs = parse_jobs(request('/jobs').decode('utf-8'))
        matches = [job for job in jobs.values() if token.lower() in job['text'].lower()]
        if len(matches) != 1:
            raise RuntimeError('Could not identify submitted job. Inspect /jobs; do not resubmit blindly.')
        job_id = matches[0]['id']
        print('Submitted', token, 'id=', job_id, flush=True)
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            jobs = parse_jobs(request('/jobs').decode('utf-8'))
            job = jobs.get(job_id)
            if job is None:
                raise RuntimeError('Job disappeared; inspect PARCS before submitting more work')
            if job['failed']:
                raise RuntimeError('PARCS job failed: ' + job['text'].strip())
            if job['output_ready']:
                payload = request('/api/job/%d/output' % job_id)
                data = json.loads(payload)
                validate_output(data, spec['config'])
                remote_code = request('/api/job/%d/solution' % job_id)
                remote_input = json.loads(request('/api/job/%d/input' % job_id))
                if hashlib.sha256(remote_code).hexdigest() != code_hash:
                    raise RuntimeError('Downloaded solution differs from the submitted solver')
                if remote_input != spec['config']:
                    raise RuntimeError('Downloaded input differs from the plan')
                with output_path.open('xb') as handle:
                    handle.write(payload)
                provenance = dict(submission, job_id=job_id, status='completed',
                                  source='parcs_http_api',
                                  output_sha256=hashlib.sha256(payload).hexdigest(),
                                  downloaded_utc=datetime.now(timezone.utc).isoformat())
                with provenance_path.open('x', encoding='utf-8') as handle:
                    json.dump(provenance, handle, indent=2)
                print('Collected', spec['name'], flush=True)
                break
            time.sleep(args.poll)
        else:
            raise TimeoutError('Job %d is still pending. It was NOT cancelled; inspect /jobs.' % job_id)


if __name__ == '__main__':
    main()
