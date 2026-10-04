"""Run the public CLI with real model calls in fresh directories; never fabricate success.

These practice briefs are not the instructor's hidden assessment inputs.
All source acquisition, generation, repairs and browser checks remain inside agent.py.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / 'examples' / 'verification'


def code_digest():
    paths = [ROOT / 'agent.py', ROOT / 'requirements.txt', *sorted(
        p for p in (ROOT / 'playground').rglob('*') if p.is_file() and p.suffix in {'.py', '.js', '.css'})]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='deepseek/deepseek-v4.1-flash')
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--cases', nargs='+', default=[p.stem for p in sorted(CASES.glob('*.json'))])
    parser.add_argument('--output', type=Path, default=ROOT / 'out' / 'verification')
    parser.add_argument('--prompt-key', action='store_true', help='Prompt for a key with terminal echo disabled')
    args = parser.parse_args()
    if args.prompt_key:
        import getpass
        os.environ['OPENROUTER_API_KEY'] = getpass.getpass('OpenRouter key (hidden): ')
    if not os.environ.get('OPENROUTER_API_KEY'):
        parser.error('Set OPENROUTER_API_KEY in the environment; never pass a key on the command line.')
    if not 1 <= args.repeats <= 10 or any(not (CASES / (name + '.json')).is_file() or '/' in name or '\\' in name for name in args.cases):
        parser.error('Use 1..10 repeats and existing example case names.')
    session = args.output / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + os.urandom(3).hex())
    session.mkdir(parents=True, exist_ok=False)
    report = {'model': args.model, 'code_sha256': code_digest(),
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'note': 'Local Windows practice cases, not the original VPS assessment inputs.', 'runs': []}
    for name in args.cases:
        case_path = CASES / (name + '.json')
        for repetition in range(1, args.repeats + 1):
            destination = session / f'{name}-{repetition}'
            started = time.monotonic()
            run_digest = code_digest()
            print(f'Running {name}, attempt {repetition}, fresh output: {destination}', flush=True)
            command = [sys.executable, '-X', 'utf8', str(ROOT / 'agent.py'), '--input', str(case_path),
                       '--output', str(destination), '--model', args.model]
            try:
                process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                         encoding='utf-8', timeout=610)
                exit_code, stdout, stderr = process.returncode, process.stdout, process.stderr
            except subprocess.TimeoutExpired:
                exit_code, stdout, stderr = 124, '', 'Verification runner stopped a run exceeding 610 seconds.'
            elapsed = round(time.monotonic() - started, 3)
            destination.mkdir(parents=True, exist_ok=True)
            # Defense in depth: subprocess diagnostics must not expose credentials.
            key = os.environ['OPENROUTER_API_KEY']
            (destination / 'cli.log').write_text((stdout + stderr).replace(key, '[REDACTED]'), encoding='utf-8')
            trace = destination / 'trace.jsonl'
            events = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()] if trace.is_file() else []
            failures = [e['details'] for e in events if e['action'] == 'failure']
            calls = sum(e['stage'] == 'model' and e['action'] == 'request' and e['result'] == 'started' for e in events)
            prompt = sum(e.get('prompt_tokens', 0) for e in events)
            completion = sum(e.get('completion_tokens', 0) for e in events)
            checks = {e['stage']: e['result'] for e in events if e['stage'] in {'STATIC_VALIDATION', 'BROWSER_VALIDATION', 'FINALIZE'}}
            usable = exit_code == 0 and (destination / 'index.html').is_file()
            row = {'case': name, 'repeat': repetition, 'input': json.loads(case_path.read_text(encoding='utf-8')),
                   'code_sha256': run_digest, 'code_changed_during_run': code_digest() != run_digest,
                   'exit_code': exit_code, 'html_produced': usable, 'elapsed_seconds': elapsed, 'calls': calls,
                   'prompt_tokens': prompt, 'completion_tokens': completion, 'checks': checks,
                   'failures': failures, 'output': destination.relative_to(ROOT).as_posix()}
            report['runs'].append(row)
            report['finished_utc'] = datetime.now(timezone.utc).isoformat()
            (session / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps({k: row[k] for k in ('case', 'repeat', 'exit_code', 'html_produced', 'elapsed_seconds', 'calls', 'completion_tokens', 'checks')}), flush=True)
            if failures:
                print(json.dumps(failures[-1]), flush=True)
    print(f'Results: {session / "results.json"}', flush=True)
    return 0 if all(r['html_produced'] for r in report['runs']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
