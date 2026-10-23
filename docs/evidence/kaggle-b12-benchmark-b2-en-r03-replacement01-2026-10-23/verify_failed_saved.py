"""Offline audit of genuine saved setup failure, never a native completeness receipt."""
import hashlib
import json
from pathlib import Path

base = Path(__file__).resolve().parent
read = lambda p: json.loads(p.read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
plan = read(base / 'submission-plan-short-ref.json')
output = base / 'downloaded' / ('b12-benchmark-' + plan['campaign_id'])
session = output / ('session-' + plan['session_id'])
manifest = read(session / 'artifacts-manifest.json')
for name, entry in manifest.items():
    p = output / name
    assert p.resolve().is_relative_to(output.resolve())
    assert p.is_file() and not p.is_symlink()
    assert p.stat().st_size == entry['bytes'] and sha(p) == entry['sha256']
files = sorted(p for p in output.rglob('*') if p.is_file())
assert set(str(p.relative_to(output)) for p in files) == set(manifest) | {str((session / 'artifacts-manifest.json').relative_to(output))}
download = read(base / 'download-record.json')
assert download['worker_status'] == 'ERROR' and download['omitted'] == []
assert len(files) == len(download['downloaded']) == 8
assert sum(p.stat().st_size for p in files) == 14146
summary = read(session / 'driver-summary.json')
assert summary['status'] == 'failed'
assert summary['error_type'] == 'TimeoutExpired'
assert summary['stage'] == 'verify_mounted_cache'
assert summary['scratch_removed'] is True
assert (summary['setup_cap_seconds'], summary['process_cap_seconds'], summary['session_cap_seconds']) == (1620,5400,7200)
assert summary['settings'] == read(base / 'settings.json')
assert 1620 <= summary['wall_seconds'] < 1621
assert (session / 'verify_mounted_cache.log').stat().st_size == 0
assert not (output / 'runs').exists()
for name in ['worker.log','benchmark-driver.py','settings.json','campaign-ledger.json','completeness.json','run-config.json','data-preflight.json','runtime-preflight.json']:
    assert not (session / name).exists(), name
for name in ['run.json','predictions.jsonl','native-log.jsonl','native-report.json']:
    assert not list(output.rglob(name)), name
provenance = read(session / 'input-provenance.json')
assert provenance['bundle_sha256'] == '2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de'
assert provenance['cache_inventory_sha256'] == 'ae3b7dc2361f151bcc59d68f4b2ddcdef74b99a5fe8374b041190bded84d84f1'
assert provenance['weights_copied'] is False and provenance['cache_version'] == 5
assert provenance['payload_files'] == 181 and provenance['tar_members'] == 182
stages = [json.loads(s) for s in (session / 'stage-timings.jsonl').read_text().splitlines()]
assert len(stages) == 8
expected = ['install_bootstrap','create_python311','install_locked_environment','verify_mounted_cache']
for i, name in enumerate(expected):
    start, finish = stages[2*i:2*i+2]
    assert start['stage'] == finish['stage'] == name
    assert start['event'] == 'started' and finish['event'] == 'finished'
    assert start['budget'] == finish['budget'] == 'setup'
    assert finish['outcome'] == ('timed_out' if i == 3 else 'completed')
assert stages[-1]['error_type'] == 'TimeoutExpired'
assert stages[-1]['budget_remaining_seconds'] == 0
assert stages[-1]['elapsed_seconds'] >= stages[-1]['timeout_seconds']
assert 'Installed 218 packages' in (session / 'install_locked_environment.log').read_text()
result = dict(status='setup_timeout_saved_artifacts_integrity_verified',
    kernel=plan['kernel'], version=1, run_id=plan['run_id'], replacement_of=plan['replacement_of'],
    session_id=plan['session_id'], native_inference_started=False, cases_generated=0,
    failure_stage=summary['stage'], error_type=summary['error_type'],
    driver_wall_seconds=summary['wall_seconds'], setup_cap_seconds=1620,native_cap_seconds=5400,session_cap_seconds=7200,
    setup_stage_timings=[dict(stage=stages[i]['stage'],elapsed_seconds=stages[i]['elapsed_seconds'],outcome=stages[i]['outcome']) for i in [1,3,5,7]],
    cache_timeout_seconds=stages[-1]['timeout_seconds'],cache_log_bytes=0,
    cache_verification_complete=False, cache_corruption_established=False,
    underlying_cache_slowness_cause='not established; no per-file or byte-progress telemetry',
    scratch_removed=True,saved_files_verified=8,saved_bytes_verified=14146,native_manifest_entries_verified=len(manifest),
    native_ledger_published=False,native_completeness_receipt_published=False,
    scientific_ready=False,accuracy_assessed=False,new_bigquery_jobs=0,automatic_retry_performed=False,
    attempt_id_must_not_be_reused=True)
(base / 'verified-failure-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
