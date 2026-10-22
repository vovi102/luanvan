"""Verify saved setup-only validation; no model imports, inference or canonical adaptation."""
import hashlib,json,math
from pathlib import Path
base=Path(__file__).parent
campaign='b12-setup-20261022-v02'
output=base/'downloaded'/('b12-benchmark-'+campaign)
session=output/'session-validate-setup-v02'
read=lambda p:json.loads(p.read_bytes())
hashfile=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=read(session/'artifacts-manifest.json')
for rel,m in manifest.items():
 p=output/rel
 assert p.stat().st_size==m['bytes'] and hashfile(p)==m['sha256'],rel
summary=read(session/'driver-summary.json')
assert summary['status']=='prepared_without_inference' and summary['scratch_removed'] is True
assert summary['setup_cap_seconds']==1620 and summary['process_cap_seconds']==5400
assert summary['worker_max_seconds']==5460 and summary['cleanup_reserve_seconds']==120 and summary['session_cap_seconds']==7200
settings=read(session/'settings.json')
assert settings['allow_preparation'] is True and settings['allow_env_install'] is True
assert settings['allow_real_inference'] is False and settings['prior_attempts']==[]
assert settings['campaign_id']==campaign and settings['session_id']=='validate-setup-v02'
assert not (output/'runs').exists() and not (session/'campaign-ledger.json').exists() and not (session/'completeness.json').exists()
assert not list(output.rglob('predictions.jsonl')) and not list(output.rglob('native-report.json'))
assert hashfile(session/'benchmark-driver.py')==hashfile(Path('scripts/27_kaggle_b12_benchmark.py'))=='7f80915acfb47ce4e2741eb1f60f20487b121390d9cdd2ef43ffe8b1f4e7c5de'
cache=read(session/'verify_mounted_cache.log')
assert cache['status']=='cache_bytes_verified' and cache['model_loaded'] is False
assert cache['models']['model']['revision']=='8afb486c1db24fe5011ec46dfbe5b5dccdb575c2' and cache['models']['model']['files_verified']==13
assert cache['models']['encoder']['revision']=='1110a243fdf4706b3f48f1d95db1a4f5529b4d41' and cache['models']['encoder']['files_verified']==11
provenance=read(session/'input-provenance.json')
assert provenance['bundle_sha256']=='2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de'
assert provenance['cache_inventory_sha256']=='ae3b7dc2361f151bcc59d68f4b2ddcdef74b99a5fe8374b041190bded84d84f1' and provenance['weights_copied'] is False
runtime=read(session/'runtime-preflight.json');data=read(session/'data-preflight.json')
assert runtime['status']=='ready' and runtime['blockers']==[] and runtime['hardware_checked'] is False
assert runtime['expected_packages']==runtime['installed_packages']
assert data['status']=='data_ready' and data['training_records']==7208 and data['english_records']==data['vietnamese_records']==100
assert data['training_sha256']=='b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835'
assert len(read(session/'campaign-plan.json'))==12
rows=[json.loads(s) for s in (session/'stage-timings.jsonl').read_text().splitlines()]
expected=['install_bootstrap','create_python311','install_locked_environment','verify_mounted_cache','native_cli25']
assert len(rows)==10
stages=[]
for index,name in enumerate(expected):
 start,finish=rows[index*2:index*2+2]
 assert start['stage']==finish['stage']==name and start['event']=='started' and finish['event']=='finished'
 assert finish['outcome']=='completed' and finish['elapsed_seconds']>=0
 cap=1620 if index<4 else 7080
 expected_timeout=cap-start['driver_elapsed_seconds']
 if index==4:expected_timeout=min(5460,expected_timeout)
 assert start['timeout_seconds']>0 and math.isclose(start['timeout_seconds'],expected_timeout,abs_tol=1e-6)
 assert finish['driver_elapsed_seconds']>=start['driver_elapsed_seconds'] and finish['driver_elapsed_seconds']<=cap
 stages.append({'stage':name,'elapsed_seconds':finish['elapsed_seconds'],'driver_elapsed_seconds_at_finish':finish['driver_elapsed_seconds'],'timeout_seconds':start['timeout_seconds']})
assert summary['wall_seconds']<7080
record={'status':'real_setup_cache_runtime_validation_integrity_verified','campaign_id':campaign,'native_generations':0,'benchmark_attempt_id_reserved':False,'cache_bytes_verified_files':24,'model_loaded':False,'native_inference_enabled':False,'hardware_checked':False,'python_31115_worker_guard_passed':True,'runtime_packages_ready':True,'data_preflight_ready':True,'new_driver_sha256':hashfile(session/'benchmark-driver.py'),'setup_cap_seconds':1620,'session_cap_seconds':7200,'driver_wall_seconds':summary['wall_seconds'],'setup_completed_seconds':stages[3]['driver_elapsed_seconds_at_finish'],'stages':stages,'manifest_entries_verified':len(manifest),'scratch_removed':True,'scientific_ready':False,'bigquery_jobs':0,'original_en_r03_failure_preserved':True,'limitation':'This real session passed; it does not prove the original transient slowdown cannot recur or verify GPU hardware/model inference.'}
(base/'verified-result.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
