"""Read-only Kaggle monitoring; authentication stays inside the installed SDK."""
import json
import signal
import sys
from datetime import datetime,timezone
from pathlib import Path
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest,ApiGetKernelSessionLogsStreamRequest
base=Path(__file__).parent
slug='nl2sql-b12-benchmark-20261023-b2-en-r03-replacement01'
a=KaggleApi();a.authenticate()
s=a.kernels_status('aohkvd/'+slug)
r=ApiGetKernelRequest();r.user_name='aohkvd';r.kernel_slug=slug
with a.build_kaggle_client() as c:
 m=c.kernels.kernels_api_client.get_kernel(r).metadata
 q=c.kernels.kernels_api_client.get_accelerator_quota_statistics();g=q.gpu_quota
record={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'ref':m.ref,'version':m.current_version_number,'status':s.status.name,'private':m.is_private,'enable_gpu':m.enable_gpu,'machine_shape':m.machine_shape,'kernel_sources':list(m.kernel_data_sources or []),'gpu_used_hours':g.time_used.total_seconds()/3600,'gpu_reserved_hours':g.time_reserved.total_seconds()/3600,'gpu_remaining_hours':(g.total_time_allowed-g.time_used-g.time_reserved).total_seconds()/3600}
assert m.is_private and m.enable_gpu and m.machine_shape=='NvidiaTeslaT4'
assert list(m.dataset_data_sources or [])==['aohkvd/nl2sql-setup-inputs']
assert list(m.kernel_data_sources or []) in (['aohkvd/nl2sql-environment-cache/5'],['aohkvd/nl2sql-environment-cache'])
with (base/'status-history.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
(base/'current-status.json').write_text(json.dumps(record,indent=2)+'\n')
print(record['checked_at_utc'], record['status'], 'GPU remaining hours:', round(record['gpu_remaining_hours'], 5), flush=True)
if "--status-only" in sys.argv:sys.exit(0)
lines=[]
def stop(*args):raise TimeoutError()
signal.signal(signal.SIGALRM,stop);signal.alarm(12)
try:
 for event in a.kernels_logs_stream('aohkvd/'+slug):
  data=event.get('data')
  if data:lines.append(data)
except Exception as e:
 print('Log stream:',type(e).__name__,'HTTP',getattr(getattr(e,'response',None),'status_code',None),flush=True)
finally:
 signal.alarm(0)
 if lines:
  data='\n'.join(lines)+'\n'
  target=base/'v1-live.log'
  if not target.exists() or len(data)>=target.stat().st_size:target.write_text(data)
  print(data[-1800:],flush=True)
