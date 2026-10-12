"""Compare paired and separate exports using the compiled renderer."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class RenderPairTests(unittest.TestCase):
    def setUp(self):
        binary=os.environ.get('EBALLS_BIN')
        if not binary:
            self.skipTest('Set EBALLS_BIN to a compiled renderer')
        self.binary=str(Path(binary).resolve())
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.avatar=ROOT/'examples/perl-lsp-2026-10-04-teal/avatar.png'
        self.data=self.root/'data.json'
        self.data.write_text(json.dumps({'schema_version':1,'title':'e','footer':'source',
            'unit':"e's",'rows':[{'label':'Sunday','count':20},{'label':'Monday','count':1}]}))

    def export(self,fmt,name):
        out=self.root/name
        subprocess.run([self.binary,'--data',str(self.data),'--avatar',str(self.avatar),
            '--format',fmt,'--out',str(out),'--width','320','--duration','0.4','--threads','2'],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=45,
            env={**os.environ,'GITHUB_OUTPUT':str(self.root/'github-output')})
        return out

    def test_pair_matches_separate_media_exactly(self):
        pair=self.export('both','pair')
        for fmt in ['mp4','gif']:
            single=self.export(fmt,fmt)
            self.assertEqual((pair/f'e-balls.{fmt}').read_bytes(),(single/f'e-balls.{fmt}').read_bytes())
            subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(pair/f'e-balls.{fmt}'),'-f','null','-'],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=30)
        self.assertEqual([f['path'] for f in json.loads((pair/'manifest.json').read_text())['files']],
            ['e-balls.mp4','e-balls.gif'])

if __name__=='__main__': unittest.main()
