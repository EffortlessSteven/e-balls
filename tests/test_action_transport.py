"""Run real shell glue against synthetic Git/collector/renderer boundary stubs."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/action_render.sh'
STUB = r'''#!/usr/bin/env python3
import json,os,pathlib,sys
name=pathlib.Path(sys.argv[0]).name
log=pathlib.Path(os.environ['HANDOFF_LOG'])
with log.open('a') as f:
    f.write(json.dumps({'program':name,'args':sys.argv[1:],
        'credentials':{k:os.environ[k] for k in ('EB_TOKEN','GH_TOKEN','GITHUB_TOKEN') if k in os.environ}})+'\n')
if name=='git':
    if sys.argv[1]=='clone': pathlib.Path(sys.argv[-1]).mkdir()
    sys.exit(0)
args=dict(zip(sys.argv[1::2],sys.argv[2::2]))
if name=='e-balls-collect':
    if os.environ.get('FAIL_COLLECT'): sys.exit(42)
    pathlib.Path(args['--out']).write_text('{"schema_version":1}')
    if '--avatar-out' in args: pathlib.Path(args['--avatar-out']).write_bytes(b'fixture-avatar')
else:
    out=pathlib.Path(args['--out']); out.mkdir()
    (out/'embed.md').write_text('owned by Rust renderer boundary\n')
    (out/'handoff.json').write_text(json.dumps(args))
    pathlib.Path(os.environ['GITHUB_OUTPUT']).write_text('owned_by_renderer=yes\n')
'''

class ActionTransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in ['git','e-balls','e-balls-collect']:
            path=self.root/('bin' if name=='git' else 'target/release')/name
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text(STUB); path.chmod(0o755)
        (self.root/'avatar.png').write_bytes(b'synthetic portrait fixture')
        (self.root/'data.json').write_text('{}')
        self.env={**os.environ,
            'PATH':str(self.root/'bin')+os.pathsep+os.environ['PATH'],
            'GITHUB_ACTION_PATH':str(self.root),'GITHUB_OUTPUT':str(self.root/'github-output'),
            'RUNNER_TEMP':str(self.root),'HANDOFF_LOG':str(self.root/'calls.jsonl'),
            'EB_REPOSITORY':'fixture/repo','EB_REF':'','EB_PROJECT':'',
            'EB_TOKEN':'synthetic-token','GH_TOKEN':'synthetic-ambient','GITHUB_TOKEN':'synthetic-ambient',
            'EB_SINCE':'7d','EB_END':'','EB_LETTER':'e','EB_DATA':str(self.root/'data.json'),
            'EB_AVATAR':str(self.root/'avatar.png'),'EB_FORMAT':'both',
            'EB_OUTPUT':str(self.root/'output'),'EB_ASSET_BASE':'https://example.test/media'}

    def run_wrapper(self,**changes):
        return subprocess.run(['bash',str(SCRIPT)],env={**self.env,**changes},
            capture_output=True,text=True,timeout=15)

    def calls(self):
        path=self.root/'calls.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_renderer_owns_metadata_and_output_records(self):
        p=self.run_wrapper(); self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual((self.root/'output/embed.md').read_text(),'owned by Rust renderer boundary\n')
        self.assertEqual((self.root/'github-output').read_text(),'owned_by_renderer=yes\n')
        args=json.loads((self.root/'output/handoff.json').read_text())
        self.assertEqual(args['--asset-base-url'],'https://example.test/media')
        self.assertEqual([c['program'] for c in self.calls()],['e-balls'])

    def test_renderer_does_not_inherit_github_credentials(self):
        p=self.run_wrapper(); self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.calls()[-1]['credentials'],{})

    def test_existing_output_rejected_before_source_network(self):
        (self.root/'output').mkdir(); (self.root/'output/keep').write_text('keep')
        p=self.run_wrapper(EB_DATA=''); self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.calls(),[]); self.assertEqual((self.root/'output/keep').read_text(),'keep')

    def test_newlines_rejected_before_source_network(self):
        for suffix in ['\nforged=yes','\rforged=yes']:
            with self.subTest(suffix=suffix):
                p=self.run_wrapper(EB_DATA='',EB_OUTPUT=str(self.root/'output')+suffix)
                self.assertNotEqual(p.returncode,0); self.assertEqual(self.calls(),[])

    def test_broken_destination_symlink_is_not_overwritten(self):
        (self.root/'output').symlink_to(self.root/'missing')
        p=self.run_wrapper(EB_DATA=''); self.assertNotEqual(p.returncode,0)
        self.assertEqual(self.calls(),[]); self.assertTrue((self.root/'output').is_symlink())

    def test_missing_override_rejected_before_source_network(self):
        p=self.run_wrapper(EB_DATA='',EB_AVATAR=str(self.root/'missing'))
        self.assertNotEqual(p.returncode,0); self.assertEqual(self.calls(),[])

    def test_saved_data_requires_avatar(self):
        p=self.run_wrapper(EB_AVATAR=''); self.assertNotEqual(p.returncode,0)
        self.assertIn('saved data requires an explicit avatar',p.stderr); self.assertEqual(self.calls(),[])

    def test_source_git_has_no_token_and_auto_avatar_stays_automatic(self):
        p=self.run_wrapper(EB_DATA='',EB_AVATAR=''); self.assertEqual(p.returncode,0,p.stderr)
        calls=self.calls(); self.assertTrue(any(c['program']=='git' for c in calls))
        for call in calls:
            if call['program']=='git': self.assertEqual(call['credentials'],{})
        collector=next(c for c in calls if c['program']=='e-balls-collect')
        self.assertIn('--avatar-out',collector['args'])
        self.assertEqual(collector['credentials']['GITHUB_TOKEN'],'synthetic-token')
        self.assertEqual(list(self.root.glob('e-balls-source.*')),[])

    def test_failed_collection_cleans_source_without_renderer(self):
        p=self.run_wrapper(EB_DATA='',EB_AVATAR='',FAIL_COLLECT='1')
        self.assertEqual(p.returncode,42)
        self.assertFalse(any(c['program']=='e-balls' for c in self.calls()))
        self.assertEqual(list(self.root.glob('e-balls-source.*')),[])
        self.assertFalse((self.root/'output').exists())

if __name__=='__main__': unittest.main()
