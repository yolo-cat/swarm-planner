from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install.sh"
SKILL_SRC = REPO_ROOT / "skills" / "swarm-planner"


def run_install(
    args: list[str],
    *,
    skills_dir: Path,
    script_path: Path = INSTALL_SCRIPT,
    cwd: Path = REPO_ROOT,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ANTIGRAVITY_SKILLS_DIR"] = str(skills_dir)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(script_path), *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def create_temp_git_repo(base_dir: Path) -> Path:
    """Create a self-contained git repo copy with scripts/install.sh and skills/swarm-planner."""
    repo = base_dir / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(INSTALL_SCRIPT, repo / "scripts" / "install.sh")
    shutil.copytree(
        SKILL_SRC,
        repo / "skills" / "swarm-planner",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store"),
    )
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo), check=True)
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(repo), check=True)
    return repo


class InstallScriptTests(unittest.TestCase):
    def test_copy_status_drift_dangling_and_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_dir = root / "skills"
            dest = skills_dir / "swarm-planner"

            # Missing install -> --status exits 1
            missing = run_install(["--status"], skills_dir=skills_dir)
            self.assertEqual(missing.returncode, 1)
            self.assertIn("MISSING:", missing.stdout)

            # Copy install -> clean status, executable scripts, no leftover staging dirs
            copied = run_install(["--copy", "--skip-tests"], skills_dir=skills_dir)
            self.assertEqual(copied.returncode, 0, copied.stderr)
            self.assertTrue((dest / "SKILL.md").is_file())
            self.assertTrue(os.access(dest / "scripts" / "model_matrix.py", os.X_OK))
            self.assertTrue(os.access(dest / "examples" / "pretool-guard.py", os.X_OK))
            leftovers = [p.name for p in skills_dir.iterdir() if p.name.startswith(".swarm-planner.")]
            self.assertEqual(leftovers, [])

            ok_status = run_install(["--status"], skills_dir=skills_dir)
            self.assertEqual(ok_status.returncode, 0, ok_status.stdout + ok_status.stderr)
            self.assertIn("OK (copy):", ok_status.stdout)

            # Drifted file -> --status exits 1
            (dest / "SKILL.md").write_text("# drifted\n", encoding="utf-8")
            drifted = run_install(["--status"], skills_dir=skills_dir)
            self.assertEqual(drifted.returncode, 1)
            self.assertIn("DRIFT:", drifted.stdout)

            # Dangling symlink -> --status exits 1
            shutil.rmtree(dest)
            dest.symlink_to(root / "nonexistent-target")
            dangling = run_install(["--status"], skills_dir=skills_dir)
            self.assertEqual(dangling.returncode, 1)
            self.assertIn("DANGLING:", dangling.stdout)

            # Symlink pointing to wrong directory -> --status exits 1
            wrong_dir = root / "other-checkout"
            wrong_dir.mkdir()
            dest.unlink()
            dest.symlink_to(wrong_dir)
            wrong_status = run_install(["--status"], skills_dir=skills_dir)
            self.assertEqual(wrong_status.returncode, 1)
            self.assertIn("DRIFT:", wrong_status.stdout)

            # Uninstall removes install and is idempotent
            removed = run_install(["--uninstall"], skills_dir=skills_dir)
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertFalse(dest.exists() or dest.is_symlink())

            removed_again = run_install(["--uninstall"], skills_dir=skills_dir)
            self.assertEqual(removed_again.returncode, 0)
            self.assertIn("Nothing to remove", removed_again.stdout)

    def test_symlink_guards_in_primary_dirty_and_linked_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_dir = root / "skills"
            dest = skills_dir / "swarm-planner"
            repo = create_temp_git_repo(root)

            # Clean primary checkout -> --symlink succeeds without --force
            ok_sym = run_install(
                ["--symlink", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(ok_sym.returncode, 0, ok_sym.stderr)
            self.assertTrue(dest.is_symlink())

            sym_status = run_install(
                ["--status"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(sym_status.returncode, 0, sym_status.stdout + sym_status.stderr)
            self.assertIn("OK (symlink):", sym_status.stdout)

            # Linked worktree -> --symlink refused without --force, allowed with --force + warning
            wt = root / "linked-wt"
            subprocess.run(["git", "worktree", "add", "-q", "-b", "wt-branch", str(wt)], cwd=str(repo), check=True)
            refused_wt = run_install(
                ["--symlink", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=wt / "scripts" / "install.sh",
                cwd=wt,
            )
            self.assertEqual(refused_wt.returncode, 1)
            self.assertIn("--force", refused_wt.stderr)

            forced_wt = run_install(
                ["--symlink", "--skip-tests", "--force"],
                skills_dir=skills_dir,
                script_path=wt / "scripts" / "install.sh",
                cwd=wt,
            )
            self.assertEqual(forced_wt.returncode, 0, forced_wt.stderr)
            self.assertIn("WARNING:", forced_wt.stderr)
            wt_status = run_install(
                ["--status"],
                skills_dir=skills_dir,
                script_path=wt / "scripts" / "install.sh",
                cwd=wt,
            )
            self.assertEqual(wt_status.returncode, 0, wt_status.stdout + wt_status.stderr)
            self.assertIn("OK (symlink):", wt_status.stdout)

            # Dirty primary checkout -> --symlink refused without --force
            (repo / "skills" / "swarm-planner" / "dirty.txt").write_text("x\n", encoding="utf-8")
            refused_dirty = run_install(
                ["--symlink", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(refused_dirty.returncode, 1)
            self.assertIn("dirty", refused_dirty.stderr)

    def test_cdpath_safety_and_conflicting_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skills_dir = Path(tmpdir) / "skills"

            # CDPATH=. must not break REPO_ROOT resolution
            help_proc = run_install(["--help"], skills_dir=skills_dir, env_overrides={"CDPATH": "."})
            self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
            self.assertIn("--status", help_proc.stdout)

            copy_proc = run_install(
                ["--copy", "--skip-tests"],
                skills_dir=skills_dir,
                env_overrides={"CDPATH": "."},
            )
            self.assertEqual(copy_proc.returncode, 0, copy_proc.stderr)
            self.assertTrue((skills_dir / "swarm-planner" / "SKILL.md").is_file())

            # Conflicting modes exit 2
            for bad_args in (
                ["--symlink", "--uninstall"],
                ["--copy", "--status"],
                ["--copy", "--symlink"],
                ["--unknown-flag"],
            ):
                proc = run_install(bad_args, skills_dir=skills_dir)
                self.assertEqual(proc.returncode, 2, f"Expected exit 2 for {bad_args}: {proc.stderr}")

    def test_cp_fallback_without_rsync_excludes_junk(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_dir = root / "skills"
            repo = create_temp_git_repo(root)

            # Plant excluded artifacts inside temp repo source
            pycache = repo / "skills" / "swarm-planner" / "scripts" / "__pycache__"
            pycache.mkdir()
            (pycache / "model_matrix.cpython-312.pyc").write_bytes(b"pyc")
            (repo / "skills" / "swarm-planner" / "foo.pyo").write_bytes(b"pyo")
            (repo / "skills" / "swarm-planner" / ".DS_Store").write_bytes(b"ds")

            # Build a clean PATH without rsync
            no_rsync_bin = root / "bin"
            no_rsync_bin.mkdir()
            for tool in (
                "bash",
                "dirname",
                "basename",
                "readlink",
                "pwd",
                "mkdir",
                "mktemp",
                "cp",
                "find",
                "rm",
                "mv",
                "chmod",
                "diff",
                "git",
            ):
                resolved = shutil.which(tool)
                if resolved:
                    (no_rsync_bin / tool).symlink_to(resolved)

            proc = run_install(
                ["--copy", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
                env_overrides={"PATH": str(no_rsync_bin)},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            dest = skills_dir / "swarm-planner"
            self.assertTrue((dest / "SKILL.md").is_file())
            self.assertFalse((dest / "scripts" / "__pycache__").exists())
            self.assertFalse((dest / "foo.pyo").exists())
            self.assertFalse((dest / ".DS_Store").exists())

            status_proc = run_install(
                ["--status"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
                env_overrides={"PATH": str(no_rsync_bin)},
            )
            self.assertEqual(status_proc.returncode, 0, status_proc.stdout + status_proc.stderr)

    def test_default_runs_tests_and_skip_tests_bypasses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_dir = root / "skills"
            log_file = root / "py.log"

            # Fake PYTHON stub that records calls and succeeds
            stub_py = root / "fake_python.sh"
            stub_py.write_text(
                f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{log_file}'\nexit 0\n",
                encoding="utf-8",
            )
            stub_py.chmod(stub_py.stat().st_mode | stat.S_IEXEC)

            # Default --copy invokes json.tool + unittest
            proc = run_install(
                ["--copy"],
                skills_dir=skills_dir,
                env_overrides={"PYTHON": str(stub_py)},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            calls = log_file.read_text(encoding="utf-8").splitlines()
            self.assertTrue(any("json.tool" in c for c in calls), calls)
            self.assertTrue(any("unittest discover" in c for c in calls), calls)

            # --skip-tests skips stub_py completely
            log_file.unlink()
            proc_skip = run_install(
                ["--copy", "--skip-tests"],
                skills_dir=skills_dir,
                env_overrides={"PYTHON": str(stub_py)},
            )
            self.assertEqual(proc_skip.returncode, 0, proc_skip.stderr)
            self.assertFalse(log_file.exists())

            # Failing test aborts install before overwriting destination
            fail_py = root / "fail_python.sh"
            fail_py.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            fail_py.chmod(fail_py.stat().st_mode | stat.S_IEXEC)
            sentinel = skills_dir / "swarm-planner" / "sentinel.txt"
            sentinel.write_text("keep-me\n", encoding="utf-8")
            proc_fail = run_install(
                ["--copy"],
                skills_dir=skills_dir,
                env_overrides={"PYTHON": str(fail_py)},
            )
            self.assertNotEqual(proc_fail.returncode, 0)
            self.assertTrue(sentinel.is_file(), "Existing install should be untouched when tests fail")


if __name__ == "__main__":
    unittest.main()
