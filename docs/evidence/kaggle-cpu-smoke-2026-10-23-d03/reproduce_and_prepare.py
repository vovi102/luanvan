"""Reproduce the actual Papermill admission failure, then fix only notebook metadata."""
import copy
import hashlib
import json
from pathlib import Path
import nbformat
from papermill.utils import nb_kernel_name
root=Path.cwd();old=root/'.local/kaggle-cpu-smoke-20261023-d02'
base=Path(__file__).resolve().parent
source=next((old/'deploy').glob('*.ipynb'))
nb=nbformat.read(source,as_version=4)
try:nb_kernel_name(nb)
except ValueError as e:
 assert str(e)=='No kernel name found in notebook and no override provided.'
 print('REPRODUCED:',str(e))
else:raise AssertionError('Expected original Papermill admission failure')
fixed=copy.deepcopy(nb)
fixed.metadata.kernelspec=dict(display_name='Python 3',language='python',name='python3')
assert nb_kernel_name(fixed)=='python3'
assert [dict(c) for c in fixed.cells]==[dict(c) for c in nb.cells]
nbformat.validate(fixed)
slug='nl2sql-cpu-smoke-20261023-d03'
folder=base/'deploy';folder.mkdir()
path=folder/(slug+'.ipynb');nbformat.write(fixed,path)
metadata=json.loads((old/'deploy/kernel-metadata.json').read_text())
metadata.update(id='aohkvd/'+slug,title=slug,code_file=path.name)
(folder/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
plan=json.loads((old/'submission-plan.json').read_text())
plan.update(kernel=metadata['id'],notebook_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
 purpose='Validate Python kernelspec-only fix after API log proved Papermill admission error',
 preceding_failed_control='aohkvd/nl2sql-cpu-smoke-20261023-d02',notebook_cells_byte_equivalent=True,
 notebook_metadata_only_change={'kernelspec':dict(fixed.metadata.kernelspec)},
 output_prefix='cpu-smoke-d02',platform_cap_seconds=300,
 papermill_missing_kernel_reproduced=True,papermill_kernel_admission_after_fix='python3')
(base/'submission-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
result=dict(status='actual_papermill_failure_reproduced_and_metadata_fix_validated',
 original_failure='No kernel name found in notebook and no override provided.',
 fixed_kernel_name=nb_kernel_name(fixed),cells_unchanged=True,product_code_changed=False,
 source_before_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_after_sha256=plan['notebook_sha256'])
(base/'offline-papermill-check.json').write_text(json.dumps(result,indent=2)+'\n')
print('FIX VALIDATED: Papermill selects python3; exact notebook cells unchanged.')
