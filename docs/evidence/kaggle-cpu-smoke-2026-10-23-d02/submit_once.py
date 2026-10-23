import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from kaggle.api.kaggle_api_extended import KaggleApi
base=Path(__file__).resolve().parent
plan=json.loads((base/'submission-plan.json').read_text());ref=plan['kernel'];slug=ref.split('/')[-1]
def save(name,obj):
 with (base/name).open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
assert not (base/'submission-intent.json').exists()
assert hashlib.sha256((base/'deploy'/(slug+'.ipynb')).read_bytes()).hexdigest()==plan['notebook_sha256']
a=KaggleApi();a.authenticate()
assert a.kernels_status('aohkvd/nl2sql-cache-diag-20261023-d01').status.name=='ERROR'
assert not [k for k in a.kernels_list(mine=True,search=slug,page_size=100) if k.ref.strip('/') in [ref,'code/'+ref]]
save('submission-intent.json',dict(started_at_utc=datetime.now(timezone.utc).isoformat(),ref=ref,one_request=True))
try:r=a.kernels_push(str(base/'deploy'),timeout='300')
except Exception as e:
 response=getattr(e,'response',None)
 save('submission-error.json',dict(error_type=type(e).__name__,http_status=getattr(response,'status_code',None),automatic_retry=False))
 raise SystemExit('Uncertain response retained; inspect before any further submission.')
save('api-submitted-v1.json',dict(submitted_at_utc=datetime.now(timezone.utc).isoformat(),ref=r.ref,url=r.url,version=r.version_number,kernel_id=r.kernel_id,error=r.error,
 invalid_dataset_sources=list(r.invalid_dataset_sources or []),invalid_kernel_sources=list(r.invalid_kernel_sources or []),gpu_requested=False,platform_cap_seconds=300))
assert r.version_number==1 and not r.error
print('Submitted one CPU control:',r.url,'version',r.version_number,'id',r.kernel_id,flush=True)
