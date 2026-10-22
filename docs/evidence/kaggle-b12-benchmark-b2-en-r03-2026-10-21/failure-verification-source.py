"""Read-only verification of a failed setup; no inference or retry."""
import hashlib,json
from pathlib import Path
base=Path(__file__).parent
output=base/'downloaded/b12-benchmark-b12-envi-20261018-c01'
session=output/'session-s11-b2-en-r03'
read=lambda p:json.loads(p.read_bytes())
manifest=read(session/'artifacts-manifest.json')
assert len(manifest)==6
for rel,m in manifest.items():
 p=output/rel
 assert p.stat().st_size==m['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==m['sha256'],rel
summary=read(session/'driver-summary.json')
assert summary['status']=='failed' and summary['stage']=='verify_mounted_cache'
assert summary['error_type']=='TimeoutExpired'
assert 'verify-cache' in summary['error'] and 'timed out after' in summary['error']
assert 1200<=summary['wall_seconds']<1205 and summary['scratch_removed'] is True
assert summary['process_cap_seconds']==5400 and summary['session_cap_seconds']==7200
assert not (output/'runs').exists()
assert (session/'verify_mounted_cache.log').stat().st_size==0
assert not (session/'completeness.json').exists() and not (session/'campaign-ledger.json').exists()
assert not (session/'data-preflight.json').exists() and not (session/'runtime-preflight.json').exists()
plan=read(base/'submission-plan.json')
assert summary['settings']['prior_attempts']==plan['prior_attempted_run_ids']
assert len(plan['prior_attempted_run_ids'])==10
assert summary['settings']['baseline']=='b2' and summary['settings']['language']=='en' and summary['settings']['replicate']==3
assert hashlib.sha256(Path('scripts/27_kaggle_b12_benchmark.py').read_bytes()).hexdigest()==plan['driver_sha256']
assert read(session/'input-provenance.json')['bundle_sha256']=='2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de'
download=read(base/'download-record.json')
assert download['worker_status']=='ERROR' and len(download['downloaded'])==7 and download['omitted']==[]
result={'status':'setup_failure_evidence_integrity_verified','run_id':plan['run_id'],'worker_status':'ERROR','failure_stage':summary['stage'],'error_type':summary['error_type'],'setup_cap_seconds':1200,'driver_wall_seconds':summary['wall_seconds'],'remaining_stage_timeout_seconds_observed':615.2326039670006,'native_inference_started':False,'native_cases_generated':0,'native_result_available':False,'native_ledger_published':False,'cache_integrity_verified':False,'cache_corruption_proven':False,'scratch_removed':True,'native_manifest_entries_verified':6,'saved_files_retained':7,'saved_bytes_retained':11712,'campaign_native_processes_complete':10,'campaign_setup_failures':1,'campaign_unstarted_slots':1,'automatic_retry_performed':False,'additional_process_launched':False,'scientific_ready':False,'bigquery_jobs':0,'underlying_cache_verification_delay_cause':'undetermined; no per-file timing output before timeout'}
(base/'verified-failure.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
