"""Runs scripts/gates.py as the CI does. Every gate has a passing case and a failing one, so a gate that
always passes (or always fails) is caught.

    python3 -I -m unittest discover -s tests -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATES = ROOT / "scripts" / "gates.py"
sys.path.insert(0, str(ROOT / "scripts"))
import gates  # noqa: E402

NOREPLY = "Dualgame <26533696+Dualgame@users.noreply.github.com>"


def run(*args, cwd=None, env=None):
    r = subprocess.run([sys.executable, "-I", str(GATES), *map(str, args)], capture_output=True, text=True, cwd=cwd,
                       env={**os.environ, **(env or {})})
    return r.returncode, [json.loads(line) for line in r.stdout.splitlines()]


class Title(unittest.TestCase):
    def test_conventional_titles_pass(self):
        for title in ("feat: entry schema", "fix(check)!: refuse a bad tag", "Docs: README", "ci: pin the actions"):
            code, records = run("title", "--title", title)
            self.assertEqual(code, 0, (title, records))
            self.assertEqual(records[0]["event"], "gate.title")
            self.assertTrue(records[0]["ok"])

    def test_other_titles_fail(self):
        for title in ("Form: the EchoVRCE username is contact only", "feat:no space", "wip: x", "feat: ", "update readme"):
            code, records = run("title", "--title", title)
            self.assertEqual(code, 1, title)
            self.assertFalse(records[0]["ok"])
            self.assertTrue(records[0]["errors"])

    def test_title_from_the_environment(self):
        self.assertEqual(run("title", env={"PR_TITLE": "fix: x"})[0], 0)
        self.assertEqual(run("title", env={"PR_TITLE": "x"})[0], 1)

    def test_no_title_cannot_run(self):
        env = {k: v for k, v in os.environ.items() if k != "PR_TITLE"}
        r = subprocess.run([sys.executable, "-I", str(GATES), "title"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(json.loads(r.stdout)["event"], "gate.cannot_run")


class Commits(unittest.TestCase):
    def repo(self, d, *messages):
        git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                                         "-c", "commit.gpgsign=false", *a], cwd=d, check=True, capture_output=True,
                                        text=True).stdout.strip()
        git("init", "-q", "-b", "main")
        git("commit", "-q", "--allow-empty", "-m", "chore: root")
        base = git("rev-parse", "HEAD")
        for m in messages:
            git("commit", "-q", "--allow-empty", "-m", m)
        return base, git("rev-parse", "HEAD")

    def check(self, *messages):
        with tempfile.TemporaryDirectory() as d:
            base, head = self.repo(d, *messages)
            return run("commits", "--base", base, "--head", head, cwd=d)

    def test_good_commits(self):
        code, records = self.check("feat: a", f"fix(x): b\n\nbody\n\nCo-Authored-By: {NOREPLY}\n"
                                              "Co-Authored-By: Andrew Bates <a@sprock.io>")
        self.assertEqual(code, 0, records)
        self.assertEqual(records[0]["commits"], 2)

    def test_free_text_subject_fails(self):
        code, records = self.check("feat: a", "Pull a version form")
        self.assertEqual(code, 1)
        self.assertEqual(len(records[0]["errors"]), 1)
        self.assertIn("subject", records[0]["errors"][0])

    def test_credit_must_be_a_noreply_address(self):
        code, records = self.check("feat: a\n\nCo-Authored-By: Dualgame <dual@example.com>")
        self.assertEqual(code, 1)
        self.assertIn("noreply", records[0]["errors"][0])

    def test_trailer_needs_an_address(self):
        code, records = self.check("feat: a\n\nCo-Authored-By: Dualgame")
        self.assertEqual(code, 1)
        self.assertIn("Name <email>", records[0]["errors"][0])

    def test_no_commits_cannot_run(self):
        with tempfile.TemporaryDirectory() as d:
            base, _ = self.repo(d)
            code, records = run("commits", "--base", base, "--head", base, cwd=d)
        self.assertEqual(code, 2)
        self.assertEqual(records[0]["event"], "gate.cannot_run")


class Review(unittest.TestCase):
    HEAD = "a" * 40

    def review(self, user="mia", state="APPROVED", commit=None, assoc="OWNER"):
        return {"user": user, "state": state, "commit_id": commit or self.HEAD, "association": assoc}

    def errors(self, files, reviews, author="author"):
        return gates.review_errors(author, self.HEAD, files, reviews)[0]

    def test_docs_only_needs_no_review(self):
        self.assertEqual(self.errors(["README.md", "docs/x.md"], []), [])

    def test_gated_path_without_review_fails(self):
        for path in ("mods/x.json", "schema/entry.schema.json", "scripts/gates.py", "tests/t.py",
                     ".github/workflows/x.yml", "AGENTS.md"):
            self.assertTrue(self.errors(["README.md", path], []), path)

    def test_approval_by_someone_else_passes(self):
        self.assertEqual(self.errors(["mods/x.json"], [self.review()]), [])

    def test_own_approval_does_not_count(self):
        self.assertTrue(self.errors(["mods/x.json"], [self.review(user="Author")]))

    def test_stale_approval_does_not_count(self):
        self.assertTrue(self.errors(["mods/x.json"], [self.review(commit="b" * 40)]))

    def test_outsider_approval_does_not_count(self):
        self.assertTrue(self.errors(["mods/x.json"], [self.review(assoc="NONE")]))

    def test_comment_does_not_count(self):
        self.assertTrue(self.errors(["mods/x.json"], [self.review(state="COMMENTED")]))

    def test_dismissed_approval_does_not_count(self):
        self.assertTrue(self.errors(["mods/x.json"], [self.review(), self.review(state="DISMISSED")]))

    def test_changes_requested_blocks_even_with_another_approval(self):
        errors = self.errors(["mods/x.json"], [self.review(), self.review(user="sprockee", state="CHANGES_REQUESTED")])
        self.assertEqual(errors, ["sprockee requested changes"])

    def test_later_approval_clears_the_users_own_request(self):
        self.assertEqual(self.errors(["mods/x.json"], [self.review(state="CHANGES_REQUESTED"), self.review()]), [])


class Workflow(unittest.TestCase):
    def test_a_piped_gate_still_fails_the_job(self):
        """`gates.py ... | tee` is green whatever gates.py exits unless the shell has pipefail."""
        text = (ROOT / ".github" / "workflows" / "gates.yml").read_text(encoding="utf-8")
        self.assertIn("| tee", text)
        self.assertRegex(text, r"(?m)^defaults:\n  run:\n    shell: bash$")


class Pins(unittest.TestCase):
    def check(self, text):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "w.yml"
            path.write_text(text, encoding="utf-8")
            return run("pins", path)

    def test_pinned_passes(self):
        code, records = self.check("steps:\n  - uses: actions/checkout@" + "a" * 40 + " # v4\n  - uses: ./local\n  - run: x\n")
        self.assertEqual(code, 0, records)

    def test_tag_fails(self):
        code, records = self.check("steps:\n  - uses: actions/checkout@v4\n")
        self.assertEqual(code, 1)
        self.assertIn("w.yml:2", records[0]["errors"][0])

    def test_short_sha_and_branch_fail(self):
        self.assertEqual(self.check("  uses: a/b@abc1234\n")[0], 1)
        self.assertEqual(self.check("  uses: a/b@main\n")[0], 1)

    def test_the_repos_workflows_are_pinned(self):
        code, records = run("pins", cwd=ROOT)
        self.assertEqual(code, 0, records)


if __name__ == "__main__":
    unittest.main()
