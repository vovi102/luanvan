"""Offline source/provenance preparation. Does not call Kaggle or run inference."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import nbformat
from nl2sparql.kaggle.bundle import preflight_data, verify_bundle

ROOT = Path.cwd()
BASE = ROOT / '.local/kaggle-b12-benchmark-20261023-b2-en-r03-replacement01'
SLUG = 'nl2sql-b12-benchmark-20261023-b2-en-r03-replacement01'
PARENT = 'b12-envi-20261018-c01'
CAMPAIGN = PARENT + '-replacement01'
SESSION = 's11-b2-en-r03-replacement01'
SCRIPT = ROOT / 'scripts/27_kaggle_b12_benchmark.py'
ACCEPTED = ROOT / '.local/benchmark-preparation/driver-accepted-input'
ARCHIVE = ROOT.parent / 'b12-bilingual-consumer/.local/kaggle-b12-bilingual/release/input-bundle.tar.gz'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')

spec = importlib.util.spec_from_file_location('driver', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert sha(ARCHIVE) == m.BUNDLE_SHA256
manifest = verify_bundle(ACCEPTED)
assert len(manifest['files']) == 181
# Immutable inference implementation remains byte-identical to accepted release.
for folder in ('src', 'scripts', 'configs'):
    for p in (ACCEPTED / folder).rglob('*'):
        if p.is_file() and p.suffix != '.pyc' and '__pycache__' not in p.parts:
            assert sha(ROOT / p.relative_to(ACCEPTED)) == sha(p), str(p)
data = preflight_data(ACCEPTED)
assert data['status'] == 'data_ready'
assert data['training_records'] == 7208
assert data['english_records'] == data['vietnamese_records'] == 100

last = ROOT / '.local/kaggle-b12-benchmark-20261022-b2-vi-r03/downloaded'
ledger = json.loads(next(last.rglob('campaign-ledger.json')).read_text())
prior = ledger['attempted_run_ids']
assert len(prior) == len(set(prior)) == 12
assert PARENT + '-b2-en-r03' in prior
settings = dict(allow_preparation=True, allow_env_install=True, allow_real_inference=True,
    campaign_id=CAMPAIGN, session_id=SESSION, baseline='b2', language='en', replicate=3,
    prior_attempts=prior, prior_completeness_reviewed=True, replacement_of=PARENT+'-b2-en-r03')
assert m.validate_attempts(settings) == dict(parent_campaign_id=PARENT, replacement_of=PARENT+'-b2-en-r03')
output = Path('/kaggle/working/b12-benchmark-' + CAMPAIGN + '/runs')
home = Path('/kaggle/input/cache-v5/hf-home') # comparison only; actual path discovered and hashed on mount
item = m.select_process(m.campaign_plan(ACCEPTED,CAMPAIGN,home,output),'b2','en',3,prior)
original = m.select_process(m.campaign_plan(ACCEPTED,PARENT,home,output),'b2','en',3)
assert item['run_id'] == CAMPAIGN+'-b2-en-r03'
assert item['run_id'] not in prior
assert [a.replace(item['run_id'], original['run_id']) for a in item['argv']] == original['argv']
assert {k:v for k,v in item['config'].items() if k!='campaign_id'} == {k:v for k,v in original['config'].items() if k!='campaign_id'}
assert '--limit' not in item['argv']

old = subprocess.run(['git','show','b029943:scripts/27_kaggle_b12_benchmark.py'], capture_output=True,text=True,check=True).stdout
old_ast = {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(old).body if isinstance(n,ast.FunctionDef)}
new_ast = {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(SCRIPT.read_text()).body if isinstance(n,ast.FunctionDef)}
unchanged = ['digest','write_new','discover_inputs','extract_inputs','runtime_config','campaign_plan','select_process','run_logged','run_timed_stage','cleanup_scratch','check_complete','main']
assert all(old_ast[n] == new_ast[n] for n in unchanged)
assert (m.SETUP_CAP,m.PROCESS_CAP,m.SESSION_CAP,m.CLEANUP_RESERVE)==(1620,5400,7200,120)

nb=nbformat.read(ROOT/'notebooks/16_kaggle_b12_benchmark.ipynb',as_version=4)
nbformat.validate(nb)
ns={};exec(next(c.source for c in nb.cells if c.id=='settings'),ns)
assert all(ns[k] is False for k in ['ALLOW_PREPARATION','ALLOW_ENV_INSTALL','ALLOW_REAL_INFERENCE'])
assert ns['REPLACEMENT_OF'] is None
for c in nb.cells:
    if c.cell_type=='code':
        assert c.execution_count is None and c.outputs==[]
    if c.id=='settings':
        values=dict(ALLOW_PREPARATION=True,ALLOW_ENV_INSTALL=True,ALLOW_REAL_INFERENCE=True,
            CAMPAIGN_ID=CAMPAIGN,SESSION_ID=SESSION,BASELINE='b2',LANGUAGE='en',REPLICATE=3,
            PRIOR_ATTEMPTS=prior,PRIOR_COMPLETENESS_REVIEWED=True,REPLACEMENT_OF=PARENT+'-b2-en-r03')
        c.source='\n'.join(k+' = '+repr(v) for k,v in values.items())+'\n'
    if c.id=='driver-source':
        ns={};exec(c.source,ns)
        assert ns['DRIVER_SOURCE']==SCRIPT.read_text()
        assert ns['DRIVER_SHA256']==sha(SCRIPT)
nbformat.validate(nb)
deploy=BASE/'deploy';deploy.mkdir(exist_ok=False)
nbpath=deploy/(SLUG+'.ipynb');nbformat.write(nb,nbpath)
metadata=dict(id='aohkvd/'+SLUG,title=SLUG,code_file=nbpath.name,language='python',kernel_type='notebook',
    is_private=True,enable_gpu=True,enable_tpu=False,enable_internet=True,
    dataset_sources=['aohkvd/nl2sql-setup-inputs'],kernel_sources=['aohkvd/nl2sql-environment-cache/5'],
    competition_sources=[],model_sources=[],machine_shape='NvidiaTeslaT4')
save(deploy/'kernel-metadata.json',metadata)
save(BASE/'settings.json',settings)
save(BASE/'offline-verification.json',dict(status='offline_checks_passed',accepted_bundle_sha256=m.BUNDLE_SHA256,
    accepted_payload_files=181,immutable_inference_source_and_configs_byte_identical=True,
    data_preflight=data,unchanged_operational_functions=unchanged,selected_native_plan=item,
    normalized_native_argv_identical=True,config_diff_keys=['campaign_id'],driver_sha256=sha(SCRIPT),
    disabled_default_notebook=True,no_inference_executed=True))
save(BASE/'submission-plan.json',dict(kernel='aohkvd/'+SLUG,campaign_id=CAMPAIGN,parent_campaign_id=PARENT,
    session_id=SESSION,run_id=item['run_id'],replacement_of=settings['replacement_of'],baseline='b2',language='en',replicate=3,
    cases=100,notebook_sha256=sha(nbpath),driver_sha256=sha(SCRIPT),setup_cap_seconds=1620,native_cap_seconds=5400,
    platform_session_cap_seconds=7200,prior_attempted_run_ids=prior,prior_successful_native_processes=11,prior_failed_setup_slots=1,
    authorization='User approved preparing and executing one full B2 EN r03 replacement under a distinct ID, preserving original failure evidence.',
    identity_note='Replacement marker precedes baseline/language/replicate so immutable native runner can generate the new ID; proposal suffix placement superseded.',
    prior_completeness_reviewed_flag=True,review_exception='Eleven genuine native runs and one retained setup failure reviewed; failure is not a successful completeness receipt.',
    research_semantics_changed=False,native_review_live_flags_changed=False,preserve_original_failure=True,splice_partial_outputs=False,
    expected_campaign_if_success='12 successful native processes across original plus replacement namespace and one retained setup failure, each language/run N=100 separately; scientific blockers retained.'))
print('Offline bundle, native argv/config, notebook, provenance and source checks passed. Deployment prepared, not submitted.')
