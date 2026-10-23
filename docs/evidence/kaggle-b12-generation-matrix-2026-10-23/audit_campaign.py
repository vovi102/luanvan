"""Read-only campaign audit; no model, BigQuery, report mutation or pooling."""
import collections
import hashlib
import json
from pathlib import Path

root=Path.cwd()
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
old=read(root/'docs/evidence/kaggle-b12-campaign-status-2026-10-23.json')
new_base=root/'.local/kaggle-b12-benchmark-20261023-b2-en-r03-repl02'
new_run=next((root/'docs/evidence/kaggle-b12-benchmark-b2-en-r03-replacement02-2026-10-23/saved-v1').rglob('run.json'))
registry=[]
reference={}
rows=old['rows']+[dict(source_run_json=str(new_run.relative_to(root)))]
for row in rows:
 p=root/row['source_run_json'];r=read(p);report_path=p.parent/'native-report.json'
 if 'source_run_sha256' in row:assert sha(p)==row['source_run_sha256']
 if 'source_report_sha256' in row:assert sha(report_path)==row['source_report_sha256']
 report=read(report_path);digest=report.pop('report_sha256')
 assert hashlib.sha256((json.dumps(report,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()==digest
 assert r['status']=='completed_native_inference' and r['returncode']==0
 assert report['prediction_count']==report['metrics']['total']==100
 assert r['bundle_content_sha256']=='4c10b260b7e1b119b9b6a13b43b9c00c3a4ec84402648b03eac92253840682bc'
 snapshot=root/'data/dataset/test'/('test-100.jsonl' if r['language']=='en' else 'test-100-vi.jsonl')
 assert report['input_sha256']==sha(snapshot)
 assert (r['baseline'],r['language'],r['run_id'])==(report['baseline'],report['language'],report['run_id'])
 for name,expected in r['native_outputs'].items():assert sha(p.parent/name)==expected
 predictions=[json.loads(s) for s in (p.parent/'predictions.jsonl').read_text().splitlines()]
 logs=[json.loads(s) for s in (p.parent/'native-log.jsonl').read_text().splitlines()]
 assert len(predictions)==len(logs)==100
 ids=[x['case_id'] for x in predictions]
 assert len(set(ids))==100 and ids==[x['case_id'] for x in logs]
 for prediction,log in zip(predictions,logs,strict=True):
  assert prediction['run_id']==log['run_id']==r['run_id']
  assert prediction['language']==log['language']==r['language']
  assert not prediction['prediction']['completion']['synthetic_backend'] and not log['synthetic_backend']
  assert prediction['prediction']['completion']['model_revision']==r['config']['model_revision']
 config={k:v for k,v in r['config'].items() if k not in ('campaign_id','hf_home')}
 if r['language'] in reference:assert config==reference[r['language']]
 else:reference[r['language']]=config
 assert all('T4' in x for x in r['hardware']['gpu_names'])
 assert r['hardware']['python'].startswith('3.11.15 ')
 assert not report['scientific_ready']
 registry.append(dict(run_id=r['run_id'],execution_campaign_id=r['config']['campaign_id'],
  baseline=r['baseline'],language=r['language'],replicate=r['replicate'],N=100,
  status='complete_native_outputs_integrity_verified',native_scientific_ready=report['scientific_ready'],
  native_blockers=report['blockers'],extraction_ok=report['metrics']['extraction_ok'],
  status_counts=report['metrics']['status_counts'],p50_latency_ms=report['metrics']['p50_latency_ms'],
  p95_latency_ms=report['metrics']['p95_latency_ms'],
  source_run_json=str(p.relative_to(root)),source_run_sha256=sha(p),source_report_sha256=sha(report_path)))
assert len({r['run_id'] for r in registry})==len(registry)==12
counts=collections.Counter(r['baseline']+'_'+r['language'] for r in registry)
assert counts=={'b1_en':3,'b1_vi':3,'b2_en':3,'b2_vi':3}
for key in counts:
 assert {r['replicate'] for r in registry if r['baseline']+'_'+r['language']==key}=={1,2,3}
ledger=read(next((root/'docs/evidence/kaggle-b12-benchmark-b2-en-r03-replacement02-2026-10-23/saved-v1').rglob('campaign-ledger.json')))
assert len(ledger['attempted_run_ids'])==len(set(ledger['attempted_run_ids']))==14
failed_ids=['b12-envi-20261018-c01-b2-en-r03','b12-envi-20261018-c01-replacement01-b2-en-r03']
assert set(ledger['attempted_run_ids'])==set(failed_ids)|{r['run_id'] for r in registry}
assert ledger['parent_campaign_id']=='b12-envi-20261018-c01' and ledger['replacement_of']==failed_ids[0]
result=dict(date='2026-10-23',status='native_generation_matrix_complete_scientific_gates_pending',
 parent_campaign_id='b12-envi-20261018-c01',native_generation_matrix_complete=True,
 native_successes_verified=12,setup_failures_retained=2,total_attempted_ids=14,
 native_replicates_per_baseline_language=dict(counts),N_per_run_language=100,
 original_unstarted_slots=0,remaining_native_generation_processes=0,
 english_vietnamese_pooled=False,native_execution_accuracy_evaluated=False,scientific_campaign_complete=False,
 research_config_compatible_within_language=True,
 failed_attempts=[dict(run_id=x,native_inference_started=False,cases_generated=0,id_must_not_be_reused=True) for x in failed_ids],
 final_full_replacement='b12-envi-20261018-c01-replacement02-b2-en-r03',rows=registry,
 retained_native_ledger=ledger,
 next_required_work='T5.4 canonical adaptation, privacy/cost review, separately authorized/budgeted predicted/gold BigQuery execution and reports/comparisons; no extra B1/B2 generation process needed.',
 automatic_new_process_started=False)
folder=root/'.local/kaggle-b12-campaign-final-20261023'
folder.mkdir(parents=True,exist_ok=True)
(folder/'verified-campaign.json').write_text(json.dumps(result,indent=2)+'\n')
print('Independent audit:',dict(counts),'; 12 native successes, 2 retained setup failures, 14 native-ledger IDs.')
print('No remaining B1/B2 generation process. Scientific/execution-accuracy gates remain pending.')
