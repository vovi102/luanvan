"""Read-only source/private metadata verification after the one submission."""
import json
from datetime import datetime,timezone
from pathlib import Path
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest
base=Path(__file__).resolve().parent
plan=json.loads((base/'submission-plan-short-ref.json').read_text())
slug=plan['kernel'].split('/')[-1]
a=KaggleApi();a.authenticate()
r=ApiGetKernelRequest();r.user_name='aohkvd';r.kernel_slug=slug
with a.build_kaggle_client() as c: response=c.kernels.kernels_api_client.get_kernel(r)
m=response.metadata
remote=json.loads(response.blob.source)
local=json.loads((base/'deploy-short-ref'/(slug+'.ipynb')).read_text())
assert len(remote['cells'])==len(local['cells'])
assert [(c['cell_type'],''.join(c['source'])) for c in remote['cells']]==[(c['cell_type'],''.join(c['source'])) for c in local['cells']]
assert m.current_version_number==1 and m.is_private and m.enable_gpu and m.machine_shape=='NvidiaTeslaT4'
assert list(m.dataset_data_sources or [])==['aohkvd/nl2sql-setup-inputs']
assert list(m.kernel_data_sources or []) in (['aohkvd/nl2sql-environment-cache'],['aohkvd/nl2sql-environment-cache/5'])
record=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),version=1,all_cells_match_submitted_source=True,
    private=True,enable_gpu=True,machine_shape='NvidiaTeslaT4',input_dataset_verified=True,cache_source_verified=True)
with (base/'remote-source-verified.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
print('Remote v1 source, private T4 and input metadata verified.')
