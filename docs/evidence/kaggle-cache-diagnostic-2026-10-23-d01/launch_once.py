"""Fresh read-only gates, then one private CPU diagnostic submission."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest
base=Path(__file__).resolve().parent
plan=json.loads((base/'submission-plan.json').read_text());ref=plan['kernel'];slug=ref.split('/')[-1]

def save(name,value):
 with (base/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')

assert not (base/'submission-intent.json').exists(),'Inspect existing request before any further submission.'
assert hashlib.sha256((base/'diagnostic_driver.py').read_bytes()).hexdigest()==plan['driver_sha256']
assert hashlib.sha256((base/'deploy'/(slug+'.ipynb')).read_bytes()).hexdigest()==plan['notebook_sha256']
a=KaggleApi();a.authenticate()
statuses={name:a.kernels_status('aohkvd/'+name).status.name for name in [
 'nl2sql-b12-benchmark-20261023-b2-en-r03-repl01','nl2sql-b12-benchmark-20261021-b2-en-r03',
 'nl2sql-b12-benchmark-20261022-b2-vi-r03','nl2sql-environment-cache']}
assert list(statuses.values())==['ERROR','ERROR','COMPLETE','COMPLETE']
r=ApiGetKernelRequest();r.user_name='aohkvd';r.kernel_slug='nl2sql-environment-cache'
with a.build_kaggle_client() as c:
 cache=c.kernels.kernels_api_client.get_kernel(r).metadata
 quota=c.kernels.kernels_api_client.get_accelerator_quota_statistics().gpu_quota
assert cache.is_private and cache.current_version_number==5
assert quota.time_reserved.total_seconds()==0 and not quota.is_pay_to_scale_enabled
matches=[k.ref for k in a.kernels_list(mine=True,search=slug,page_size=100) if k.ref.strip('/') in (ref,'code/'+ref)]
assert not matches,'Exact diagnostic already exists; inspect without pushing.'
save('quota-and-state-before.json',dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),prior_statuses=statuses,
 gpu_remaining_hours=(quota.total_time_allowed-quota.time_used-quota.time_reserved).total_seconds()/3600,
 gpu_reserved_hours=0,is_pay_to_scale_enabled=quota.is_pay_to_scale_enabled,gpu_requested=False,
 cache_private=True,cache_version=5,matching_diagnostic_exists=False))
save('submission-intent.json',dict(started_at_utc=datetime.now(timezone.utc).isoformat(),ref=ref,one_request_only=True))
try:response=a.kernels_push(str(base/'deploy'),timeout='1800')
except Exception as exc:
 resp=getattr(exc,'response',None)
 record=dict(error_type=type(exc).__name__,http_status=getattr(resp,'status_code',None),automatic_retry=False)
 if resp is not None:
  try:
   payload=resp.json()
   if isinstance(payload,dict):record['error']=payload.get('error',payload.get('message'))
  except Exception:pass
 save('submission-error.json',record)
 raise SystemExit('Uncertain API response retained; inspect ref, do not retry.')
record=dict(submitted_at_utc=datetime.now(timezone.utc).isoformat(),ref=response.ref,url=response.url,
 version=response.version_number,kernel_id=response.kernel_id,error=response.error,
 invalid_dataset_sources=list(response.invalid_dataset_sources or []),invalid_kernel_sources=list(response.invalid_kernel_sources or []),
 private_requested=True,gpu_requested=False,internet_requested=False,platform_timeout_seconds=1800)
save('api-submitted-v1.json',record)
assert response.version_number==1 and not response.error and not record['invalid_dataset_sources'] and not record['invalid_kernel_sources']
print('Accepted private CPU diagnostic:',response.url,'v',response.version_number,'id',response.kernel_id,flush=True)
