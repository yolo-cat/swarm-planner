from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
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


def create_temp_checkout(base_dir: Path, *, init_git: bool = True, name: str = "repo") -> Path:
    """Create a self-contained checkout with scripts/install.sh and skills/swarm-planner."""
    repo = base_dir / name
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(INSTALL_SCRIPT, repo / "scripts" / "install.sh")
    shutil.copytree(
        SKILL_SRC,
        repo / "skills" / "swarm-planner",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store"),
    )
    if init_git:
        subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo), check=True)
        subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(repo), check=True)
    return repo


def build_minimal_bin(base_dir: Path, *, omit: set[str] | None = None) -> Path:
    bin_dir = base_dir / "min_bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    omit = omit or set()
    tools = (
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
        "ln",
        "chmod",
        "diff",
        "git",
        "rmdir",
        "rsync",
        "cat",
        "sleep",
    )
    for tool in tools:
        if tool in omit:
            continue
        resolved = shutil.which(tool)
        if resolved:
            link = bin_dir / tool
            if not link.exists():
                link.symlink_to(resolved)
    return bin_dir


class InstallScriptTests(unittest.TestCase):
    def test_copy_status_drift_dangling_and_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_dir = root / "skills"
            dest = skills_dir / "swarm-planner"
            repo = create_temp_checkout(root)

            # Plant excluded junk to verify rsync path also excludes __pycache__/*.pyc/*.pyo/.DS_Store (RSI3-25)
            pycache = repo / "skills" / "swarm-planner" / "scripts" / "__pycache__"
            pycache.mkdir()
            (pycache / "model_matrix.cpython-312.pyc").write_bytes(b"pyc")
            (repo / "skills" / "swarm-planner" / "junk.pyo").write_bytes(b"pyo")
            (repo / "skills" / "swarm-planner" / ".DS_Store").write_bytes(b"ds")

            # Missing install -> --status and --check alias exit 1
            for status_flag in ("--status", "--check"):
                missing = run_install(
                    [status_flag],
                    skills_dir=skills_dir,
                    script_path=repo / "scripts" / "install.sh",
                    cwd=repo,
                )
                self.assertEqual(missing.returncode, 1)
                self.assertIn("MISSING:", missing.stdout)

            # Default mode (no mode flag) performs --copy (RSI3-25)
            copied = run_install(
                ["--skip-tests"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(copied.returncode, 0, copied.stderr)
            self.assertTrue((dest / "SKILL.md").is_file())
            self.assertFalse((dest / "scripts" / "__pycache__").exists())
            self.assertFalse((dest / "junk.pyo").exists())
            self.assertFalse((dest / ".DS_Store").exists())
            self.assertTrue(os.access(dest / "scripts" / "model_matrix.py", os.X_OK))
            self.assertTrue(os.access(dest / "examples" / "pretool-guard.py", os.X_OK))
            leftovers = [p.name for p in skills_dir.iterdir() if p.name.startswith(".swarm-planner.")]
            self.assertEqual(leftovers, [])

            ok_status = run_install(
                ["--check"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(ok_status.returncode, 0, ok_status.stdout + ok_status.stderr)
            self.assertIn("OK (copy):", ok_status.stdout)

            # RSI3-05: chmod -x on installed executable script triggers DRIFT
            mm_dest = dest / "scripts" / "model_matrix.py"
            orig_mode = mm_dest.stat().st_mode
            mm_dest.chmod(orig_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
            no_exec_status = run_install(
                ["--status"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(no_exec_status.returncode, 1)
            self.assertIn("DRIFT:", no_exec_status.stdout)
            mm_dest.chmod(orig_mode)

            # RSI3-05: internal symlink inside copied install triggers DRIFT
            skill_copy = dest / "SKILL.md"
            skill_copy.unlink()
            skill_copy.symlink_to(repo / "skills" / "swarm-planner" / "SKILL.md")
            internal_link_status = run_install(
                ["--status"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(internal_link_status.returncode, 1)
            self.assertIn("DRIFT:", internal_link_status.stdout)

            # Drifted file -> --status exits 1
            skill_copy.unlink()
            skill_copy.write_text("# drifted\n", encoding="utf-8")
            drifted = run_install(
                ["--status"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(drifted.returncode, 1)
            self.assertIn("DRIFT:", drifted.stdout)

            # RSI3-25: regular file at $DEST_DIR -> DRIFT
            shutil.rmtree(dest)
            dest.write_text("not a dir\n", encoding="utf-8")
            file_status = run_install(
                ["--status"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(file_status.returncode, 1)
            self.assertIn("DRIFT:", file_status.stdout)

            # RSI3-05: symlink to regular file -> DRIFT (must not crash with cd Not a directory)
            regular_target = root / "some-file.txt"
            regular_target.write_text("hello\n", encoding="utf-8")
            dest.unlink()
            dest.symlink_to(regular_target)
            sym_file_status = run_install(
                ["--status"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(sym_file_status.returncode, 1)
            self.assertIn("DRIFT:", sym_file_status.stdout)
            self.assertNotIn("Not a directory", sym_file_status.stderr)

            # Dangling symlink -> --status exits 1 with DANGLING
            dest.unlink()
            dest.symlink_to(root / "nonexistent-target")
            dangling = run_install(
                ["--status"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(dangling.returncode, 1)
            self.assertIn("DANGLING:", dangling.stdout)

            # RSI3-25: --copy cleanly replaces a dangling symlink in place
            replace_dangling = run_install(
                ["--copy", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(replace_dangling.returncode, 0, replace_dangling.stderr)
            self.assertTrue(dest.is_dir() and not dest.is_symlink())

            # Symlink pointing to wrong directory -> --status exits 1
            wrong_dir = root / "other-checkout"
            wrong_dir.mkdir()
            shutil.rmtree(dest)
            dest.symlink_to(wrong_dir)
            wrong_status = run_install(
                ["--status"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(wrong_status.returncode, 1)
            self.assertIn("DRIFT:", wrong_status.stdout)

            # Uninstall removes install and is idempotent
            removed = run_install(["--uninstall"], skills_dir=skills_dir)
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertFalse(dest.exists() or dest.is_symlink())

            removed_again = run_install(["--uninstall"], skills_dir=skills_dir)
            self.assertEqual(removed_again.returncode, 0)
            self.assertIn("Nothing to remove", removed_again.stdout)

    def test_symlink_guards_mode_transitions_and_fast_fail_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_dir = root / "skills"
            dest = skills_dir / "swarm-planner"
            repo = create_temp_checkout(root)

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

            # RSI3-25: mode transitions in-place (--copy replaces --symlink, then --symlink replaces --copy)
            copy_over_sym = run_install(
                ["--copy", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(copy_over_sym.returncode, 0, copy_over_sym.stderr)
            self.assertTrue(dest.is_dir() and not dest.is_symlink())

            sym_over_copy = run_install(
                ["--symlink", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(sym_over_copy.returncode, 0, sym_over_copy.stderr)
            self.assertTrue(dest.is_symlink())

            # Linked worktree -> --symlink refused BEFORE running tests or creating $SKILLS_ROOT (RSI3-24)
            wt = root / "linked-wt"
            subprocess.run(["git", "worktree", "add", "-q", "-b", "wt-branch", str(wt)], cwd=str(repo), check=True)
            untouched_skills = root / "untouched-skills"
            py_log = root / "should-not-run.log"
            stub_py = root / "stub_py.sh"
            stub_py.write_text(f"#!/bin/sh\necho ran >> '{py_log}'\nexit 0\n", encoding="utf-8")
            stub_py.chmod(stub_py.stat().st_mode | stat.S_IEXEC)

            refused_wt = run_install(
                ["--symlink"],
                skills_dir=untouched_skills,
                script_path=wt / "scripts" / "install.sh",
                cwd=wt,
                env_overrides={"PYTHON": str(stub_py)},
            )
            self.assertEqual(refused_wt.returncode, 1)
            self.assertIn("--force", refused_wt.stderr)
            self.assertFalse(untouched_skills.exists(), "--symlink refusal must not create $SKILLS_ROOT")
            self.assertFalse(py_log.exists(), "--symlink refusal must happen before preflight tests")

            # Linked worktree with --force succeeds + emits WARNING; --status emits INFO + WARNING (RSI3-25)
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
            self.assertIn("INFO:", wt_status.stdout)
            self.assertIn("OK (symlink):", wt_status.stdout)
            self.assertIn("WARNING:", wt_status.stderr)

            # Linked AND dirty worktree with --force (RSI3-25)
            (wt / "skills" / "swarm-planner" / "dirty.txt").write_text("x\n", encoding="utf-8")
            forced_ld = run_install(
                ["--symlink", "--skip-tests", "--force"],
                skills_dir=skills_dir,
                script_path=wt / "scripts" / "install.sh",
                cwd=wt,
            )
            self.assertEqual(forced_ld.returncode, 0, forced_ld.stderr)
            self.assertIn("linked and dirty git worktree", forced_ld.stderr)

            # Dirty primary checkout -> refused without --force, allowed with --force (RSI3-25)
            (repo / "skills" / "swarm-planner" / "dirty.txt").write_text("x\n", encoding="utf-8")
            refused_dirty = run_install(
                ["--symlink", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(refused_dirty.returncode, 1)
            self.assertIn("dirty", refused_dirty.stderr)

            forced_dirty = run_install(
                ["--symlink", "--skip-tests", "--force"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(forced_dirty.returncode, 0, forced_dirty.stderr)
            self.assertIn("WARNING:", forced_dirty.stderr)

    def test_swap_rollback_on_sigterm_and_failed_symlink(self) -> None:
        # RSI3-06: verify rollback on mid-swap SIGTERM during --copy and failed ln during --symlink
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_dir = root / "skills"
            dest = skills_dir / "swarm-planner"
            repo = create_temp_checkout(root)

            # Seed an existing install with a sentinel file
            init_copy = run_install(
                ["--copy", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
            )
            self.assertEqual(init_copy.returncode, 0, init_copy.stderr)
            sentinel = dest / "sentinel.txt"
            sentinel.write_text("original-install\n", encoding="utf-8")

            # 1. Simulate mid-swap SIGTERM right after moving existing $DEST_DIR into backup
            real_mv = shutil.which("mv")
            assert real_mv
            sigterm_bin = build_minimal_bin(root / "sigterm_env", omit={"mv"})
            mv_count_file = root / "mv.count"
            fake_mv = sigterm_bin / "mv"
            fake_mv.write_text(
                "#!/bin/sh\n"
                f"c=0; [ -f '{mv_count_file}' ] && c=$(cat '{mv_count_file}')\n"
                "c=$((c + 1))\n"
                f"echo \"$c\" > '{mv_count_file}'\n"
                "if [ \"$c\" -eq 2 ]; then\n"
                "  kill -TERM \"$PPID\"\n"
                "  sleep 1\n"
                "  exit 143\n"
                "fi\n"
                f"exec '{real_mv}' \"$@\"\n",
                encoding="utf-8",
            )
            fake_mv.chmod(fake_mv.stat().st_mode | stat.S_IEXEC)

            interrupted = run_install(
                ["--copy", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
                env_overrides={"PATH": str(sigterm_bin)},
            )
            self.assertNotEqual(interrupted.returncode, 0)
            self.assertTrue(sentinel.is_file(), "Prior install must be rolled back on mid-swap SIGTERM")
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "original-install\n")
            leftovers = [p.name for p in skills_dir.iterdir() if p.name.startswith(".swarm-planner.")]
            self.assertEqual(leftovers, [], f"Leftover temp/backup dirs after rollback: {leftovers}")

            # 2. Simulate failed `ln -s` during --symlink -> original install rolled back cleanly
            fail_ln_bin = build_minimal_bin(root / "failln_env", omit={"ln"})
            fake_ln = fail_ln_bin / "ln"
            fake_ln.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            fake_ln.chmod(fake_ln.stat().st_mode | stat.S_IEXEC)

            failed_sym = run_install(
                ["--symlink", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
                env_overrides={"PATH": str(fail_ln_bin)},
            )
            self.assertNotEqual(failed_sym.returncode, 0)
            self.assertTrue(sentinel.is_file(), "Prior install must survive failed --symlink")
            leftovers_sym = [p.name for p in skills_dir.iterdir() if p.name.startswith(".swarm-planner.")]
            self.assertEqual(leftovers_sym, [], f"Leftover dirs after failed symlink: {leftovers_sym}")

    def test_cdpath_flags_symlinked_script_missing_skill_and_nongit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_dir = root / "skills"

            # -h and --help with CDPATH=.
            for help_flag in ("-h", "--help"):
                help_proc = run_install([help_flag], skills_dir=skills_dir, env_overrides={"CDPATH": "."})
                self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
                self.assertIn("--status", help_proc.stdout)

            # Invoking install.sh via a symlink exercises resolve_script_dir loop (RSI3-25)
            script_link = root / "linked-install.sh"
            script_link.symlink_to(INSTALL_SCRIPT)
            copy_proc = run_install(
                ["--copy", "--skip-tests"],
                skills_dir=skills_dir,
                script_path=script_link,
                cwd=root,
                env_overrides={"CDPATH": "."},
            )
            self.assertEqual(copy_proc.returncode, 0, copy_proc.stderr)
            self.assertTrue((skills_dir / "swarm-planner" / "SKILL.md").is_file())

            # Conflicting modes & unknown options exit 2
            for bad_args in (
                ["--symlink", "--uninstall"],
                ["--copy", "--status"],
                ["--copy", "--symlink"],
                ["--unknown-flag"],
            ):
                proc = run_install(bad_args, skills_dir=skills_dir)
                self.assertEqual(proc.returncode, 2, f"Expected exit 2 for {bad_args}: {proc.stderr}")

            # Non-git checkout installs cleanly with --copy and --symlink (RSI3-25)
            nongit = create_temp_checkout(root, init_git=False, name="nongit-repo")
            nongit_skills = root / "nongit-skills"
            ng_copy = run_install(
                ["--copy", "--skip-tests"],
                skills_dir=nongit_skills,
                script_path=nongit / "scripts" / "install.sh",
                cwd=nongit,
            )
            self.assertEqual(ng_copy.returncode, 0, ng_copy.stderr)
            ng_sym = run_install(
                ["--symlink", "--skip-tests"],
                skills_dir=nongit_skills,
                script_path=nongit / "scripts" / "install.sh",
                cwd=nongit,
            )
            self.assertEqual(ng_sym.returncode, 0, ng_sym.stderr)

            # Missing SKILL.md exits 1 (RSI3-25)
            (nongit / "skills" / "swarm-planner" / "SKILL.md").unlink()
            missing_skill = run_install(
                ["--copy", "--skip-tests"],
                skills_dir=nongit_skills,
                script_path=nongit / "scripts" / "install.sh",
                cwd=nongit,
            )
            self.assertEqual(missing_skill.returncode, 1)
            self.assertIn("SKILL.md", missing_skill.stderr)

    def test_cp_fallback_without_rsync_excludes_junk_and_sets_0755(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_dir = root / "skills"
            repo = create_temp_checkout(root)

            pycache = repo / "skills" / "swarm-planner" / "scripts" / "__pycache__"
            pycache.mkdir()
            (pycache / "model_matrix.cpython-312.pyc").write_bytes(b"pyc")
            (repo / "skills" / "swarm-planner" / "foo.pyo").write_bytes(b"pyo")
            (repo / "skills" / "swarm-planner" / ".DS_Store").write_bytes(b"ds")

            no_rsync_bin = build_minimal_bin(root, omit={"rsync"})
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
            # RSI3-24: cp -Rp fallback must set root dir permissions to 0755 (not 0700 from mktemp -d)
            self.assertEqual(dest.stat().st_mode & 0o777, 0o755)

            status_proc = run_install(
                ["--status"],
                skills_dir=skills_dir,
                script_path=repo / "scripts" / "install.sh",
                cwd=repo,
                env_overrides={"PATH": str(no_rsync_bin)},
            )
            self.assertEqual(status_proc.returncode, 0, status_proc.stdout + status_proc.stderr)

    def test_default_runs_preflight_with_bytecode_guards_and_skip_tests_bypasses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skills_dir = root / "skills"
            log_file = root / "py.log"

            # Fake PYTHON stub that records PYTHONDONTWRITEBYTECODE and arguments (RSI3-25)
            stub_py = root / "fake_python.sh"
            stub_py.write_text(
                f"#!/bin/sh\nprintf 'BYTECODE=%s ARGS=%s\\n' \"$PYTHONDONTWRITEBYTECODE\" \"$*\" >> '{log_file}'\nexit 0\n",
                encoding="utf-8",
            )
            stub_py.chmod(stub_py.stat().st_mode | stat.S_IEXEC)

            # Default --copy invokes json.tool + unittest with PYTHONDONTWRITEBYTECODE=1 and -B
            proc = run_install(
                ["--copy"],
                skills_dir=skills_dir,
                env_overrides={"PYTHON": str(stub_py)},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            calls = log_file.read_text(encoding="utf-8").splitlines()
            self.assertTrue(any("json.tool" in c for c in calls), calls)
            self.assertTrue(any("unittest discover" in c for c in calls), calls)
            self.assertTrue(all(c.startswith("BYTECODE=1 ARGS=-B ") for c in calls), calls)

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
