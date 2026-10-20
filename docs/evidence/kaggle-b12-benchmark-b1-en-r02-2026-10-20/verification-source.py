"""Offline artifact/runtime verification only; no canonical adaptation or inference."""
import hashlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path
base=Path(__file__).parent
campaign='b12-envi-20261018-c01';run_id=campaign+'-b1-en-r02'
root=Path('.local/benchmark-preparation/driver-accepted-input').resolve()
output=base/'downloaded'/('b12-benchmark-'+campaign)
session=output/'session-s05-b1-en-r02';folder=output/'runs'/run_id
read=lambda p:json.loads(p.read_bytes())
hashfile=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=read(session/'artifacts-manifest.json')
for name,meta in manifest.items():
 path=output/name
 assert path.is_file(),name
 assert path.stat().st_size==meta['bytes'] and hashfile(path)==meta['sha256'],name
summary=read(session/'driver-summary.json');run=read(folder/'run.json')
assert summary['status']=='completed_native_process' and summary['scratch_removed']
assert summary['session_cap_seconds']==7200 and summary['process_cap_seconds']==5400
assert run['status']=='completed_native_inference' and run['returncode']==0
assert (run['baseline'],run['language'],run['replicate'],run['run_id'])==('b1','en',2,run_id)
assert run['config']['campaign_id']==campaign and run['config']['seed']==42
assert run['config']['max_new_tokens']==512 and run['config']['batch_size']==1
assert run['config']['load_in_4bit'] and run['config']['do_sample'] is False
assert run['config']['run_timeout_seconds']==5400
spec=importlib.util.spec_from_file_location('benchmark_driver','scripts/27_kaggle_b12_benchmark.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
assert hashfile(session/'benchmark-driver.py')==hashfile(Path('scripts/27_kaggle_b12_benchmark.py'))
assert run['config']['model_revision']==driver.MODEL_REVISION
assert run['config']['encoder_revision']==driver.ENCODER_REVISION
item=dict(run_id=run_id,baseline='b1',language='en',folder=str(folder))
check=driver.check_complete(root,item)
assert read(session/'completeness.json')==check
assert read(session/'campaign-ledger.json')['attempted_run_ids']==[campaign+'-b1-en-r01',campaign+'-b1-vi-r01',campaign+'-b2-en-r01',campaign+'-b2-vi-r01',run_id]
assert {p.parent.name for p in (output/'runs').glob('*/run.json')}=={run_id}
assert len(read(session/'campaign-plan.json'))==12
assert read(session/'runtime-preflight.json')['status']=='ready'
data=read(session/'data-preflight.json')
assert data['status']=='data_ready' and data['training_records']==7208
assert data['english_records']==data['vietnamese_records']==100
assert data['training_sha256']=='b6440c0b281a270907d8dd5b8d11cdd1506ce125ae465aa63ee66963e0dd4835'
assert read(session/'verify_mounted_cache.log')['status']=='cache_bytes_verified'
provenance=read(session/'input-provenance.json')
assert provenance['bundle_sha256']==driver.BUNDLE_SHA256
assert provenance['cache_inventory_sha256']==driver.INVENTORY_SHA256
assert provenance['weights_copied'] is False
hardware=run['hardware']
assert hardware['gpu_names']==['Tesla T4','Tesla T4']
assert hardware['python'].startswith('3.11.15 ')
report=read(folder/'native-report.json');supplied=report.pop('report_sha256')
assert report['input_sha256']==hashfile(root/'data/dataset/test/test-100.jsonl')
canonical=(json.dumps(report,sort_keys=True,separators=(',',':'))+'\n').encode()
assert hashlib.sha256(canonical).hexdigest()==supplied
rows=[json.loads(line) for line in (folder/'predictions.jsonl').read_text().splitlines()]
logs=[json.loads(line) for line in (folder/'native-log.jsonl').read_text().splitlines()]
for row,log in zip(rows,logs,strict=True):
 prediction=row['prediction'];completion=prediction['completion']
 assert completion['model_id']=='meta-llama/Meta-Llama-3-8B-Instruct'
 assert completion['model_revision']==driver.MODEL_REVISION and completion['synthetic_backend'] is False
 assert row['seed']==log['seed']==42
 assert row['input_sha256']==log['input_sha256']==report['input_sha256']
 assert prediction['latency_ms']==log['latency_ms']
 assert prediction['prompt_sha256']==log['prompt_sha256']
 assert prediction['extraction_status']==log['extraction_status']
from nl2sparql.models.b12.evaluate import load_evaluation_cases
cases=load_evaluation_cases(root/'data/dataset/test/test-100.jsonl',language='en',source_root=root)
for row,case in zip(rows,cases,strict=True):
 assert row['prediction']['question']==case.question and case._trusted_source and case.reviewed and case.live_verified
 assert row['prediction']['selected_examples']==[]

seconds=(datetime.fromisoformat(run['finished_at_utc'])-datetime.fromisoformat(run['started_at_utc'])).total_seconds()
result={'status':'native_process_complete_and_integrity_verified','run_id':run_id,'baseline':'b1','language':'en','N':100,'session_native_processes_completed':1,'campaign_native_processes_completed':5,'remaining_campaign_processes':7,'native_wall_seconds':seconds,'driver_wall_seconds':summary['wall_seconds'],'native_manifest_files_verified':len(manifest),'genuine_completions_verified':100,'hardware':hardware,'metrics':report['metrics'],'native_scientific_ready':report['scientific_ready'],'native_blockers':report['blockers'],'scientific_campaign_complete':False,'bigquery_jobs':0,'canonical_adaptation_performed':False,'scratch_removed':True}
(base/'verified-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
