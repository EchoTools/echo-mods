# AGENTS.md

Rules for any agent or contributor working in this repo. The home-level `AGENTS.md` files (logging, read
before acting, verify then say done) apply as well; this file adds to them and wins where it is more specific.

## What this repo is

The catalog and submission place for nEVR plugins. An author submits once (an issue from the form); a
check comments what it found; a maintainer approves; each listed plugin points at its EchoTools fork and
release and carries what a plugin browser needs: description, media, versions, author, credits.

| Path | What |
|---|---|
| `.github/ISSUE_TEMPLATE/` | The submit and pull-a-version forms |
| `.github/workflows/check-submission.yml`, `scripts/inspect_submission.py`, `scripts/report_submission.py` | The automatic check of a submission, in a read-only job, and its comment |
| `mods/<id>.json`, `schema/entry.schema.json`, `docs/entry-format.md`, `scripts/validate_entries.py` | The listed entries and their format |
| `.github/workflows/gates.yml`, `scripts/gates.py`, `tests/test_gates.py` | The pull-request gates below |

Read `README.md` and `docs/entry-format.md` before changing an entry or the check. The signing design this
repo is part of is release-signer's `docs/plugin-release.md`.

## Logging

Everything here that runs logs what it did, as JSON, durably. Nothing in it is allowed to pass quietly.

- The gates and the entry validator print one JSON record per check (`event`, `at`, `ok`, `errors`, and
  what was checked). CI keeps those records as artifacts for 90 days. A gate that cannot run prints a
  `cannot_run` record and exits 2; it never passes by default.
- The submission check writes `report.json` (an artifact) and an issue comment for every run.
- A new script or workflow step is not done until you have shown a real record from a real run and a test
  that asserts it. Never print or log a token or a secrets file.

## Commits and PR titles

- Commits and PR titles follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):
  `type(scope)!: description`, with `type` one of `feat fix docs style refactor perf test build ci chore
  revert`. One logical change per commit. The history before this file is free text; new commits are not.
- The `gates` workflow checks the title and every commit of a PR (`scripts/gates.py title`, `commits`).
- Version tags are SemVer, `v<version>`. The changelog is the git log.

## Credit

Credit the people whose work we integrate, every time.

- A commit that draws on a person's code, patch, research or findings carries `Co-Authored-By: Name
  <id+login@users.noreply.github.com>` for that person (`gh api users/<login>` gives the id). The gate
  rejects a trailer that is not `Name <email>` with a GitHub noreply address or the house addresses
  (`a@sprock.io`, `agents@sprock.io`). Someone with no GitHub account is credited by name in the commit
  body.
- A listed mod credits everyone whose work it builds on in the entry's `credits` (name, role, link).
  The mod's own repo keeps their license files and says who they are in `NOTICE` and its README.
- Never list a mod whose credits you know to be missing: send it back to the author.

## Review

- Every PR that changes more than `README.md` and `docs/` needs a current approval from an owner, member
  or collaborator who did not write it. "Current" means given on the PR's latest commit. An open request
  for changes blocks. `gates.yml`'s `review` job (`scripts/gates.py review`) checks it.
- The reviewer reads the diff and the code around it, runs what the PR claims, and reports findings with
  `file:line`. An entry's reviewer also reads the mod: what it hooks, what it sends where, and whether its
  capabilities say what it does.
- A change to a gate (`scripts/gates.py`, `.github/workflows/`) is reviewed with extra care: the PR's own
  copy of the gate is the one that runs on it.
- Owner setting, not in this repo: make `gates / review`, `title`, `commits`, `pins` and `tests` required
  checks on `main`, and restrict who can merge. Until then the gates report but do not block.

## Issues, branches and PRs

- Every unit of work has an issue before it starts. The PR body names it (`Closes #N`, or `Refs #N` while
  part stays open) and carries the commands you ran and their output.
- One worktree per PR: `git worktree add --no-track -b <branch> <path> origin/main`. Push with
  `git push origin <local>:refs/heads/<branch>`. Never push `main`, never force-push, never rewrite a
  pushed branch: fix with a new commit.
- A PR is one small change. When it is merged, delete its branch and remove its worktree
  (`git worktree remove <path>`); the repo owner merges, not the author.

## Workflows

- Pin every action by its 40-hex commit, with the tag in a comment. The `pins` gate checks it.
- Trust boundary: use `pull_request` (and `issues` for the submission check), never `pull_request_target`.
  A job that opens, downloads or loads anything a submitter controls holds a read-only token and no secret;
  the job that writes (the comment) runs nothing from the submission. Untrusted text reaches a script
  through `env`, never inside a script body.
- `permissions: {}` at the top of a workflow, and the least each job needs.

## Entries

- `mods/<id>.json` is created by a maintainer when a submission is approved, and changed when a release
  is listed or pulled. It is checked against `schema/entry.schema.json`; `docs/entry-format.md` says what
  each field means.
- The `signer` block records what the release-signer did. Copy its digests from the signer's public
  record; never invent or edit them by hand to make the check pass.
- Pulling a version sets `pulled` on it; it never edits the release's digests.

## Commands

```
python3 -I -m unittest discover -s tests -v     # the tests (validate_entries needs: pip install jsonschema==4.26.0)
python3 -I scripts/validate_entries.py          # every mods/*.json
python3 -I scripts/gates.py pins                # actions pinned
python3 -I scripts/gates.py title --title "fix: x"
python3 -I scripts/gates.py commits --base origin/main --head HEAD
python3 -I scripts/gates.py review --repo EchoTools/echo-mods --pr <N>
```

## Never

- Sign, hold keys or secrets, or add a secret to a workflow here: signing happens only in release-signer.
- Delete, rename or reorganize files, or delete logs, without the owner's word.
- List a mod that failed the check without a maintainer saying why in the issue.
- Turn a check into a warning, or add `|| true`, to make a PR green. Fix the thing it found.
