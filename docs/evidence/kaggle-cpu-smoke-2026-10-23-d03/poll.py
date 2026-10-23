import json
from datetime import datetime,timezone
from pathlib import Path
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest,ApiListKernelSessionOutputRequest
base=Path(__file__).resolve().parent
plan=json.loads((base/'submission-plan.json').read_text());ref=plan['kernel'];slug=ref.split('/')[-1]
a=KaggleApi();a.authenticate();status=a.kernels_status(ref)
r=ApiGetKernelRequest();r.user_name='aohkvd';r.kernel_slug=slug
with a.build_kaggle_client() as c:response=c.kernels.kernels_api_client.get_kernel(r)
m=response.metadata
assert m.is_private and not m.enable_gpu and not m.enable_tpu and not m.enable_internet and m.current_version_number==1
assert not list(m.dataset_data_sources or []) and not list(m.kernel_data_sources or [])
remote=json.loads(response.blob.source);local=json.loads((base/'deploy'/(slug+'.ipynb')).read_text())
assert [(c['cell_type'],''.join(c['source'])) for c in remote['cells']]==[(c['cell_type'],''.join(c['source'])) for c in local['cells']]
assert remote['metadata']['kernelspec']['name']==local['metadata']['kernelspec']['name']=='python3'
record=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),status=status.status.name,failure_message=status.failure_message,private=True,gpu_enabled=False,internet_enabled=False,
 no_input_attachments=True,remote_source_match=True)
if status.status.name in ('ERROR','COMPLETE','CANCELLED'):
 req=ApiListKernelSessionOutputRequest();req.user_name='aohkvd';req.kernel_slug=slug;req.page_size=100
 with a.build_kaggle_client() as c:out=c.kernels.kernels_api_client.list_kernel_session_output(req)
 record.update(output_names=[f.file_name for f in out.files or []],next_page_present=bool(out.next_page_token),persisted_log=out.log or '')
(base/'current-status.json').write_text(json.dumps(record,indent=2)+'\n')
with (base/'status-history.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
print(json.dumps(record,indent=2),flush=True)
