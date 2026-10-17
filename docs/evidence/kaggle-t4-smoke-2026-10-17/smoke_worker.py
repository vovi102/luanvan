"""Operational non-test T4 probe using unchanged native CLI17; never evaluate test data."""
import argparse
import hashlib
import importlib.metadata
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TRAINING_SHA = 'b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835'
MODEL_REVISION = '8afb486c1db24fe5011ec46dfbe5b5dccdb575c2'
ENCODER_REVISION = '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
NATIVE_CAP_SECONDS = 300
SMOKE_CAP_SECONDS = 1800


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, payload):
    if path.exists():
        raise ValueError('Refuse to overwrite existing smoke evidence: ' + str(path))
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n')


def select_cases(training_bytes):
    if hashlib.sha256(training_bytes).hexdigest() != TRAINING_SHA:
        raise ValueError('Accepted training fingerprint mismatch')
    rows = [json.loads(line) for line in training_bytes.decode().splitlines()]
    selected = []
    families = set()
    for language in ('en', 'vi', 'en', 'vi', 'en'):
        row = next(r for r in rows if r['split'] == 'train' and r['language'] == language and r['semantic_family_id'] not in families)
        selected.append({key: row[key] for key in ('id', 'language', 'semantic_family_id', 'question', 'record_sha256')})
        families.add(row['semantic_family_id'])
    return selected


def as_text(value):
    return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--hf-home', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--campaign', required=True)
    args = parser.parse_args()
    root, output = args.root, args.output
    output.mkdir(parents=True, exist_ok=False)
    started = utc()
    summary = {'mode': 'non_test_train_smoke', 'campaign_id': args.campaign, 'started_at': started,
               'status': 'blocked', 'scientific_ready': False, 'benchmark_evaluation': False,
               'training_sha256': TRAINING_SHA, 'model_revision': MODEL_REVISION,
               'encoder_revision': ENCODER_REVISION, 'native_cap_seconds': NATIVE_CAP_SECONDS,
               'smoke_cap_seconds': SMOKE_CAP_SECONDS, 'cases': [], 'processes': []}
    try:
        from nl2sparql.kaggle.bundle import preflight_data
        from nl2sparql.kaggle.runner import offline_environment, preflight_runtime, probe_hardware
        from nl2sparql.models.b12.retrieval import validate_training_snapshot
        training = root / 'data/dataset/processed/b2-training.jsonl'
        data = training.read_bytes()
        records, digest = validate_training_snapshot(data, accepted_training_sha256=TRAINING_SHA)
        if len(records) != 7208 or digest != TRAINING_SHA:
            raise ValueError('Training authority mismatch')
        cases = select_cases(data)
        summary['cases'] = cases
        write_json(output / 'smoke-cases.json', {'selection': 'First matching rows in accepted train order, alternating EN/VI, distinct families, fixed before generation', 'cases': cases, 'training_sha256': TRAINING_SHA})
        config = json.loads((root / 'configs/kaggle-b12-run.template.json').read_bytes())
        config.update(campaign_id=args.campaign, language='en', model_revision=MODEL_REVISION,
                      encoder_revision=ENCODER_REVISION, hf_home=str(args.hf_home), run_timeout_seconds=NATIVE_CAP_SECONDS)
        write_json(output / 'runtime-config.json', config)
        data_check = preflight_data(root)
        write_json(output / 'data-preflight.json', data_check)
        if data_check['status'] != 'data_ready':
            raise ValueError('Data preflight blocked')
        runtime_check = preflight_runtime(root, config, output)
        write_json(output / 'runtime-preflight.json', runtime_check)
        if runtime_check['status'] != 'ready':
            raise ValueError('Runtime preflight blocked: ' + '; '.join(runtime_check['blockers']))
        write_json(output / 'packages.json', sorted((d.metadata['Name'], d.version) for d in importlib.metadata.distributions()))
        hardware = probe_hardware()
        write_json(output / 'hardware.json', hardware)
        print('Actual hardware:', hardware, flush=True)
        child_env = offline_environment(root, config)
        begin = time.monotonic()
        for baseline in ('b1', 'b2'):
            for index, case in enumerate(cases, 1):
                remaining = SMOKE_CAP_SECONDS - (time.monotonic() - begin)
                if remaining <= 0:
                    raise TimeoutError('Smoke wall-time budget exhausted')
                folder = output / f'{baseline}-case-{index:02d}'
                folder.mkdir()
                argv = [sys.executable, str(root / 'scripts/17_small_llm_baselines.py'), 'predict',
                        '--baseline', baseline, '--question', case['question'], '--model-revision', MODEL_REVISION,
                        '--catalog', str(root / 'src/nl2sparql/sql/catalog/ethereum_analytics.json'),
                        '--training', str(training), '--cache', str(output / 'cache/b2-few-shot.npz'),
                        '--encoder-id', 'sentence-transformers/all-MiniLM-L6-v2', '--encoder-revision', ENCODER_REVISION,
                        '--accepted-training-sha256', TRAINING_SHA, '--target-id', case['id'], '--real-inference']
                record = {'baseline': baseline, 'case_id': case['id'], 'language': case['language'],
                          'argv': argv, 'started_at': utc(), 'timeout_seconds': min(NATIVE_CAP_SECONDS, remaining)}
                print('Starting', baseline, case['id'], flush=True)
                tick = time.monotonic()
                try:
                    process = subprocess.run(argv, env=child_env, text=True, capture_output=True, timeout=record['timeout_seconds'])
                    stdout, stderr, code = process.stdout, process.stderr, process.returncode
                except subprocess.TimeoutExpired as exc:
                    stdout, stderr, code = as_text(exc.stdout), as_text(exc.stderr), 124
                    record['timed_out'] = True
                (folder / 'native-stdout.json').write_text(stdout)
                (folder / 'native-stderr.log').write_text(stderr)
                record.update(exit_code=code, finished_at=utc(), wall_seconds=time.monotonic() - tick)
                try:
                    payload = json.loads(stdout)
                except (ValueError, TypeError):
                    payload = {'status': 'unparseable_native_stdout'}
                record['native_status'] = payload.get('status')
                if payload.get('status') == 'ready':
                    prediction = payload['prediction']
                    if prediction['completion']['synthetic_backend'] is not False:
                        raise ValueError('Non-genuine completion marker in smoke')
                    record.update(latency_ms=prediction['latency_ms'], extraction_status=prediction['extraction_status'],
                                  model_revision=prediction['completion']['model_revision'],
                                  synthetic_backend=prediction['completion']['synthetic_backend'])
                else:
                    record['error'] = payload.get('error', payload.get('status'))
                write_json(folder / 'process.json', record)
                summary['processes'].append(record)
                print('Finished', baseline, case['id'], 'exit', code, 'native status', payload.get('status'), flush=True)
                if code != 0 or payload.get('status') != 'ready':
                    raise RuntimeError(str(record.get('error', 'Native prediction failed')))
        summary['status'] = 'passed'
        summary['latency_observations'] = {
            baseline: {'cases': 5, 'median_ms': statistics.median(r['latency_ms'] for r in summary['processes'] if r['baseline'] == baseline),
                       'max_ms': max(r['latency_ms'] for r in summary['processes'] if r['baseline'] == baseline)}
            for baseline in ('b1', 'b2')}
    except Exception as exc:
        summary['error_type'] = type(exc).__name__
        summary['error'] = str(exc)
        print('Smoke blocked:', type(exc).__name__, str(exc), flush=True)
    finally:
        summary['finished_at'] = utc()
        write_json(output / 'smoke-summary.json', summary)
        files = {str(p.relative_to(output)): {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                 for p in output.rglob('*') if p.is_file()}
        write_json(output / 'smoke-artifacts-manifest.json', files)
    return 0 if summary['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
