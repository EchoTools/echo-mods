#!/usr/bin/env python3
"""The pull-request gates for this repo. Each prints one JSON record and exits 0 (ok) or 1 (fail).

    gates.py title   [--title T]                     # $PR_TITLE: a Conventional Commits header
    gates.py commits --base SHA --head SHA           # every commit: a conventional header, credit trailers well formed
    gates.py review  --repo OWNER/NAME --pr N        # a changed gated path has a current approval from someone else
    gates.py pins    [WORKFLOW ...]                  # every `uses:` is pinned by a 40-hex commit

A record is {"event": "gate.<name>", "at", "ok", "errors": [...], ...}: what was checked and why it
failed. A gate that can't run (no PR, no git, no gh) exits 2 with a `gate.cannot_run` record: it never
passes by default. Python 3.9+, standard library only. Needs `git` (commits) and `gh` (review).

The conventional-commit header check is adapted from EchoTools/nevr-runtime's tools/check_pr_title.py
(Andrew Bates).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TYPES = ("feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert")
HEADER = re.compile(r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^()\s][^()]*)\))?(?P<bang>!)?: (?P<description>\S.*)$")

# Co-Authored-By trailers: a GitHub noreply address (credits a person: <id>+<login>@users.noreply.github.com),
# or the project's house addresses.
TRAILER = re.compile(r"^co-authored-by:[ \t]*(?P<value>.*)$", re.I | re.M)
TRAILER_VALUE = re.compile(r"^(?P<name>[^<>\n]*[^<>\s]) <(?P<email>[^<>\s]+)>$")
NOREPLY = re.compile(r"^\d+\+[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})@users\.noreply\.github\.com$")
HOUSE = {"a@sprock.io", "agents@sprock.io"}

# A change to any of these needs a review. README and docs alone don't.
GATED = ("mods/", "schema/", "scripts/", "tests/", ".github/", "AGENTS.md")
REVIEWERS = {"OWNER", "MEMBER", "COLLABORATOR"}

USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<ref>[^\s#]+)")
PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def header_error(title):
    """None when `title` is a Conventional Commits 1.0.0 header, else why not."""
    if "\n" in title or "\r" in title:
        return "must be one line"
    m = HEADER.match(title)
    if not m:
        return (f"{title!r} is not `type(scope)!: description` (https://www.conventionalcommits.org/en/v1.0.0/); "
                "the scope and the ! are optional, the colon and the space after it are not")
    if m.group("type").lower() not in TYPES:
        return f"unknown type {m.group('type')!r}; use one of: {', '.join(TYPES)}"
    return None


def trailer_errors(message):
    errors = []
    for m in TRAILER.finditer(message):
        value = m.group("value").strip()
        t = TRAILER_VALUE.match(value)
        if not t:
            errors.append(f"Co-Authored-By {value!r}: write `Name <email>`")
        elif not (NOREPLY.match(t.group("email")) or t.group("email") in HOUSE):
            errors.append(f"Co-Authored-By {value!r}: credit a person by their GitHub noreply address "
                          "`<id>+<login>@users.noreply.github.com` (`gh api users/<login>` gives the id)")
    return errors


def commit_errors(message):
    subject = message.split("\n", 1)[0]
    errors = []
    e = header_error(subject)
    if e:
        errors.append(f"subject: {e}")
    return errors + trailer_errors(message)


def gated(path):
    return path.startswith(GATED)


def review_errors(author, head_sha, files, reviews):
    """Why a PR that changes gated paths has no current approval; [] when it has one or needs none."""
    touched = sorted(f for f in files if gated(f))
    if not touched:
        return [], "no gated path changed"
    latest = {}
    for r in reviews:  # in the order GitHub lists them: later wins; comments don't count
        if r["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[r["user"]] = r
    errors = [f"{u} requested changes" for u, r in latest.items() if r["state"] == "CHANGES_REQUESTED"]
    ok = [u for u, r in latest.items()
          if r["state"] == "APPROVED" and u.lower() != author.lower() and r["association"] in REVIEWERS
          and r["commit_id"] == head_sha]
    if not ok and not errors:
        errors.append(f"no approval of {head_sha[:12]} from an owner, member or collaborator other than {author} "
                      f"(changed: {', '.join(touched[:5])}{' ...' if len(touched) > 5 else ''})")
    return errors, f"approved by {', '.join(sorted(ok))}" if ok else ""


def pin_errors(path, text):
    errors = []
    for n, line in enumerate(text.splitlines(), 1):
        m = USES.match(line)
        if m and not m.group("ref").startswith("./") and not PINNED.match(m.group("ref")):
            errors.append(f"{path}:{n}: `{m.group('ref')}` is not pinned by a 40-hex commit")
    return errors


def gh_json(path):
    r = subprocess.run(["gh", "api", "--paginate", "--slurp", path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {path}: {r.stderr.strip()[:300]}")
    data = json.loads(r.stdout)
    return [x for page in data for x in (page if isinstance(page, list) else [page])]


def emit(gate, errors, **fields):
    record = {"event": f"gate.{gate}", "at": now(), "ok": not errors, "errors": errors, **fields}
    print(json.dumps(record, sort_keys=True), flush=True)
    return 1 if errors else 0


def cannot_run(gate, why):
    print(json.dumps({"event": "gate.cannot_run", "at": now(), "gate": gate, "error": why}, sort_keys=True), flush=True)
    return 2


def run_title(args):
    title = args.title if args.title is not None else os.environ.get("PR_TITLE")
    if title is None:
        return cannot_run("title", "no title: --title or $PR_TITLE")
    e = header_error(title)
    return emit("title", [e] if e else [], title=title)


def run_commits(args):
    r = subprocess.run(["git", "log", "--no-merges", "--format=%H%x1f%B%x1e", f"{args.base}..{args.head}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return cannot_run("commits", r.stderr.strip()[:300])
    errors, shas = [], []
    for chunk in filter(None, (c.strip("\n") for c in r.stdout.split("\x1e"))):
        sha, _, message = chunk.partition("\x1f")
        shas.append(sha)
        errors.extend(f"{sha[:12]}: {e}" for e in commit_errors(message))
    if not shas:
        return cannot_run("commits", f"no commits in {args.base}..{args.head}")
    return emit("commits", errors, base=args.base, head=args.head, commits=len(shas))


def run_review(args):
    try:
        pr = gh_json(f"repos/{args.repo}/pulls/{args.pr}")[0]
        files = [f["filename"] for f in gh_json(f"repos/{args.repo}/pulls/{args.pr}/files")]
        reviews = [{"user": r["user"]["login"], "state": r["state"], "commit_id": r["commit_id"],
                    "association": r["author_association"]} for r in gh_json(f"repos/{args.repo}/pulls/{args.pr}/reviews")]
    except (RuntimeError, ValueError, KeyError, IndexError) as e:
        return cannot_run("review", str(e))
    errors, note = review_errors(pr["user"]["login"], pr["head"]["sha"], files, reviews)
    return emit("review", errors, repo=args.repo, pr=args.pr, author=pr["user"]["login"], head=pr["head"]["sha"],
                files=len(files), note=note)


def run_pins(args):
    paths = args.paths or sorted(Path(".github/workflows").glob("*.y*ml"))
    if not paths:
        return cannot_run("pins", "no workflow files found")
    errors = []
    for p in paths:
        errors.extend(pin_errors(str(p), Path(p).read_text(encoding="utf-8")))
    return emit("pins", errors, files=[str(p) for p in paths])


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="gate", required=True)
    t = sub.add_parser("title")
    t.add_argument("--title")
    t.set_defaults(fn=run_title)
    c = sub.add_parser("commits")
    c.add_argument("--base", required=True)
    c.add_argument("--head", required=True)
    c.set_defaults(fn=run_commits)
    r = sub.add_parser("review")
    r.add_argument("--repo", required=True)
    r.add_argument("--pr", required=True, type=int)
    r.set_defaults(fn=run_review)
    p = sub.add_parser("pins")
    p.add_argument("paths", nargs="*", type=Path)
    p.set_defaults(fn=run_pins)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
