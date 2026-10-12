"""Offline checks for immutable Action references and intentionally idle workflows."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
USES = re.compile(r"^\s*(?:- )?uses:\s*([^\s#]+)", re.MULTILINE)


def remote_pin_errors(text):
    errors = []
    for ref in USES.findall(text):
        # Local calls and the repository's own consumer examples follow its main.
        if ref.startswith('./') or ref.startswith('EffortlessSteven/e-balls@'):
            continue
        if not re.fullmatch(r'[^@\s]+@[0-9a-f]{40}', ref):
            errors.append(ref)
    return errors


def run_block(text, marker):
    """Read one known Bash block without adding a YAML dependency to CI."""
    section = text.split(marker, 1)[1].split('      run: |\n', 1)[1]
    lines = []
    for line in section.splitlines():
        if line.strip() and not line.startswith('        '):
            break
        lines.append(line)
    return textwrap.dedent('\n'.join(lines)) + '\n'


class WorkflowCloseoutTests(unittest.TestCase):
    def test_external_actions_are_pinned_everywhere_they_execute(self):
        files = [ROOT/'action.yml', ROOT/'legacy/action.yml']
        files += list((ROOT/'.github/workflows').glob('*.yml'))
        files += list((ROOT/'examples').glob('*.yml'))
        self.assertGreaterEqual(len(files), 7)
        for path in files:
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertEqual(remote_pin_errors(path.read_text()), [])

    def test_pin_scanner_rejects_moving_tags_and_accepts_local_calls(self):
        self.assertEqual(remote_pin_errors('- uses: actions/cache@v4'), ['actions/cache@v4'])
        self.assertEqual(remote_pin_errors('      uses: actions/checkout@main'), ['actions/checkout@main'])
        self.assertEqual(remote_pin_errors('- uses: ./\n- uses: EffortlessSteven/e-balls@main'), [])
        self.assertEqual(remote_pin_errors('- uses: actions/cache/restore@' + 'a'*40 + ' # v4'), [])

    def test_rust_installers_have_explicit_version_after_pinning(self):
        for name in ['action.yml', 'legacy/action.yml', '.github/workflows/ci.yml']:
            text = (ROOT/name).read_text()
            blocks = re.split(r'(?m)^\s*- uses: dtolnay/rust-toolchain@', text)[1:]
            self.assertEqual(len(blocks), 1, name)
            for block in blocks:
                step = re.split(r'\n\s*- (?:id|name|uses):', block, maxsplit=1)[0]
                self.assertRegex(step, r'^[0-9a-f]{40} # master; Rust 1\.88\.0\n')
                self.assertIn("toolchain: '1.88.0'", step)

    def test_no_scheduled_or_event_dispatched_background_jobs(self):
        workflows = ROOT/'.github/workflows'
        self.assertEqual({p.name for p in workflows.glob('*.yml')}, {'ci.yml', 'demo.yml'})
        for path in workflows.glob('*.yml'):
            text = path.read_text()
            self.assertNotRegex(text, r'(?m)^\s*(schedule|repository_dispatch|workflow_run|pull_request_target):')
            self.assertIn('  contents: read\n', text)
            self.assertNotIn('contents: write', text)
        demo = (workflows/'demo.yml').read_text()
        events = demo.split('\non:\n', 1)[1].split('\npermissions:', 1)[0]
        self.assertEqual(re.findall(r'^  ([a-z_]+):', events, re.MULTILINE), ['workflow_dispatch'])
        self.assertIn('timeout-minutes: 10', demo)
        self.assertIn('cancel-in-progress: true', demo)
        self.assertIn('retention-days: 7', demo)

    def test_expensive_ci_stays_manual_and_docs_only_remain_ignored(self):
        ci = (ROOT/'.github/workflows/ci.yml').read_text()
        self.assertEqual(ci.count('    paths-ignore:\n'), 2)
        for path in ['README.md', 'AGENTS.md', "'docs/**'", 'LICENSE']:
            self.assertEqual(ci.count('      - '+path+'\n'), 2)
        self.assertIn('    branches: [main]\n', ci)
        self.assertNotIn('feat/e-balls', ci)
        self.assertIn("  action-smoke:\n    if: github.repository == 'EffortlessSteven/e-balls' && github.event_name == 'workflow_dispatch'", ci)
        self.assertIn("      - name: Render the pinned perl-lsp example\n        if: github.event_name == 'workflow_dispatch'", ci)

    def test_demo_inputs_map_to_current_action(self):
        demo = (ROOT/'.github/workflows/demo.yml').read_text()
        inputs = demo.split('    inputs:\n', 1)[1].split('\npermissions:', 1)[0]
        declared = set(re.findall(r'^      ([a-z_]+):', inputs, re.MULTILINE))
        call = demo.split('      - uses: ./\n', 1)[1].split('      - name:', 1)[0]
        mappings = dict(re.findall(r'^          ([a-z-]+): \$\{\{ inputs\.([a-z_]+) \}\}', call, re.MULTILINE))
        self.assertEqual(set(mappings.values()), declared)
        self.assertEqual(mappings['case-sensitive'], 'case_sensitive')
        self.assertEqual(mappings['text'], 'text')
        action = (ROOT/'action.yml').read_text().split('\ninputs:\n', 1)[1].split('\noutputs:', 1)[0]
        accepted = set(re.findall(r'^  ([a-z-]+):', action, re.MULTILINE))
        self.assertLessEqual(set(mappings), accepted)
        self.assertNotRegex(demo, r'^          (metric|releases|match):')

    def test_legacy_cache_uses_repo_root_and_canonical_binary_path(self):
        legacy = (ROOT/'legacy/action.yml').read_text()
        script = run_block(legacy, '    - id: binary-key\n')
        script = script.replace('${{ runner.os }}', 'Linux').replace('${{ runner.arch }}', 'X64')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)/'fixture with spaces'
            for path, content in {
                'Cargo.toml': '[package]\nname="fixture"\n', 'Cargo.lock': 'version=4\n',
                'src/lib.rs': '', 'assets/manifest.json': '{}',
                'legacy/action.yml': legacy,
            }.items():
                dest=root/path; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(content)
            (root/'scripts').mkdir()
            shutil.copy(ROOT/'scripts/action_cache_key.sh', root/'scripts/action_cache_key.sh')
            output = Path(directory)/'outputs'
            env = {**os.environ, 'GITHUB_ACTION_PATH': str(root)+'/./legacy', 'GITHUB_OUTPUT': str(output)}
            subprocess.run(['bash', '-c', script], env=env, check=True, capture_output=True, timeout=10)
            records = dict(line.split('=',1) for line in output.read_text().splitlines())
            self.assertEqual(records['path'], str(root/'target/release/release-balls'))
            original = records['key']
            (root/'assets/manifest.json').write_text('{"changed":true}')
            output.unlink()
            subprocess.run(['bash', '-c', script], env=env, check=True, capture_output=True, timeout=10)
            updated = dict(line.split('=',1) for line in output.read_text().splitlines())
            self.assertNotEqual(original, updated['key'])
            (root/'Cargo.lock').unlink()
            failed = subprocess.run(['bash', '-c', script], env=env, capture_output=True, timeout=10)
            self.assertNotEqual(failed.returncode, 0)

    def test_legacy_build_only_builds_its_binary(self):
        legacy = (ROOT/'legacy/action.yml').read_text()
        build = run_block(legacy, '    - name: Build Rust binary on cache miss\n')
        self.assertIn('set -euo pipefail', build)
        self.assertIn('--manifest-path "$GITHUB_ACTION_PATH/../Cargo.toml" --bin release-balls', build)

    def test_demo_media_check_rejects_an_empty_directory(self):
        demo = (ROOT/'.github/workflows/demo.yml').read_text()
        block = demo.split('      - name: Check generated media\n',1)[1]
        script = textwrap.dedent(block.split('        run: |\n',1)[1].split('      - uses:',1)[0])
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(['bash', '-c', script], env={**os.environ,'MEDIA_DIR':directory}, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode,0)

    def test_demo_media_check_accepts_actual_compiled_exports(self):
        binary = os.environ.get('EBALLS_BIN')
        if not binary:
            self.skipTest('Set EBALLS_BIN to a compiled renderer')
        demo = (ROOT/'.github/workflows/demo.yml').read_text()
        block = demo.split('      - name: Check generated media\n',1)[1]
        script = textwrap.dedent(block.split('        run: |\n',1)[1].split('      - uses:',1)[0])
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory); data=parent/'data.json'; out=parent/'media'
            data.write_text(json.dumps({'schema_version':1,'title':'Text matches','footer':'fixture','unit':'matches',
                'rows':[{'label':'Monday','count':3},{'label':'Tuesday','count':0}]}))
            env = {**os.environ,'GITHUB_OUTPUT':str(parent/'action-output')}
            subprocess.run([str(Path(binary).resolve()),'--data',str(data),'--avatar',str(ROOT/'examples/perl-lsp-2026-10-04-teal/avatar.png'),
                '--format','both','--duration','0.2','--width','320','--out',str(out)],
                env=env, check=True, capture_output=True, timeout=45)
            subprocess.run(['bash','-c',script],env={**env,'MEDIA_DIR':str(out)},check=True,capture_output=True,timeout=20)

if __name__ == '__main__':
    unittest.main()
