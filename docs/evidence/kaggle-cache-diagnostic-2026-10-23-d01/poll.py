"""Read-only existing CPU diagnostic state and source verification."""
import json
from datetime import datetime,timezone
from pathlib import Path
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest
base=Path(__file__).resolve().parent
plan=json.loads((base/'submission-plan.json').read_text());ref=plan['kernel'];slug=ref.split('/')[-1]
a=KaggleApi();a.authenticate();status=a.kernels_status(ref).status.name
r=ApiGetKernelRequest();r.user_name='aohkvd';r.kernel_slug=slug
with a.build_kaggle_client() as c:response=c.kernels.kernels_api_client.get_kernel(r)
m=response.metadata
assert m.is_private and not m.enable_gpu and not m.enable_tpu and not m.enable_internet
assert m.current_version_number==1
assert list(m.dataset_data_sources)==['aohkvd/nl2sql-setup-inputs']
assert list(m.kernel_data_sources) in (['aohkvd/nl2sql-environment-cache/5'],['aohkvd/nl2sql-environment-cache'])
remote=json.loads(response.blob.source);local=json.loads((base/'deploy'/(slug+'.ipynb')).read_text())
assert [(c['cell_type'],''.join(c['source'])) for c in remote['cells']]==[(c['cell_type'],''.join(c['source'])) for c in local['cells']]
record=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),ref=ref,version=1,status=status,
 private=True,gpu_enabled=False,tpu_enabled=False,internet_enabled=False,remote_cells_match=True,
 input_dataset_verified=True,cache_source_metadata_verified=True)
(base/'current-status.json').write_text(json.dumps(record,indent=2)+'\n')
with (base/'status-history.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
print(record['checked_at_utc'],status,'private CPU/no internet; remote v1 source verified',flush=True)
