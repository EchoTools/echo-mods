"""Checks a release in the plugin-release layout (release-signer docs/plugin-release.md, section 4):
exactly three assets, `<id>-v<version>-windows.zip`, `echo-mod.json` and `SHA256SUMS`.

    check_package(work, manifest, assets, report) -> Path of the unpacked DLL, or None

`work` holds the downloaded echo-mod.json, SHA256SUMS and the zip. `assets` is the release's asset names.
`report` needs `error(text)`. The zip is untrusted: it is read member by member with a size cap, nothing is
extracted but the DLL, and that goes to `work/unpacked/`. Python 3.9+, standard library only.
"""
import hashlib
import re
import stat
import zipfile
from pathlib import Path

MAX_DLL = 16 << 20
MAX_OTHER = 1 << 20
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# Windows device names collide with files whatever the extension.
DEVICES = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.I)
SUMS_LINE = re.compile(r"^([0-9a-f]{64}) [ *](\S.*)$")


def parse_sums(text):
    """({name: sha256}, [bad lines]) from a SHA256SUMS file."""
    sums, bad = {}, []
    for line in text.splitlines():
        if not line.strip():
            continue
        m = SUMS_LINE.match(line)
        if not m:
            bad.append(line[:80])
        elif m.group(2) in sums:
            bad.append(f"{m.group(2)} twice")
        else:
            sums[m.group(2)] = m.group(1)
    return sums, bad


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def check_sums(label, text, expected, report, exact=True):
    """`text` is a SHA256SUMS; `expected` is {name: bytes}. Every name must match; exact: no other names."""
    sums, bad = parse_sums(text)
    for line in bad:
        report.error(f"{label}: can't read the line {line!r}")
    for name, data in expected.items():
        if name not in sums:
            report.error(f"{label} has no line for {name}")
        elif sums[name] != sha256(data):
            report.error(f"{name} doesn't match {label}")
    if exact:
        extra = sorted(set(sums) - set(expected))
        if extra:
            report.error(f"{label} names files it shouldn't: {', '.join(extra[:5])}")


def check_package(work, manifest, assets, report):
    work = Path(work)
    mod_id, version = manifest.get("id"), manifest.get("version")
    package, file = manifest.get("package"), manifest.get("file")
    want = f"{mod_id}-v{version}-windows.zip"
    if package != want:
        report.error(f"echo-mod.json's \"package\" is {package!r}, it must be {want}")
    names = set(assets)
    if names != {want, "echo-mod.json", "SHA256SUMS"}:
        report.error("the release's files must be exactly " + f"{want}, echo-mod.json and SHA256SUMS, not: "
                     + ", ".join(sorted(names)))
    for key in ("sha256", "size"):
        if key in manifest:
            report.error(f"echo-mod.json has \"{key}\": signing changes the DLL's bytes, so the release's "
                         "digests live in SHA256SUMS only")
    if not isinstance(manifest.get("source"), dict):
        report.error("echo-mod.json has no \"source\" object")
    if not isinstance(file, str) or not file.lower().endswith(".dll") or not SAFE_NAME.match(file):
        report.error(f"echo-mod.json's \"file\" isn't a DLL name: {file!r}")
        return None
    zip_path = work / want
    if not zip_path.is_file():
        report.error(f"the release lacks {want}")
        return None
    try:
        outer = (work / "SHA256SUMS").read_text(encoding="utf-8")
        check_sums("SHA256SUMS", outer, {want: zip_path.read_bytes(),
                                         "echo-mod.json": (work / "echo-mod.json").read_bytes()}, report)
    except OSError as e:
        report.error(f"SHA256SUMS: {e}")

    stem = file[:-4]
    allowed = {file, "LICENSE", "NOTICE", "SHA256SUMS"}
    required = {file, "LICENSE", "SHA256SUMS"}
    if manifest.get("settings"):
        allowed.add(f"{stem}.plugin.json")
        required.add(f"{stem}.plugin.json")
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        report.error(f"{want} isn't a zip")
        return None
    contents, seen, total = {}, set(), 0
    with zf:
        for info in zf.infolist():
            name = info.filename
            if info.is_dir() or "/" in name or "\\" in name:
                report.error(f"{want}: {name!r} is in a folder; the zip is flat")
                continue
            if not SAFE_NAME.match(name) or DEVICES.match(name) or name.endswith((".", " ")):
                report.error(f"{want}: {name!r} isn't a name the zip may hold")
                continue
            if name.lower() in seen:
                report.error(f"{want}: {name!r} is there twice (names compare without case on Windows)")
                continue
            seen.add(name.lower())
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or (mode and not stat.S_ISREG(mode)) or info.flag_bits & 0x1:
                report.error(f"{want}: {name!r} is a link, a special entry or encrypted")
                continue
            if name not in allowed:
                report.error(f"{want}: {name!r} isn't one of: {', '.join(sorted(allowed))}")
                continue
            cap = MAX_DLL if name == file else MAX_OTHER
            try:
                with zf.open(info) as f:
                    data = f.read(cap + 1)
            except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as e:
                report.error(f"{want}: can't read {name!r}: {e}")
                continue
            if len(data) > cap:
                report.error(f"{want}: {name!r} is over {cap >> 20} MiB")
                continue
            total += len(data)
            contents[name] = data
    for name in sorted(required - set(contents)):
        report.error(f"{want} has no {name}")
    if "SHA256SUMS" in contents:
        inner = {n: d for n, d in contents.items() if n != "SHA256SUMS"}
        check_sums(f"{want}'s SHA256SUMS", contents["SHA256SUMS"].decode("utf-8", "replace"), inner, report)
    if file not in contents:
        return None
    out = work / "unpacked"
    out.mkdir(exist_ok=True)
    (out / file).write_bytes(contents[file])
    return out / file
