"""Audit the genuine tiny CPU control result; not model/scientific evidence."""
import hashlib,json
from pathlib import Path
base=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_bytes())
output=base/'downloaded/cpu-smoke-d02'
status=read(base/'current-status.json');assert status['status']=='COMPLETE'
assert status['remote_source_match'] and status['no_input_attachments']
started=read(output/'started.json');complete=read(output/'complete.json')
assert complete['status']=='runtime_and_output_probe_complete'
assert started['probe']==complete['probe']=='cpu-smoke-d02'
assert started['python']==complete['python']
assert not complete['model_loaded'] and not complete['inference'] and not complete['benchmark_attempt_reserved']
assert [json.loads(s)['step'] for s in (output/'heartbeat.jsonl').read_text().splitlines()]==[0,1,2]
log=''.join(e.get('data','') for e in json.loads(status['persisted_log']))
assert 'CPU_SMOKE_BEGIN' in log and 'CPU_SMOKE_COMPLETE' in log
assert 'No kernel name found' not in log
(base/'platform.log').write_text(log)
record=dict(status='genuine_cpu_runtime_and_output_control_complete',files_verified=3,
 cpu_python=complete['python'],gpu_requested=False,internet_requested=False,no_input_attachments=True,
 missing_kernelspec_fix_remote_execution_validated=True,kaggle_runtime_and_output_persistence_worked=True,
 cache_verification_performed=False,T4_setup_issue_resolved=False,model_loaded=False,
 benchmark_attempt_reserved=False,scientific_ready=False,
 saved_files={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in output.iterdir() if p.is_file()})
(base/'verified-result.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
