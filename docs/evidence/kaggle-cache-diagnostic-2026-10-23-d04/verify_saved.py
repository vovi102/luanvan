"""Terminal-only offline diagnostic audit; never a benchmark completeness receipt."""
import hashlib
import json
from pathlib import Path

base=Path(__file__).resolve().parent
root=base.parents[1]
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
output=base/'downloaded/cache-diagnostic-d01'
manifest=read(output/'artifacts-manifest.json')
for name,entry in manifest.items():
 p=output/name
 assert p.resolve().is_relative_to(output.resolve()) and p.is_file() and not p.is_symlink()
 assert p.stat().st_size==entry['bytes'] and sha(p)==entry['sha256']
files=[p for p in output.iterdir() if p.is_file()]
assert set(p.name for p in files)==set(manifest)|{'artifacts-manifest.json'}
assert read(base/'download-record.json')['omitted']==[]
plan=read(base/'submission-plan.json')
assert sha(output/'diagnostic-driver.py')==plan['driver_sha256']
settings=read(output/'diagnostic-settings.json')
summary=read(output/'diagnostic-summary.json')
assert settings['cpu_only'] and settings['diagnostic_only']
assert settings['verification_cap_seconds']==1620 and settings['platform_cap_seconds']==1800
assert not settings['inference'] and not settings['model_loaded'] and not settings['benchmark_attempt_reserved']
assert not summary['inference'] and not summary['model_loaded'] and not summary['benchmark_attempt_reserved']
assert not summary['scientific_ready']
assert summary['status'] in ('completed_cache_diagnostic','failed','timed_out')
provenance=read(output/'diagnostic-provenance.json') if (output/'diagnostic-provenance.json').exists() else None
pins=read(root/'configs/kaggle-b12-model-pins.json')
expected=[(kind+'/'+name,e['bytes']) for kind in ['model','encoder'] for name,e in pins['models'][kind]['files'].items()]
expected_bytes=sum(b for _,b in expected)
journal=output/'cache-progress.jsonl'
events=[json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []
starts=[e for e in events if e['event']=='file_started']
closes=[e for e in events if e['event']=='file_read_complete']
assert [e['file'] for e in starts]==[name for name,_ in expected[:len(starts)]]
assert all(b['elapsed_seconds']>=a['elapsed_seconds'] for a,b in zip(events,events[1:]))
assert all(b['total_bytes_read']>=a['total_bytes_read'] for a,b in zip(events,events[1:]))
receipt_path=output/'native-cache-receipt.json'
complete=summary['status']=='completed_cache_diagnostic'
if complete:
 assert summary['returncode']==0 and receipt_path.is_file() and provenance
 assert events[-1]['event']=='verification_completed'
 assert len(starts)==len(closes)==24
 assert events[-1]['total_bytes_read']==expected_bytes and events[-1]['files_read_complete']==24
 assert [(e['file'],e['file_bytes_read']) for e in closes]==expected
 receipt=read(receipt_path)
 assert receipt['status']=='cache_bytes_verified' and not receipt['model_loaded'] and not receipt['scientific_ready']
 assert set(receipt['models'])=={'model','encoder'}
 for kind in ['model','encoder']:
  assert receipt['models'][kind]['repo_id']==pins['models'][kind]['repo_id']
  assert receipt['models'][kind]['revision']==pins['models'][kind]['revision']
  assert receipt['models'][kind]['files_verified']==len(pins['models'][kind]['files'])
else:
 assert not receipt_path.exists()
 assert not any(e['event']=='verification_completed' for e in events)
if provenance:
 assert provenance['script_sha256']==plan['accepted_verifier_sha256']
 assert provenance['pins_sha256']==sha(root/'configs/kaggle-b12-model-pins.json')
 assert provenance['bundle_sha256']=='2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de'
 assert provenance['inventory_sha256']=='ae3b7dc2361f151bcc59d68f4b2ddcdef74b99a5fe8374b041190bded84d84f1'
 assert not provenance['inference'] and not provenance['model_loaded'] and not provenance['weights_copied']
for name in ['run.json','predictions.jsonl','native-report.json','campaign-ledger.json','completeness.json']:
 assert not list(output.rglob(name)),name
result=dict(status='terminal_cpu_diagnostic_artifacts_verified',diagnostic_outcome=summary['status'],
 cache_verification_complete=complete,saved_files_verified=len(files),manifest_entries_verified=len(manifest),
 saved_bytes_verified=sum(p.stat().st_size for p in files),driver_wall_seconds=summary['wall_seconds'],
 expected_files=24,expected_total_bytes=expected_bytes,files_read_started=len(starts),files_read_closed=len(closes),
 last_progress=events[-1] if events else None,
 per_file_read_observations=[{k:e[k] for k in ['file','expected_bytes','file_bytes_read','file_wall_seconds','read_wall_seconds','read_cpu_seconds','hash_and_loop_wall_seconds']} for e in closes],
 comparison_limit=plan['comparison_limit'],T4_setup_failure_resolved=False,
 model_loaded=False,benchmark_attempt_reserved=False,scientific_ready=False)
(base/'verified-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
