# Echo VR mods

Submissions of mods for the [Echo VR launcher](https://github.com/marshmallow-mia/EchoVR_Launcher).

## Making a mod

Start from the [mod template](https://github.com/EchoTools/echo-mod-template-repo): its README
covers building, testing in the game, and releasing; its AGENTS.md has the exact rules.

## Submitting it

1. Your mod's repo is public, has an open-source license, and has a release made by the template's
   release workflow (tag `v<version>`).
2. [Open a submission](https://github.com/EchoTools/echo-mods/issues/new?template=submit-mod.yml)
   from the account that owns the repo (for a repo of an organization: a public member of it).
3. A check runs and comments what it found. Fix anything marked ❌, then edit the issue or comment
   `/check`.
4. A maintainer reviews the mod. Once it's approved, the issue is closed with the label
   `approved`, and every new release of the mod reaches the launcher on its own.

After your first approval you also get a dev channel for test builds; the approval comment says
how to reach it. Each further mod of yours is submitted the same way, once.

## Labels

| Label | Meaning |
|---|---|
| `submission` | A mod submission (set by the form) |
| `checks-passed` / `checks-failed` | The automatic check's result |
| `approved` | Added to the launcher |
| `denied` | Not added; the closing comment says why |

Questions about a mod or the process: open a normal issue.
