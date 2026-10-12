"""Compiled regressions for Rust-owned embeds and GitHub output records."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class RenderMetadataTests(unittest.TestCase):
    def setUp(self):
        binary=os.environ.get('EBALLS_BIN')
        if not binary: self.skipTest('Set EBALLS_BIN to the compiled candidate renderer')
        self.binary=str(Path(binary).resolve())
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.output=self.root/'out'; self.github=self.root/'github-output'
        self.data=self.root/'data.json'
        self.data.write_text(json.dumps({'schema_version':1,'title':'e','footer':'source','unit':"e's",
            'rows':[{'label':'Sunday','count':20},{'label':'Monday','count':1}]}))

    def invoke(self,*extra,**env):
        return subprocess.run([self.binary,'--data',str(self.data),'--avatar',
            str(ROOT/'examples/perl-lsp-2026-10-04-teal/avatar.png'),
            '--format','both','--out',str(self.output),'--width','320','--duration','0.4',*extra],
            env={**os.environ,'GITHUB_OUTPUT':str(self.github),**env},capture_output=True,text=True,timeout=45)

    def test_embeds_and_four_outputs_are_published_together(self):
        p=self.invoke('--asset-base-url','https://example.test/clip(1)/')
        self.assertEqual(p.returncode,0,p.stderr)
        records=dict(line.split('=',1) for line in self.github.read_text().splitlines())
        self.assertEqual(set(records),{'directory','markdown','manifest','data'})
        for name in ['markdown','manifest','data']: self.assertTrue(Path(records[name]).is_file())
        text=(self.output/'embed.md').read_text()
        self.assertIn('https://example.test/clip%281%29/e-balls.gif',text)
        self.assertIn('https://example.test/clip%281%29/e-balls.mp4',text)
        self.assertEqual(json.loads((self.output/'manifest.json').read_text())['markdown'],'embed.md')

    def test_failed_encoder_does_not_publish_action_outputs(self):
        empty=self.root/'empty'; empty.mkdir()
        p=self.invoke(PATH=str(empty))
        self.assertNotEqual(p.returncode,0)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.github.exists() and self.github.read_text())
        self.assertEqual(list(self.root.glob('.e-balls-*')),[])

    def test_invalid_metadata_does_not_create_output(self):
        p=self.invoke('--asset-base-url','javascript:alert(1)')
        self.assertNotEqual(p.returncode,0)
        self.assertIn('asset-base-url',p.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.github.exists() and self.github.read_text())

if __name__=='__main__': unittest.main()
