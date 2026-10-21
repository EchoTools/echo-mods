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
   `approved`, and every new release of the mod reaches the launcher on its own, within about
   5 minutes. Each result ("live", or why a release didn't make it) is a comment on your
   submission issue, so keep following it.

The issue is public, the EchoVRCE username you give in it too.

After your first approval you also get a dev channel for test builds; the approval comment says
how to reach it. Each further mod of yours is submitted the same way, once.

## Pulling a version

Something seriously wrong with a published version (it crashes, it breaks matches)? Comment on
your submission issue, or [ask here](https://github.com/EchoTools/echo-mods/issues/new?template=pull-version.yml).
A maintainer turns it off for everyone; players go back to the version before. Then release a
fixed version as usual.

## Labels

| Label | Meaning |
|---|---|
| `submission` | A mod submission (set by the form) |
| `checks-passed` / `checks-failed` | The automatic check's result |
| `approved` | Added to the launcher |
| `denied` | Not added; the closing comment says why |
| `pull-version` | A request to turn a published version off |

Questions about a mod or the process: open a normal issue.
