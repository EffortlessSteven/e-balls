import hashlib,json,pathlib,subprocess
root=pathlib.Path('.'); ev=root/'examples/perl-lsp-2026-10-04/evidence'
expected=json.loads((ev/'tested-inputs.json').read_text())
for p,sha in expected.items():
 assert hashlib.sha256((root/p).read_bytes()).hexdigest()==sha,p
print(f'All {len(expected)} tracked source, test, dependency, configuration and asset hashes still match tested inputs.')
artifacts={}
for p in ['target/release/e-balls','target/release/release-balls']:
 artifacts[p]=hashlib.sha256((root/p).read_bytes()).hexdigest()
(ev/'binary-hashes.json').write_text(json.dumps(artifacts,indent=2)+'\n')
print(json.dumps(artifacts,indent=2))
