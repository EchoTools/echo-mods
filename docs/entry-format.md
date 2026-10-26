# Entry format

A listed mod is one file, `mods/<id>.json`, checked against [`schema/entry.schema.json`](../schema/entry.schema.json).
The first half is what the author files; a maintainer adds the rest when the mod is approved and after
each release.

| Field | Who | What |
|---|---|---|
| `id`, `name`, `summary`, `description` | author | The `id` is the one in the mod's `echo-mod.json`. `summary` is one line for the plugin list; `description` says what the mod does, what it hooks and what it sends where. |
| `source` | author | `repo` (`owner/name`) and its `license` (the SPDX id GitHub reports; `NOASSERTION` is refused). |
| `contact` | author | `github` (required), `echovrce`, up to five `links`. Public, so no e-mail addresses. |
| `media` | author | Up to eight `screenshots` (`url`, `alt`, optional `caption`) and one `video`. `https` only. |
| `credits` | author | Everyone whose work the mod builds on: `name`, `role`, optional `url`. |
| `fork` | maintainer | The EchoTools copy that is built and signed (`EchoTools/<name>`). Required once a version is past signer status `unsigned`. |
| `listing` | maintainer | `state` (`listed` or `delisted`, which needs a `delisted_reason`), the `submission_issue`, `listed_at`. |
| `versions` | maintainer | Newest first. One release each, below. |

## A version

The release fields follow the plugin-release spec: release-signer's
[`docs/plugin-release.md`](https://github.com/thesprockee/release-signer/blob/teth/plugin-release-spec/docs/plugin-release.md)
(PR #25, at 642888d). The `signer` block is not in the spec and stays provisional.

| Field | What |
|---|---|
| `version`, `tag`, `commit` | The semver, `v<version>` (`v1.2.0`, `v1.2.0-rc.1`; spec §2), and the 40-hex commit the tag points at in the fork. These and the sha256s below are the pin the signer approves. |
| `assets.package` / `manifest` / `sums` | Exactly the three release assets (spec §4): `<id>-v<version>-windows.zip`, `echo-mod.json`, `SHA256SUMS`. Name and `sha256` as the release workflow built and attested them; `size` is for the plugin browser, the pin does not name it. |
| `prerelease` | `true` exactly when the version has a `-suffix`. |
| `pulled` | `reason` and `at`, set by "Pull a version". |
| `signer.status` (provisional) | `unsigned` (listed before signing), `pending` (draft exists), `approved` (pin merged in the signer), `signed`, `revoked`. |
| `signer.record`, `signed_at`, `package`, `sums` (provisional) | Only on `signed` and `revoked`: the signer's public record, the time, and the digests of the signed zip and the regenerated sums. `echo-mod.json` passes through signing untouched (spec §4), so it has no signed digest. They must differ from the attested ones. |

Versions are listed newest first by semver precedence (`1.2.0` above `1.2.0-rc.2` above `1.2.0-rc.1`),
each strictly above the next: the signer refuses a tag at or below one it already signed (spec §2).

## Checking

```
pip install jsonschema==4.26.0
python3 scripts/validate_entries.py            # every mods/*.json
python3 -I -m unittest discover -s tests -v    # the validator's own tests
```

The validator writes one JSON line per entry (file, sha256, id, ok, errors) and a summary line, and
exits 1 on any invalid entry and 2 when it can't run. `--log FILE` appends the same lines to a file;
CI keeps them as the `validate-entries` artifact. The `validate entries` workflow runs both on every
pull request and every push to `main`.

What the schema can't say, the validator checks: the file is `<id>.json`, the tag is `v<version>`,
asset names are the spec's, versions are unique and in descending semver precedence, a signed digest differs
from the attested one, and a fork is not the author's own repo.
