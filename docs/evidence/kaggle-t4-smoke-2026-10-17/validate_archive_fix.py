import ast, hashlib, json, tarfile, tempfile
from pathlib import Path, PurePosixPath
base=Path(__file__).parent
archive=Path('.local/kaggle-b12-bilingual/release/input-bundle.tar.gz').resolve()
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='2aa4dac0cb4110783279c3361b4c7618ce601402ed3a40cef168adad75caa6de'

def check(notebook, expected_pass):
 nb=json.loads(notebook.read_text())
 tree=ast.parse(''.join(nb['cells'][2]['source']))
 block=next(n for n in ast.walk(tree) if isinstance(n,ast.With) and isinstance(n.items[0].context_expr,ast.Call) and ast.unparse(n.items[0].context_expr.func)=='tarfile.open')
 code=compile(ast.fix_missing_locations(ast.Module(body=[block],type_ignores=[])),'actual-notebook-archive-block','exec')
 with tempfile.TemporaryDirectory() as folder:
  workspace=Path(folder)/'input'
  try:
   exec(code,dict(archive=archive,workspace=workspace,tarfile=tarfile,PurePosixPath=PurePosixPath))
  except ValueError as exc:
   assert not expected_pass and str(exc)=='Bundle member count/size invalid',str(exc)
   print('REPRODUCED original failure against accepted archive')
   return
  assert expected_pass,'Original notebook unexpectedly passed'
  files=[p for p in workspace.rglob('*') if p.is_file()]
  assert len(files)==182
  # Exercise the real bundle/data consumer after the actual notebook extraction.
  import subprocess,os
  env={'PATH':os.environ['PATH'],'PYTHONPATH':str(workspace/'src'),'PYTHONDONTWRITEBYTECODE':'1'}
  result=subprocess.run(['/home/khoavd/WORKSPACE/LuanVan/.venv/bin/python',str(workspace/'scripts/25_kaggle_b12.py'),'preflight','--root',str(workspace),'--level','data'],env=env,text=True,capture_output=True)
  assert result.returncode==0,result.stdout+result.stderr
  payload=json.loads(result.stdout)
  assert payload['status']=='data_ready' and payload['training_records']==7208
  print('PASS: actual corrected extraction (182 files) and native EN/VI data preflight (7208 train)')

if __name__=='__main__':
 import sys
 check(Path(sys.argv[1]),sys.argv[2]=='pass')
