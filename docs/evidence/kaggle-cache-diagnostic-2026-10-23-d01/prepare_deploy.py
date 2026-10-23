"""Prepare a one-off CPU-only diagnostic notebook, never a benchmark change."""
import hashlib
import json
from pathlib import Path
import nbformat
base=Path(__file__).resolve().parent
root=base.parents[1]
source=(base/'diagnostic_driver.py').read_text()
sha=hashlib.sha256(source.encode()).hexdigest()
probes=json.loads((base/'offline-probes.json').read_text())
assert probes['status']=='offline_fixture_probes_passed' and probes['diagnostic_driver_sha256']==sha
assert hashlib.sha256((root/'scripts/26_kaggle_environment.py').read_bytes()).hexdigest()=='91be7869ae7223b93e7ff6c3c7a58589b241161ef7a782351f02e105e86d9218'
slug='nl2sql-cache-diag-20261023-d01'
nb=nbformat.v4.new_notebook(cells=[
 nbformat.v4.new_markdown_cell('''# One-off private CPU cache diagnostic d01
Observe the unchanged, fingerprint-checked accepted verify_cache function on private mounted cache v5.
No model imports/loading/inference, training, BigQuery, network, GPU, model copying or benchmark identity reservation.
Per-file/byte/read-time/CPU/heartbeat observations are operational diagnostics, not scientific completion or benchmark latency.
Diagnostic runtime is default Kaggle CPU/Python, different from pinned T4 inference runtime.
1620s parent watchdog; 1800s platform cap. Keep every output; no retries or changes to pins/checks/caps.
'''),
 nbformat.v4.new_code_cell('ALLOW_DIAGNOSTIC = True  # enabled only for this separately authorized diagnostic\n'),
 nbformat.v4.new_code_cell('DRIVER_SHA256 = '+repr(sha)+'\nDRIVER_SOURCE = '+repr(source)+'\n'),
 nbformat.v4.new_code_cell('''if not ALLOW_DIAGNOSTIC:
    print("BLOCKED: diagnostic disabled")
else:
    import hashlib
    from pathlib import Path
    if hashlib.sha256(DRIVER_SOURCE.encode()).hexdigest() != DRIVER_SHA256:
        raise ValueError("Diagnostic source fingerprint mismatch")
    scope = {"__name__": "diagnostic_notebook"}
    exec(compile(DRIVER_SOURCE, "diagnostic-driver", "exec"), scope)
    scope["run_session"](Path("/kaggle/input"), Path("/kaggle/working/cache-diagnostic-d01"), DRIVER_SOURCE)
''')])
nbformat.validate(nb)
for c in nb.cells:
 if c.cell_type=='code':compile(c.source,'diagnostic-cell','exec')
# The disabled form is import/effect-free, despite carrying a source string.
scope={}
for i,c in enumerate(nb.cells):
 if c.cell_type=='code':exec('ALLOW_DIAGNOSTIC = False' if i==1 else c.source,scope)
assert scope['ALLOW_DIAGNOSTIC'] is False and 'run_session' not in scope
folder=base/'deploy';folder.mkdir(exist_ok=False)
path=folder/(slug+'.ipynb');nbformat.write(nb,path)
metadata=dict(id='aohkvd/'+slug,title=slug,code_file=path.name,language='python',kernel_type='notebook',
 is_private=True,enable_gpu=False,enable_tpu=False,enable_internet=False,
 dataset_sources=['aohkvd/nl2sql-setup-inputs'],kernel_sources=['aohkvd/nl2sql-environment-cache/5'],
 model_sources=[],competition_sources=[])
(folder/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
plan=dict(status='offline_diagnostic_prepared_not_submitted',kernel=metadata['id'],diagnostic_only=True,
 gpu_requested=False,internet_requested=False,model_inference=False,benchmark_attempt_reserved=False,
 verification_cap_seconds=1620,platform_cap_seconds=1800,heartbeat_seconds=10,
 driver_sha256=sha,notebook_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
 accepted_verifier_sha256='91be7869ae7223b93e7ff6c3c7a58589b241161ef7a782351f02e105e86d9218',
 native_verifier_modified=False,pins_and_digest_guards_unchanged=True,
 authorization='User requested continuation after setup failure review; diagnose cache before any further benchmark. One private CPU diagnostic, not another benchmark attempt.',
 comparison_limit='Default CPU host/Python differs from the pinned T4 benchmark runtime; cannot alone prove the T4 failure cause or repair.',
 purpose='Identify file/read/open/hash-and-loop bottlenecks with 10s in-flight heartbeats and exact native full-byte checks.',
 research_settings_changed=False,all_existing_failure_evidence_preserved=True)
(base/'submission-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
print('CPU-only offline diagnostic notebook/schema/source/admission checks passed; not submitted.')
