"""One-off no-input/no-GPU/no-network runtime/output control."""
import hashlib,json
from pathlib import Path
import nbformat
base=Path(__file__).resolve().parent
slug='nl2sql-cpu-smoke-20261023-d02'
source='''print("CPU_SMOKE_BEGIN", flush=True)
from pathlib import Path
from datetime import datetime, timezone
import json, sys, time
output = Path("/kaggle/working/cpu-smoke-d02")
output.mkdir(exist_ok=False)
record = {"probe": "cpu-smoke-d02", "python": sys.version,
          "started_at_utc": datetime.now(timezone.utc).isoformat(),
          "model_loaded": False, "inference": False, "benchmark_attempt_reserved": False}
with (output / "started.json").open("x") as f:
    json.dump(record, f)
for step in range(3):
    with (output / "heartbeat.jsonl").open("a") as f:
        f.write(json.dumps({"step": step}) + "\\n")
    print("CPU_SMOKE_HEARTBEAT", step, flush=True)
    time.sleep(1)
with (output / "complete.json").open("x") as f:
    json.dump({**record, "status": "runtime_and_output_probe_complete"}, f)
print("CPU_SMOKE_COMPLETE", flush=True)
'''
compile(source,'cpu-smoke','exec')
# Exercise the exact submitted code using a temporary TEST-ONLY output path.
import tempfile,contextlib,io
with tempfile.TemporaryDirectory(prefix='TEST-ONLY-cpu-smoke-') as folder:
 test_source=source.replace('/kaggle/working/cpu-smoke-d02',folder+'/probe')
 with contextlib.redirect_stdout(io.StringIO()):exec(compile(test_source,'TEST-ONLY-cpu-smoke','exec'),{})
 assert json.loads(Path(folder+'/probe/complete.json').read_text())['status']=='runtime_and_output_probe_complete'
 assert [json.loads(s)['step'] for s in Path(folder+'/probe/heartbeat.jsonl').read_text().splitlines()]==[0,1,2]
nb=nbformat.v4.new_notebook(cells=[nbformat.v4.new_markdown_cell('One-off private CPU runtime/output control. No input attachments, internet, GPU, model, benchmark or install. Platform cap300s.'),nbformat.v4.new_code_cell(source)])
nbformat.validate(nb)
deploy=base/'deploy';deploy.mkdir()
p=deploy/(slug+'.ipynb');nbformat.write(nb,p)
meta=dict(id='aohkvd/'+slug,title=slug,code_file=p.name,language='python',kernel_type='notebook',is_private=True,
 enable_gpu=False,enable_tpu=False,enable_internet=False,dataset_sources=[],kernel_sources=[],model_sources=[],competition_sources=[])
(deploy/'kernel-metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
plan=dict(kernel=meta['id'],purpose='Check CPU runtime execution and output persistence with no mounts before retrying cache diagnostic',
 platform_cap_seconds=300,gpu_requested=False,internet_requested=False,input_attachments=[],
 notebook_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),offline_exact_cell_fixture_passed=True,
 model_inference=False,benchmark_attempt_reserved=False,authorization='User requested API recheck or retry after empty failed CPU diagnostic; one small bounded control.')
(base/'submission-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print('Exact-cell local fixture and notebook validation passed; no product code changed.')
