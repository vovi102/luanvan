"""Fetch saved campaign evidence only, with bounded reads and no signed URL storage."""
import json
from pathlib import Path,PurePosixPath
import requests
from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kernels.types.kernels_api_service import ApiListKernelSessionOutputRequest
base=Path(__file__).parent
slug='nl2sql-cpu-smoke-20261023-d03'
prefix='cpu-smoke-d02'
a=KaggleApi();a.authenticate()
status=a.kernels_status('aohkvd/'+slug).status.name
if status not in ('COMPLETE','ERROR','CANCELLED'):
 print('Saved export deferred; worker status:',status)
 raise SystemExit(3)
items=[];page=None
while True:
 req=ApiListKernelSessionOutputRequest();req.user_name='aohkvd';req.kernel_slug=slug;req.page_size=100
 if page:req.page_token=page
 with a.build_kaggle_client() as c:r=c.kernels.kernels_api_client.list_kernel_session_output(req)
 items.extend(r.files or []);page=r.next_page_token
 if not page:break
output=base/'downloaded';output.mkdir(exist_ok=True)
records=[];omitted=[]
for item in items:
 path=PurePosixPath(item.file_name)
 if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe remote output path')
 if not path.parts or path.parts[0]!=prefix:continue
 if path.suffix not in ('.json','.jsonl','.log','.py','.npz','.lock'):
  omitted.append(str(path));continue
 with requests.Session() as session:
  session.trust_env=False
  response=session.get(item.url,stream=True,timeout=(10,60))
  if response.status_code!=200:
   code=response.status_code;response.close();raise RuntimeError('Evidence download HTTP '+str(code))
  payload=bytearray()
  for chunk in response.iter_content(65536):
   payload.extend(chunk)
   if len(payload)>32*1024*1024:
    response.close();raise ValueError('Evidence file exceeded bounded size')
  response.close()
 target=output.joinpath(*path.parts);target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():
  if target.read_bytes()!=payload:raise ValueError('Refuse changed saved artifact')
 else:
  with target.open('xb') as f:f.write(payload)
 records.append({'name':str(path),'bytes':len(payload)})
record={'worker_status':status,'downloaded':records,'omitted':omitted,'signed_urls_persisted':False,'model_payloads_downloaded':False}
(base/'download-record.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'status':status,'downloaded_files':len(records),'bytes':sum(r['bytes'] for r in records),'omitted':omitted}))
