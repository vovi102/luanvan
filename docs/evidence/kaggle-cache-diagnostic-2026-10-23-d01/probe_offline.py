"""TEST-ONLY fixture probes, never real cache/model evidence."""
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

base=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('diagnostic',base/'diagnostic_driver.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
root=base.parents[1]
native=m.load_native(root/'scripts/26_kaggle_environment.py')
original_open=Path.open
original_trace=sys.gettrace()
checks=[]
with tempfile.TemporaryDirectory(prefix='TEST-ONLY-cache-diagnostic-') as name:
    folder=Path(name);home=folder/'hf-home'
    pins={'models':{}}
    total=0
    for kind,repo in native.REPOSITORIES.items():
        revision='a'*40
        files={}
        for filename,algorithm,data in [('config.json','git-blob-sha1',b'{}'),('fixture.bin','sha256',b'TEST-ONLY\n'*500000)]:
            path=home/'hub'/('models--'+repo.replace('/','--'))/'snapshots'/revision/filename
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            expected=(hashlib.sha256(data).hexdigest() if algorithm=='sha256' else hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest())
            files[filename]=dict(bytes=len(data),algorithm=algorithm,digest=expected)
            total+=len(data)
        pins['models'][kind]=dict(repo_id=repo,revision=revision,files=files)
    out=folder/'valid';out.mkdir()
    expected=native.verify_cache(pins,home,'all')
    actual=m.observe(native,pins,home,out,heartbeat_seconds=.02)
    assert actual==expected
    events=[json.loads(line) for line in (out/'cache-progress.jsonl').read_text().splitlines()]
    assert events[-1]['event']=='verification_completed' and events[-1]['total_bytes_read']==total
    assert events[-1]['files_read_complete']==4
    assert len([e for e in events if e['event']=='file_started'])==4
    assert len([e for e in events if e['event']=='file_read_complete'])==4
    assert Path.open is original_open and sys.gettrace() is original_trace
    checks.append('Exact native receipt, byte counts, four-file progress, both digest algorithms and observer restoration')
    for mutation in ['digest','size','escape']:
        bad=copy.deepcopy(pins)
        files=bad['models']['model']['files']
        if mutation=='digest':files['config.json']['digest']='0'*40
        elif mutation=='size':files['config.json']['bytes']+=1
        else:files['../../../../../../outside']=files.pop('config.json')
        out=folder/mutation;out.mkdir()
        try:m.observe(native,bad,home,out,heartbeat_seconds=.02)
        except native.SetupError:pass
        else:raise AssertionError('Native corruption/size/path guard bypassed')
        events=[json.loads(line) for line in (out/'cache-progress.jsonl').read_text().splitlines()]
        assert events[-1]['event']=='verification_failed'
        assert not any(e['event']=='verification_completed' for e in events)
        assert Path.open is original_open and sys.gettrace() is original_trace
        checks.append('Unchanged native '+mutation+' failure and restoration, no success marker')
    # Simulate slow external reads only to observe progress while a read is in flight.
    requests=[]
    class Slow:
        def __init__(self, handle):self.handle=handle
        def __enter__(self):self.handle.__enter__();return self
        def __exit__(self,*args):return self.handle.__exit__(*args)
        def read(self,size=-1):
            requests.append(size);time.sleep(.04);return self.handle.read(size)
    def slow_open(path,*args,**kwargs):
        handle=original_open(path,*args,**kwargs)
        if path.is_relative_to(home):return Slow(handle)
        return handle
    Path.open=slow_open
    out=folder/'slow';out.mkdir()
    try:m.observe(native,pins,home,out,heartbeat_seconds=.01)
    finally:Path.open=original_open
    events=[json.loads(line) for line in (out/'cache-progress.jsonl').read_text().splitlines()]
    assert any(e['event']=='heartbeat' and e['phase']=='read' and e['current_operation_elapsed_seconds']>0 for e in events)
    assert set(requests)=={2*1024*1024}
    checks.append('Heartbeat survives slow simulated reads; exact original 2MiB read requests preserved')
    # Exercise the real parent process-group watchdog with a TEST-ONLY sleeping child.
    old_cap=m.CAP_SECONDS;m.CAP_SECONDS=.15
    try:
        try:m.run_session(folder/'absent',folder/'timeout','import time; time.sleep(5)\n')
        except subprocess.TimeoutExpired:pass
        else:raise AssertionError('Watchdog did not stop child')
    finally:m.CAP_SECONDS=old_cap
    summary=json.loads((folder/'timeout/diagnostic-summary.json').read_text())
    assert summary['status']=='timed_out' and not summary['benchmark_attempt_reserved']
    manifest=json.loads((folder/'timeout/artifacts-manifest.json').read_text())
    assert 'diagnostic-summary.json' in manifest and 'worker.log' in manifest
    assert (folder/'timeout/worker.log').stat().st_size==0
    checks.append('Real child group timeout preserves summary/log/manifest and reserves no benchmark ID')
    # Admission failure uses the real subprocess and source, without installed packages or network.
    try:m.run_session(folder/'absent',folder/'bad-mount',(base/'diagnostic_driver.py').read_text())
    except RuntimeError:pass
    else:raise AssertionError('Invalid mount accepted')
    summary=json.loads((folder/'bad-mount/diagnostic-summary.json').read_text())
    assert summary['status']=='failed' and summary['returncode']!=0
    assert not (folder/'bad-mount/native-cache-receipt.json').exists()
    checks.append('Invalid mount fails admission in real child; no fake cache receipt')
result=dict(status='offline_fixture_probes_passed',test_only=True,genuine_cache_verified=False,
 real_models_loaded=False,benchmark_attempts_reserved=0,checks=checks,diagnostic_driver_sha256=m.sha(base/'diagnostic_driver.py'))
(base/'offline-probes.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
