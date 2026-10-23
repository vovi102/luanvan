"""One requested diagnostic retry; only fix kernelspec, preserve observer/checks."""
import copy,hashlib,json,shutil
from pathlib import Path
import nbformat
from papermill.utils import nb_kernel_name
base=Path(__file__).resolve().parent
root=base.parents[1]
original=root/'.local/kaggle-cache-diagnostic-20261023-d01'
control=root/'.local/kaggle-cpu-smoke-20261023-d03'
verified=json.loads((control/'verified-result.json').read_text())
assert verified['status']=='genuine_cpu_runtime_and_output_control_complete'
assert verified['missing_kernelspec_fix_remote_execution_validated']
old=nbformat.read(next((original/'deploy').glob('*.ipynb')),as_version=4)
try:nb_kernel_name(old)
except ValueError as e:assert 'No kernel name found' in str(e)
else:raise AssertionError('Expected same missing metadata defect in original diagnostic')
nb=copy.deepcopy(old)
nb.metadata.kernelspec=dict(display_name='Python 3',language='python',name='python3')
assert nb_kernel_name(nb)=='python3'
assert [dict(c) for c in nb.cells]==[dict(c) for c in old.cells]
nbformat.validate(nb)
slug='nl2sql-cache-diag-20261023-d04'
folder=base/'deploy';folder.mkdir()
path=folder/(slug+'.ipynb');nbformat.write(nb,path)
meta=json.loads((original/'deploy/kernel-metadata.json').read_text())
meta.update(id='aohkvd/'+slug,title=slug,code_file=path.name)
(folder/'kernel-metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
plan=json.loads((original/'submission-plan.json').read_text())
plan.update(kernel=meta['id'],status='offline_requested_retry_prepared',
 notebook_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
 authorization='User explicitly requested API checks or retry; after metadata-only CPU control succeeded, one bounded CPU cache diagnostic retry with a fresh ref.',
 preceding_diagnostic='aohkvd/nl2sql-cache-diag-20261023-d01',
 successful_control='aohkvd/nl2sql-cpu-smoke-20261023-d03',
 repaired_notebook_metadata=dict(kernelspec=dict(nb.metadata.kernelspec)),
 notebook_cells_unchanged=True,diagnostic_driver_unchanged=True,
 output_prefix='cache-diagnostic-d01',benchmark_retry_authorized=False,
 default_cpu_python_observed_in_control=verified['cpu_python'])
(base/'submission-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
for name in ['diagnostic_driver.py','poll.py','export_saved.py','verify_saved.py']:
 s=(original/name).read_text()
 if name=='export_saved.py':s=s.replace('nl2sql-cache-diag-20261023-d01',slug)
 if name=='poll.py':s=s.replace("record=dict(checked_at_utc=","assert remote['metadata']['kernelspec']['name']==local['metadata']['kernelspec']['name']=='python3'\nrecord=dict(checked_at_utc=")
 (base/name).write_text(s)
assert hashlib.sha256((base/'diagnostic_driver.py').read_bytes()).hexdigest()==plan['driver_sha256']
check=dict(status='papermill_metadata_repair_and_control_validated',
 original_diagnostic_lacks_kernel=True,fixed_kernel_name=nb_kernel_name(nb),
 source_cells_unchanged=True,diagnostic_driver_unchanged=True,
 control_verified_result_sha256=hashlib.sha256((control/'verified-result.json').read_bytes()).hexdigest())
(base/'offline-retry-check.json').write_text(json.dumps(check,indent=2)+'\n')
s=(original/'launch_once.py').read_text()
s=s.replace("assert not (base/'submission-intent.json').exists()", "assert json.loads((base/'offline-retry-check.json').read_text())['fixed_kernel_name']=='python3'\nassert not (base/'submission-intent.json').exists()")
s=s.replace("a=KaggleApi();a.authenticate()", "a=KaggleApi();a.authenticate()\nassert a.kernels_status('aohkvd/nl2sql-cache-diag-20261023-d01').status.name=='ERROR'\nassert a.kernels_status('aohkvd/nl2sql-cpu-smoke-20261023-d03').status.name=='COMPLETE'")
(base/'launch_once.py').write_text(s)
for p in base.glob('*.py'):compile(p.read_text(),str(p),'exec')
print('Original diagnostic metadata failure reproduced; python3 repair passes Papermill; every cell/observer byte unchanged.')
