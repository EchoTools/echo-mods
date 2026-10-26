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

## A version (release fields: provisional)

These fields follow the release layout in the signing design (§2) and the pin the signer approves (§3).
They are drafted ahead of the plugin-release spec and will be aligned with it when it lands.

| Field | What |
|---|---|
| `version`, `tag`, `commit` | The semver, `v<version>`, and the 40-hex commit the tag points at in the fork. |
| `assets.package` / `manifest` / `sums` | `<id>-v<version>-windows.zip`, `echo-mod.json`, `SHA256SUMS`: name, `sha256`, `size` as the release workflow built and attested them. |
| `signer.status` | `unsigned` (listed before signing), `pending` (draft exists), `approved` (pin merged in the signer), `signed`, `revoked`. |
| `signer.record`, `signed_at`, `package`, `sums` | Only on `signed` and `revoked`: the signer's public record, the time, and the digests of the signed zip and the regenerated sums (the manifest is unchanged by signing). They must differ from the attested ones. |
| `pulled` | `reason` and `at`, set by "Pull a version". |
| `prerelease` | `true` exactly when the version has a `-suffix`. |

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
asset names are the release layout's, versions are unique and newest first, a signed digest differs
from the attested one, and a fork is not the author's own repo.
