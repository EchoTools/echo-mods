#!/usr/bin/env python3
"""Checks a mod submission (an issue from the "Submit a mod" form) and writes what it found to a
JSON report. The workflow runs this in a job without write access: it downloads and loads the
submitted DLL, so it must not hold anything worth taking. A second job turns the report into the
issue comment.

    inspect_submission.py --template <checkout of echo-mod-template-repo> --smoke-host <smoke_host.exe>
                          --out report.json

Reads ISSUE_BODY, ISSUE_AUTHOR, ISSUE_NUMBER and GH_TOKEN (read-only) from the environment.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# The launcher's own mods, and the published third-party ones.
CATALOGUES = ("https://release.echovr.de/launcher/mods.json", "https://release.echovr.de/launcher/catalogue.json")
THIS_REPO = os.environ.get("GITHUB_REPOSITORY", "EchoTools/echo-mods")
REPO_URL = re.compile(r"^https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$")
# OSI-approved licenses GitHub detects (SPDX ids). Anything else gets a look by hand.
OSI = {
    "MIT", "MIT-0", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Zlib", "MPL-2.0", "LGPL-2.1",
    "LGPL-3.0", "GPL-2.0", "GPL-3.0", "AGPL-3.0", "Unlicense", "BSL-1.0", "EPL-2.0", "0BSD", "UPL-1.0",
    "OSL-3.0", "EUPL-1.2", "Artistic-2.0", "MS-PL", "NCSA", "PostgreSQL",
}
SUBMISSION_HEADINGS = {
    "Repository": "repo",
    "Mod id": "mod_id",
    "EchoVRCE username": "echovrce",
    "What does it do?": "about",
}


class Report:
    def __init__(self):
        self.items = []  # [level, text]
        self.facts = {}

    def ok(self, text):
        self.items.append(["ok", text])

    def warn(self, text):
        self.items.append(["warning", text])

    def error(self, text):
        self.items.append(["error", text])

    def passed(self):
        return not any(level == "error" for level, _ in self.items)


def parse_form(body):
    """{field: value} from an issue form's body: '### Heading' followed by its answer."""
    fields = {}
    for block in re.split(r"^### ", body or "", flags=re.M)[1:]:
        heading, _, value = block.partition("\n")
        key = SUBMISSION_HEADINGS.get(heading.strip())
        if not key:
            continue
        value = value.strip()
        fields[key] = "" if value == "_No response_" else value
    return fields


def gh_api(path, allow_404=False):
    r = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        if allow_404 and "HTTP 404" in r.stderr:
            return None
        raise RuntimeError(f"GitHub API {path}: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def gh_status(path):
    """The HTTP status of a GET (public membership answers 204 or 404)."""
    r = subprocess.run(["gh", "api", "-i", path], capture_output=True, text=True)
    m = re.match(r"HTTP/\S+ (\d+)", r.stdout)
    return int(m.group(1)) if m else 0


def download(url, dest):
    # curl, not urllib: GitHub's signed asset redirects come back 404 to urllib here.
    subprocess.run(["curl", "-fsSL", "--max-time", "120", "--max-filesize", str(64 << 20), "-o", str(dest), url],
                   check=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def taken_ids(report, own_number):
    """Ids and files other mods use or reserved: the launcher's catalogue, approved submissions,
    and open submissions older than this one."""
    ids, files = {}, {}
    for url in CATALOGUES:
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                for m in json.load(r).get("mods", []):
                    ids[m.get("id", "")] = "the launcher's catalogue"
                    for v in [m] + list(m.get("versions") or []):
                        for f in [v.get("file")] + list((v.get("pack") or {}).get("plugins") or []):
                            if isinstance(f, str) and f:
                                files[f.lower()] = "the launcher's catalogue"
        except urllib.error.HTTPError as e:
            if e.code != 404:
                report.warn(f"couldn't read the launcher's catalogue to compare ids ({e})")
        except Exception as e:  # noqa: BLE001
            report.warn(f"couldn't read the launcher's catalogue to compare ids ({e})")
    for state, label in (("all", "approved"), ("open", "submission")):
        try:
            found = gh_api(f"repos/{THIS_REPO}/issues?state={state}&labels={label}&per_page=100")
        except RuntimeError as e:
            report.warn(f"couldn't list earlier submissions ({e})")
            continue
        for issue in found:
            n = issue["number"]
            if n == own_number or (label == "submission" and n > own_number) or "pull_request" in issue:
                continue
            if label == "submission" and any(l["name"] in ("denied",) for l in issue.get("labels", [])):
                continue
            mod_id = parse_form(issue.get("body") or "").get("mod_id", "").strip()
            if mod_id:
                ids.setdefault(mod_id, f"#{n}")
    return ids, files


def check(args, report):
    fields = parse_form(os.environ.get("ISSUE_BODY", ""))
    author = os.environ.get("ISSUE_AUTHOR", "")
    number = int(os.environ.get("ISSUE_NUMBER", "0") or 0)
    report.facts["author"] = author
    report.facts["echovrce"] = fields.get("echovrce", "")
    mod_id = fields.get("mod_id", "").strip().strip("`")
    report.facts["mod_id"] = mod_id

    m = REPO_URL.match(fields.get("repo", "").strip())
    if not m:
        report.error("Repository: a GitHub repo address like `https://github.com/you/my-cool-mod`.")
        return
    owner, name = m.group(1), m.group(2)
    if not fields.get("echovrce"):
        report.error("EchoVRCE username is missing.")

    # ---- the repo ----
    repo = gh_api(f"repos/{owner}/{name}", allow_404=True)
    if not repo:
        report.error(f"`{owner}/{name}` doesn't exist or isn't public.")
        return
    full = repo["full_name"]
    report.facts.update(repo=full, repo_id=repo["id"], owner=repo["owner"]["login"], owner_id=repo["owner"]["id"],
                        owner_type=repo["owner"]["type"], default_branch=repo.get("default_branch"))
    if repo.get("private") or repo.get("visibility") != "public":
        report.error("The repo must be public.")
        return
    if repo.get("archived"):
        report.error("The repo is archived.")
    spdx = (repo.get("license") or {}).get("spdx_id")
    if not spdx or spdx == "NOASSERTION":
        report.error("GitHub finds no license in the repo: add a LICENSE file with an open-source license.")
    elif spdx not in OSI:
        report.warn(f"License `{spdx}`: not one the check knows as open source; the reviewer looks at it.")
    else:
        report.ok(f"Public, license `{spdx}`.")
    report.facts["license"] = spdx

    # Who may submit: the repo's owner, or a public member of the organization that owns it.
    if repo["owner"]["type"] == "User":
        if author.lower() != repo["owner"]["login"].lower():
            report.error(f"Submit from the repo owner's account (`{repo['owner']['login']}`).")
    elif gh_status(f"orgs/{repo['owner']['login']}/public_members/{author}") != 204:
        report.error(f"`{author}` isn't a public member of `{repo['owner']['login']}`: make the membership public "
                     "(the organization's People page), then comment `/check`.")
    user = gh_api(f"users/{author}", allow_404=True) or {}
    created = user.get("created_at")
    if created:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(created.replace("Z", "+00:00"))).days
        report.facts["account_age_days"] = age
        if age < 30:
            report.warn(f"The GitHub account `{author}` is {age} days old.")

    # ---- the release ----
    releases = [r for r in gh_api(f"repos/{full}/releases?per_page=20") if not r.get("draft")]
    if not releases:
        report.error("No release yet: tag a version (`git tag v0.1.0 && git push origin v0.1.0`), let the release "
                     "workflow finish, then comment `/check`.")
        return
    release = releases[0]
    tag = release["tag_name"]
    report.facts.update(tag=tag, release_id=release["id"], prerelease=release.get("prerelease", False),
                        release_url=release["html_url"])
    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    work = Path(tempfile.mkdtemp(prefix="submission-"))
    for needed in ("echo-mod.json", "SHA256SUMS"):
        if needed not in assets:
            report.error(f"Release {tag} has no `{needed}`: releases come from the template's release workflow.")
            return
    download(assets["echo-mod.json"], work / "echo-mod.json")
    manifest = json.loads((work / "echo-mod.json").read_text(encoding="utf-8"))
    kind = manifest.get("kind", "mod")
    main_file = manifest.get("file") if kind == "mod" else (manifest.get("pack") or {}).get("file")
    if not main_file or main_file not in assets:
        report.error(f"Release {tag} lacks the file its echo-mod.json names (`{main_file}`).")
        return
    download(assets["SHA256SUMS"], work / "SHA256SUMS")
    download(assets[main_file], work / main_file)

    report.facts.update(file=main_file, sha256=sha256(work / main_file), size=(work / main_file).stat().st_size,
                        version=manifest.get("version"), kind=kind, capabilities=manifest.get("capabilities"),
                        target=manifest.get("target"), visibility=manifest.get("visibility", "public"))

    # ---- the attestation: built by this repo's release workflow, from this tag ----
    for f in (main_file, "echo-mod.json"):
        r = subprocess.run(["gh", "attestation", "verify", str(work / f), "--repo", full,
                            "--signer-workflow", f"{full}/.github/workflows/release.yml", "--format", "json"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            report.error(f"`{f}` has no valid build attestation from `{full}`'s release workflow: release with "
                         "the template's unchanged release.yml.")
            continue
        cert = json.loads(r.stdout)[0]["verificationResult"]["signature"]["certificate"]
        if cert.get("sourceRepositoryRef") != f"refs/tags/{tag}":
            report.error(f"`{f}` was attested for `{cert.get('sourceRepositoryRef')}`, not the tag {tag}.")
        elif str(cert.get("sourceRepositoryIdentifier")) != str(repo["id"]):
            report.error(f"`{f}` was attested by another repository (id {cert.get('sourceRepositoryIdentifier')}).")
        else:
            report.facts.setdefault("attested_commit", cert.get("sourceRepositoryDigest"))
    if "attested_commit" in report.facts:
        report.ok(f"Release {tag} built and attested by the repo's release workflow.")

    # ---- the release's files, the manifest and the DLL: the template's checks, the same ones the
    # launcher's catalogue applies to every later release ----
    sys.path.insert(0, str(Path(args.template) / "tools"))
    import check_mod  # noqa: E402

    if manifest.get("id") != mod_id:
        report.error(f"The release's id is `{manifest.get('id')}`, the form says `{mod_id}`.")
    sub = check_mod.Report()
    _manifest, dll = check_mod.check_published(work, tag, release.get("prerelease", False), sub)
    if dll is not None and dll.is_file():
        check_mod.check_dll(str(dll), manifest, sub)
        smoke_dir = work / "smoke"
        smoke_dir.mkdir()
        shutil.copy(dll, smoke_dir / dll.name)
        shutil.copy(args.smoke_host, smoke_dir / "smoke_host.exe")
        env = dict(os.environ, WINEDEBUG="-all", WINEPREFIX=str(work / "pfx"))
        env.pop("GH_TOKEN", None)
        env.pop("GITHUB_TOKEN", None)
        wine = shutil.which("wine") or shutil.which("wine64") or "wine"
        try:
            r = subprocess.run(["timeout", "300", wine, "smoke_host.exe", dll.name], cwd=smoke_dir, env=env,
                               capture_output=True, text=True)
            out = r.stdout.strip().splitlines()
            report.facts["smoke_stderr"] = "\n".join(l for l in r.stderr.splitlines()
                                                     if "MESA" not in l and "pci id" not in l)[-1500:]
            if r.returncode != 0 or not out:
                sub.error("the DLL didn't pass the load test (loaded like nEVR loads it, outside the game): "
                          + (report.facts["smoke_stderr"].splitlines() or ["no output"])[-1])
            else:
                (work / "smoke.json").write_text(out[0])
                check_mod.check_smoke(str(work / "smoke.json"), manifest, sub)
                report.facts["smoke"] = json.loads(out[0])
        except FileNotFoundError:
            sub.error("Wine isn't there to run the load test")
    for text in sub.errors:
        report.error(text)
    for text in sub.warnings:
        report.warn(text)
    for text in sub.notes:
        if text.startswith(tuple("0123456789")):
            report.facts["imports"] = text.split("imports: ", 1)[-1]
    if not sub.errors:
        report.ok("echo-mod.json and the DLL pass the template's checks and the load test.")

    # ---- id and file free ----
    ids, files = taken_ids(report, number)
    if mod_id in ids:
        report.error(f"The id `{mod_id}` is taken ({ids[mod_id]}).")
    if str(manifest.get("file", "")).lower() in files:
        report.error(f"The file name `{manifest.get('file')}` is taken ({files[str(manifest.get('file')).lower()]}).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--smoke-host", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = Report()
    try:
        check(args, report)
    except Exception as e:  # noqa: BLE001
        report.error(f"The check itself failed: {e}")
    Path(args.out).write_text(json.dumps({"passed": report.passed(), "items": report.items, "facts": report.facts},
                                         indent=2))
    print(json.dumps(report.items, indent=2))


if __name__ == "__main__":
    main()
