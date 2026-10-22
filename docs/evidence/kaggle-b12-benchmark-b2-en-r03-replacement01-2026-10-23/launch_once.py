"""Fresh quota/private-input checks, then one explicitly authorized submission only."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiGetKernelRequest

base = Path(__file__).resolve().parent
root = base.parents[1]
plan = json.loads((base/'submission-plan.json').read_text())
ref = plan['kernel']; slug = ref.split('/')[-1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def save(name, value):
    with (base/name).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')

def get_kernel(api, name):
    req = ApiGetKernelRequest();req.user_name='aohkvd';req.kernel_slug=name
    with api.build_kaggle_client() as client:
        return client.kernels.kernels_api_client.get_kernel(req)

assert not (base/'submission-intent.json').exists(), 'A request may already exist: inspect remote state; never push twice.'
verification = json.loads((base/'test-verification.json').read_text())
assert verification['full_suite_exit_code'] == 0
assert sha(base/'full-suite.log') == verification['full_suite_log_sha256']
assert sha(root/'scripts/27_kaggle_b12_benchmark.py') == plan['driver_sha256']
notebook_path=base/'deploy'/(slug+'.ipynb')
assert sha(notebook_path) == plan['notebook_sha256']
api = KaggleApi();api.authenticate()
prior=json.loads((root/'.local/kaggle-b12-benchmark-20261022-b2-vi-r03/quota-before.json').read_text())['prior_statuses']
prior['nl2sql-b12-benchmark-20261022-b2-vi-r03']='COMPLETE'
statuses={name:api.kernels_status('aohkvd/'+name).status.name for name in prior}
assert statuses==prior, 'Prior session state changed; do not launch.'
cache=get_kernel(api,'nl2sql-environment-cache').metadata
assert cache.current_version_number==5 and cache.is_private
validation=get_kernel(api,'nl2sql-b12-setup-validation-20261022-v02').metadata
assert validation.current_version_number==1 and validation.is_private
matches=[k for k in api.kernels_list(mine=True, search=slug, page_size=100)
    if k.ref.strip('/') in (ref,'code/'+ref)]
assert not matches, 'Exact target already exists: inspect it without submitting.'
with api.build_kaggle_client() as client:
    quota=client.kernels.kernels_api_client.get_accelerator_quota_statistics().gpu_quota
used=quota.time_used.total_seconds()/3600
reserved=quota.time_reserved.total_seconds()/3600
total=quota.total_time_allowed.total_seconds()/3600
remaining=total-used-reserved
assert remaining>=4 and reserved==0 and not quota.is_pay_to_scale_enabled
record=dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),gpu_used_hours=used,
    gpu_reserved_hours=reserved,gpu_total_hours=total,gpu_remaining_hours=remaining,
    is_pay_to_scale_enabled=quota.is_pay_to_scale_enabled,authorized_session_cap_seconds=7200,
    conservative_two_device_hours_required=4,prior_statuses=statuses,cache_version=5,
    cache_private_complete=True,validation_v1_private_complete=True,matching_kernel_exists=False,
    failed_en_setup_preserved=True,replacement_explicitly_authorized=True)
save('quota-before.json',record)
print('Fresh quota:',round(remaining,5),'hours; none reserved; pay-to-scale off. Private inputs/cache v5 verified.',flush=True)
save('submission-intent.json',dict(request_started_at_utc=datetime.now(timezone.utc).isoformat(),ref=ref,
    single_push_only=True,uncertain_response_requires_read_only_inspection=True))
try:
    response=api.kernels_push(str(base/'deploy'),timeout='7200',acc='NvidiaTeslaT4')
except Exception as exc:
    save('submission-request-error.json',dict(error_type=type(exc).__name__,retry_performed=False))
    raise SystemExit('Submission response uncertain; recorded exception type. Inspect existing ref; do not retry.')
record=dict(submitted_at_utc=datetime.now(timezone.utc).isoformat(),ref=response.ref,url=response.url,
    version=response.version_number,kernel_id=response.kernel_id,error=response.error,
    invalid_dataset_sources=list(response.invalid_dataset_sources or []),
    invalid_kernel_sources=list(response.invalid_kernel_sources or []),
    invalid_model_sources=list(response.invalid_model_sources or []),
    private_requested=True,platform_timeout_seconds=7200,machine_shape='NvidiaTeslaT4')
save('api-submitted-v1.json',record)
assert not response.error and not any(record[k] for k in ['invalid_dataset_sources','invalid_kernel_sources','invalid_model_sources'])
assert response.version_number==1
print('Submitted once:',response.url,'version',response.version_number,'kernel',response.kernel_id,flush=True)
