"""Cache-input fixtures; these tests do not claim to execute GitHub Actions."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/action_cache_key.sh'

class ActionCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'fixture'
        for path, content in {
            'Cargo.toml': '[package]\nname="fixture"\n', 'Cargo.lock': 'version=4\n',
            'src/lib.rs': 'pub mod render;\n', 'src/bin/e-balls.rs': 'fn main() {}\n',
            'assets/font.fixture': 'synthetic bytes, not a font',
            'assets/plex-manifest.json': '{"revision":"one"}\n',
        }.items():
            file = self.root/path; file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content)

    def digest(self, root=None, extra_env=None):
        return subprocess.check_output(['bash', str(SCRIPT), str(root or self.root)],
            env={**os.environ, **(extra_env or {})}, text=True).strip()

    def test_stable_and_ignores_clone_location(self):
        other = Path(self.temp.name)/'another path'; shutil.copytree(self.root, other)
        self.assertEqual(self.digest(), self.digest(other))
        self.assertRegex(self.digest(), r'^[a-f0-9]{64}$')

    def test_embedded_json_change_invalidates(self):
        before=self.digest(); (self.root/'assets/plex-manifest.json').write_text('{"revision":"two"}')
        self.assertNotEqual(before, self.digest())

    def test_nested_rust_change_invalidates(self):
        file=self.root/'src/runtime/nested.rs'; file.parent.mkdir()
        before=self.digest(); file.write_text('pub fn run() {}')
        self.assertNotEqual(before, self.digest())

    def test_same_contents_different_path_invalidates(self):
        before=self.digest(); (self.root/'assets/font.fixture').rename(self.root/'assets/renamed.fixture')
        self.assertNotEqual(before, self.digest())

    def test_lockfile_change_invalidates(self):
        before=self.digest(); (self.root/'Cargo.lock').write_text('version=4\n# revision')
        self.assertNotEqual(before, self.digest())

    def test_optional_build_configuration_invalidates(self):
        for path in ['build.rs', 'rust-toolchain.toml', '.cargo/config.toml', 'action.yml']:
            with self.subTest(path=path):
                before=self.digest(); file=self.root/path; file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('test input'); self.assertNotEqual(before, self.digest())

    def test_environment_build_flags_invalidate(self):
        self.assertNotEqual(self.digest(extra_env={'RUSTFLAGS':''}), self.digest(extra_env={'RUSTFLAGS':'-C opt-level=2'}))

    def test_readme_does_not_invalidate(self):
        before=self.digest(); (self.root/'README.md').write_text('Documentation only.')
        self.assertEqual(before, self.digest())

    def test_missing_build_input_is_an_error(self):
        (self.root/'Cargo.lock').unlink()
        process=subprocess.run(['bash',str(SCRIPT),str(self.root)],capture_output=True,text=True)
        self.assertNotEqual(process.returncode,0); self.assertIn('missing build input',process.stderr)

    def test_symlinked_build_input_is_an_error(self):
        (self.root/'assets/link').symlink_to(self.root/'Cargo.toml')
        process=subprocess.run(['bash',str(SCRIPT),str(self.root)],capture_output=True,text=True)
        self.assertNotEqual(process.returncode,0); self.assertIn('symlinked',process.stderr)

    def ready(self, restored):
        action=(ROOT/'action.yml').read_text()
        section=action.split('    - id: ready\n',1)[1].split('    - uses: dtolnay/',1)[0]
        script=textwrap.dedent(section.split('      run: |\n',1)[1])
        output=Path(self.temp.name)/'readiness-output'
        output.unlink(missing_ok=True)
        subprocess.run(['bash','-c',script],check=True,
            env={**os.environ,'RESTORED':restored,'GITHUB_ACTION_PATH':str(self.root),'GITHUB_OUTPUT':str(output)})
        return output.read_text().strip()

    def executable(self, name, status=0):
        path=self.root/'target/release'/name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(f'#!/bin/sh\nexit {status}\n'); path.chmod(0o755)

    def test_valid_cached_pair_is_ready_without_rust(self):
        self.executable('e-balls'); self.executable('e-balls-collect')
        self.assertEqual(self.ready('true'),'value=true')
        self.assertEqual(self.ready('false'),'value=false')

    def test_partial_binary_cache_requires_build(self):
        self.executable('e-balls')
        self.assertEqual(self.ready('true'),'value=false')

    def test_unrunnable_binary_cache_requires_build(self):
        self.executable('e-balls'); self.executable('e-balls-collect',1)
        self.assertEqual(self.ready('true'),'value=false')

    def test_cache_paths_are_canonical_not_raw_action_paths(self):
        action=(ROOT/'action.yml').read_text()
        self.assertNotIn('github.action_path',action)
        self.assertIn('realpath -m "$GITHUB_ACTION_PATH/target/release/e-balls"',action)
        self.assertIn('realpath -m "$GITHUB_ACTION_PATH/target/release/e-balls-collect"',action)
        self.assertEqual(action.count('steps.binary-key.outputs.renderer'),2)
        self.assertEqual(action.count('steps.binary-key.outputs.collector'),2)

    def test_workflow_restores_before_conditionally_installing_rust(self):
        # Structural wiring check, not a successful remote cache-hit claim.
        action=(ROOT/'action.yml').read_text()
        self.assertLess(action.index('actions/cache/restore@'),action.index('dtolnay/rust-toolchain@'))
        toolchain=action.split('    - uses: dtolnay/rust-toolchain@',1)[1].split('    - id: build',1)[0]
        self.assertRegex(toolchain, r"^[0-9a-f]{40} # master; Rust 1\.88\.0\n")
        self.assertIn("if: steps.ready.outputs.value != 'true'",toolchain)
        self.assertIn("toolchain: '1.88.0'",toolchain)
        self.assertLess(action.index('actions/cache/save@'),action.index('    - id: render\n'))
        self.assertNotIn('runner.imageos',action)

if __name__=='__main__': unittest.main()
