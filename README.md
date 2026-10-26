# Echo VR mods

The place to submit a mod (a plugin for nEVR) for the [Echo VR launcher](https://github.com/marshmallow-mia/EchoVR_Launcher).
You submit once. After that, each new version you release goes through a short review and shows up in the
launcher for players.

## Before you submit

1. **Make the mod from the template.** Start from the
   [mod template](https://github.com/EchoTools/echo-mod-template-repo). Its README covers building, testing in
   the game, and releasing; its AGENTS.md has the exact rules. Your mod's name, file, version and what it does
   all go in `echo-mod.json`.
2. **Make the checks pass.** Every push builds your mod and loads it in a test host. Fix anything red before you
   release.
3. **Keep the repo public, with an open-source license.** If your mod uses someone else's code, keep their
   license file and say who they are in `NOTICE` and your README. Players and reviewers rely on that.
4. **Make a release** with the template's release workflow (a tag `v<version>`). The workflow builds it into a
   *draft* release. **Publish that draft in your own repo** before you submit: the check only sees published
   releases. That release is yours and it is not signed. The signed release is a different one: the draft that
   the EchoTools copy builds after your change has been reviewed (see "What happens next").

## Submitting it

1. [Open a submission](https://github.com/EchoTools/echo-mods/issues/new?template=submit-mod.yml) from the account
   that owns the repo (for a repo of an organization: a public member of it). Say what the mod does, what it hooks
   and what it sends where. Screenshots, a video link and the people to credit can go in the same text.
2. A check runs and comments what it found, usually within a few minutes. Fix anything marked ❌, then edit the
   issue or comment `/check`.
3. A maintainer reads your mod and decides. Once it's approved, the issue is closed with the label `approved`.
   If not, the label is `denied` and the closing comment says why.

The issue is public, and so is the EchoVRCE username you give in it.

## What happens next

Approval gives you an EchoTools copy of your repo (a fork). That copy is what gets built and signed; you keep
working in your own repo. To release a version:

1. Bump `version` in your repo.
2. Open a pull request from your repo to the EchoTools copy.
3. A maintainer reads what changed since your last signed version and merges it.
4. A maintainer tags the version. The copy's release workflow builds it into a draft release.
5. The project owner checks that the draft is exactly what was reviewed, then starts the signing. The signed
   DLL replaces the unsigned one, and the release is published.
6. The launcher picks it up within about 5 minutes. Each result ("live", or why a release didn't make it) is a
   comment on your submission issue, so keep following it.

**Rolling out.** The EchoTools copy and signing are being switched on mod by mod. The approval comment tells you
which applies to yours. Until it is switched on, a new release of your own repo reaches the launcher by itself
(within about 5 minutes) and the result is a comment on your issue, as before.

After your first approval you also get a dev channel for test builds; the approval comment says how to reach
it. Each further mod of yours is submitted the same way, once.

## How long it takes

The builds take minutes. The review and the signing are done by people, so expect the same day to a few days per
version. Your first submission takes longest, because the whole mod gets read.

## What you get back

- A published release whose DLL carries the project's signature (Windows shows it under the file's Properties →
  Digital Signatures).
- A public record of the signing.
- A comment on your submission issue for every release.
- A listing for the launcher's plugin browser: your description, screenshots or video, versions, you as the
  author, and everyone you credited.

## What players see

Nothing different: the mod installs and loads. A player who starts the game in signed-only mode can load only
signed mods; an unsigned copy is refused with a message telling them to ask the author for a signed release.

## Testing your own builds

A normal game start loads your unsigned test build today. Once signed-only becomes the default, there will be a
switch for loading your own local builds (to be confirmed).

## Pulling a version

Something seriously wrong with a published version (it crashes, it breaks matches)? Comment on your submission
issue, or [ask here](https://github.com/EchoTools/echo-mods/issues/new?template=pull-version.yml). A maintainer
turns it off for everyone; players go back to the version before. Then release a fixed version as usual.

## Labels

| Label | Meaning |
|---|---|
| `submission` | A mod submission (set by the form) |
| `checks-passed` / `checks-failed` | The automatic check's result |
| `approved` | Added to the launcher |
| `denied` | Not added; the closing comment says why |
| `pull-version` | A request to turn a published version off |

Questions about a mod or the process: open a normal issue. How this repo is run (for maintainers and agents):
[AGENTS.md](AGENTS.md).
