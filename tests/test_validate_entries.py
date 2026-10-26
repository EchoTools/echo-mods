"""Runs scripts/validate_entries.py as the CI does and checks its records. Every rule has a negative
control: a valid entry with one thing broken must fail, with the message that names it.

    python3 -m unittest discover -s tests -v
"""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "validate_entries.py"
VALID = ROOT / "tests" / "fixtures" / "valid"


def run(*args):
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)], capture_output=True, text=True)
    records = [json.loads(line) for line in r.stdout.splitlines()]
    return r.returncode, records


def load(name):
    return json.loads((VALID / f"{name}.json").read_text(encoding="utf-8"))


class Valid(unittest.TestCase):
    def test_fixtures_pass_and_are_logged(self):
        code, records = run(*sorted(VALID.glob("*.json")))
        self.assertEqual(code, 0, records)
        entries = [r for r in records if r["event"] == "validate_entries.entry"]
        self.assertEqual({r["id"] for r in entries}, {"example-mod", "minimal-mod"})
        for r in entries:
            self.assertTrue(r["ok"])
            self.assertEqual(len(r["sha256"]), 64)
        self.assertEqual(records[-1]["event"], "validate_entries.done")
        self.assertEqual((records[-1]["entries"], records[-1]["invalid"]), (2, 0))

    def test_the_repos_own_entries_pass(self):
        code, records = run()
        self.assertEqual(code, 0, records)

    def test_log_file_gets_the_same_records(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "validate.jsonl"
            code, records = run(VALID / "minimal-mod.json", "--log", log)
            self.assertEqual(code, 0)
            self.assertEqual([json.loads(l) for l in log.read_text().splitlines()], records)


class Invalid(unittest.TestCase):
    def fails(self, mutate, expect, name="example-mod", filename=None):
        entry = load(name)
        mutate(entry)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / (filename or f"{entry['id']}.json")
            path.write_text(json.dumps(entry), encoding="utf-8")
            code, records = run(path)
        self.assertEqual(code, 1, records)
        errors = [e for r in records if r["event"] == "validate_entries.entry" for e in r["errors"]]
        self.assertTrue(any(expect in e for e in errors), f"{expect!r} not in {errors}")
        self.assertEqual(records[-1]["invalid"], 1)

    def test_unknown_field(self):
        self.fails(lambda e: e.update(rating=5), "rating")

    def test_missing_description(self):
        self.fails(lambda e: e.pop("description"), "'description' is a required property")

    def test_bad_id(self):
        self.fails(lambda e: e.update(id="Bad Id"), "does not match", filename="Bad Id.json")

    def test_file_name_must_match_id(self):
        self.fails(lambda e: None, "the id says example-mod.json", filename="other.json")

    def test_no_license_found(self):
        self.fails(lambda e: e["source"].update(license="NOASSERTION"), "source/license")

    def test_http_media(self):
        self.fails(lambda e: e["media"].update(video="http://example.com/v.mp4"), "media/video")

    def test_screenshot_without_alt(self):
        self.fails(lambda e: e["media"]["screenshots"][0].pop("alt"), "'alt' is a required property")

    def test_email_is_not_a_contact_field(self):
        self.fails(lambda e: e["contact"].update(email="a@example.com"), "email")

    def test_github_login_required(self):
        self.fails(lambda e: e["contact"].pop("github"), "'github' is a required property")

    def test_fork_must_be_echotools(self):
        self.fails(lambda e: e["fork"].update(repo="example-author/example-mod"), "fork/repo")

    def test_fork_required_past_unsigned(self):
        self.fails(lambda e: e.pop("fork"), "fork: required once a version is past signer status")

    def test_fork_is_not_the_authors_repo(self):
        self.fails(lambda e: e["source"].update(repo="EchoTools/example-mod"), "fork.repo is the author's own repo")

    def test_delisted_needs_a_reason(self):
        self.fails(lambda e: e["listing"].update(state="delisted"), "'delisted_reason' is a required property")

    def test_listed_has_no_reason(self):
        self.fails(lambda e: e["listing"].update(delisted_reason="x"), "listing")

    def test_tag_matches_version(self):
        self.fails(lambda e: e["versions"][0].update(tag="v0.2.1"), "the tag is v0.2.1, it must be v0.2.0")

    def test_short_commit(self):
        self.fails(lambda e: e["versions"][0].update(commit="abc1234"), "versions/0/commit")

    def test_package_name(self):
        self.fails(lambda e: e["versions"][0]["assets"]["package"].update(name="mod.zip"), "assets.package.name")

    def test_upper_case_hash(self):
        self.fails(lambda e: e["versions"][0]["assets"]["sums"].update(sha256="A" * 64), "sha256")

    def test_signed_needs_the_signed_digests(self):
        self.fails(lambda e: e["versions"][0]["signer"].pop("package"), "'package' is a required property")

    def test_signed_must_differ_from_attested(self):
        def same(e):
            v = e["versions"][0]
            v["signer"]["package"]["sha256"] = v["assets"]["package"]["sha256"]
        self.fails(same, "signing changes it")

    def test_unsigned_carries_no_signature_fields(self):
        self.fails(lambda e: e["versions"][1]["signer"].update(record="https://example.com/r"), "versions/1/signer")

    def test_unknown_signer_status(self):
        self.fails(lambda e: e["versions"][0]["signer"].update(status="trusted"), "versions/0/signer/status")

    def test_versions_newest_first(self):
        self.fails(lambda e: e["versions"].reverse(), "newest first")

    def test_duplicate_version(self):
        def dup(e):
            e["versions"].append(copy.deepcopy(e["versions"][1]))
        self.fails(dup, "a version is listed twice")

    def test_prerelease_flag_follows_the_version(self):
        def pre(e):
            v = e["versions"][0]
            v.update(version="0.3.0-rc.1", tag="v0.3.0-rc.1")
            v["assets"]["package"]["name"] = "example-mod-v0.3.0-rc.1-windows.zip"
        self.fails(pre, "prerelease must be true")

    def test_not_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.json"
            path.write_text("{", encoding="utf-8")
            code, records = run(path)
        self.assertEqual(code, 1)
        self.assertIn("not JSON", records[0]["errors"][0])


class CannotRun(unittest.TestCase):
    def test_missing_schema_fails_loudly(self):
        code, records = run("--schema", ROOT / "schema" / "nope.json", VALID / "minimal-mod.json")
        self.assertEqual(code, 2)
        self.assertEqual(records[0]["event"], "validate_entries.cannot_run")


if __name__ == "__main__":
    unittest.main()
