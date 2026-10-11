import subprocess,sys,json,hashlib,os,datetime
from pathlib import Path
root=Path('/home/vercel-sandbox/workspace/repos/github.com/effortlesssteven/e-balls')
evidence=Path('/tmp/e-balls-evidence'); evidence.mkdir(exist_ok=True)
record=Path('/home/vercel-sandbox/workspace/workspace-context/validation-record.md')
name=sys.argv[1]; command=sys.argv[2:]
files=subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'],cwd=root).decode().split('\0')
inputs={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(set(files)) if p and (root/p).is_file() and not p.startswith('examples/perl-lsp-2026-10-04-teal/') and '__pycache__' not in p}
identity=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
(evidence/f'inputs-{identity}.json').write_text(json.dumps(inputs,indent=2)+'\n')
meta={'command':command,'cwd':str(root),'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'inputs':f'inputs-{identity}.json','started':datetime.datetime.now(datetime.timezone.utc).isoformat(),'environment':'mise Rust 1.88.0 / Python 3.12.15; FFmpeg 7.0.2 static libx264; system FreeType 26.1.20 pkg-config; synthetic CLI fixtures; real source pinned separately'}
with record.open('a') as f:f.write(f'\n- {name}: outstanding, command `{command}`, input identity `{identity}`. Required acceptance check; no prior matching result.\n')
with (evidence/f'{name}.log').open('w') as log:
 proc=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
meta['exit_code']=proc.returncode;meta['result']='passed' if proc.returncode==0 else 'failed'
(evidence/f'{name}.json').write_text(json.dumps(meta,indent=2)+'\n')
with record.open('a') as f:f.write(f'  - {meta["result"]}, exit {proc.returncode}; receipt `/tmp/e-balls-evidence/{name}.json`, log alongside; cwd `{root}`, revision `{meta["revision"]}`.\n')
print(name,meta['result'],proc.returncode,flush=True)
print((evidence/f'{name}.log').read_text()[-3500:],flush=True)
sys.exit(proc.returncode)
