#!/usr/bin/env python3
"""Validates the listed entries (mods/<id>.json) against schema/entry.schema.json, then checks what a
schema can't say: the file name, the tag and asset names, the order of versions, the fork, and that
signing changed the bytes.

    validate_entries.py                      # every mods/*.json
    validate_entries.py mods/my-mod.json     # these files
    validate_entries.py --log validate.jsonl # also append the records to a file

One JSON line per entry on stdout (who: the file and its sha256, what: the checks, outcome: ok and the
errors), one summary line last. Exit 0 when every entry is valid, 1 when one is not, 2 when the check
couldn't run (no schema, no jsonschema): a gate that can't run fails.

Needs `jsonschema` (pip install jsonschema==4.26.0). Python 3.9+.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print(json.dumps({"event": "validate_entries.cannot_run", "error": "the jsonschema package is missing"}))
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
SEMVER_CORE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def core(version):
    return tuple(int(x) for x in SEMVER_CORE.match(version).groups())


def cross_checks(path, entry):
    """What the schema can't express. Only runs on an entry that already passed the schema."""
    errors = []
    mod_id = entry["id"]
    if path.name != f"{mod_id}.json":
        errors.append(f"the file is called {path.name}, the id says {mod_id}.json")
    versions = entry["versions"]
    for key in ("version", "tag"):
        seen = [v[key] for v in versions]
        if len(set(seen)) != len(seen):
            errors.append(f"versions: a {key} is listed twice")
    for v in versions:
        label = f"version {v['version']}"
        if v["tag"] != f"v{v['version']}":
            errors.append(f"{label}: the tag is {v['tag']}, it must be v{v['version']}")
        if v.get("prerelease", False) != ("-" in v["version"].split("+")[0]):
            errors.append(f"{label}: prerelease must be {'true' if '-' in v['version'].split('+')[0] else 'false or left out'}"
                          " (a semver with a -suffix is a prerelease)")
        assets = v["assets"]
        for role, want in (("package", f"{mod_id}-{v['tag']}-windows.zip"), ("manifest", "echo-mod.json"),
                           ("sums", "SHA256SUMS")):
            if assets[role]["name"] != want:
                errors.append(f"{label}: assets.{role}.name is {assets[role]['name']}, it must be {want}")
        signer = v["signer"]
        if signer["status"] in ("signed", "revoked"):
            # Signing replaces the DLL and so the zip, and regenerates the sums. A signed digest equal
            # to the attested one means nothing was signed.
            for role in ("package", "sums"):
                if signer[role]["sha256"] == assets[role]["sha256"]:
                    errors.append(f"{label}: signer.{role} has the same sha256 as the attested assets.{role}: "
                                  "signing changes it")
    for older, newer in zip(versions[1:], versions):
        if core(older["version"]) > core(newer["version"]):
            errors.append(f"versions: {older['version']} is listed after {newer['version']}; newest first")
    if any(v["signer"]["status"] != "unsigned" for v in versions):
        if "fork" not in entry:
            errors.append("fork: required once a version is past signer status 'unsigned'")
    if "fork" in entry and entry["fork"]["repo"].lower() == entry["source"]["repo"].lower():
        errors.append("fork.repo is the author's own repo; it must be the EchoTools copy")
    return errors


def check_file(path, validator):
    raw = path.read_bytes()
    record = {"event": "validate_entries.entry", "at": now(), "file": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
              "id": None, "ok": False, "errors": []}
    try:
        entry = json.loads(raw.decode("utf-8"))
    except ValueError as e:
        record["errors"].append(f"not JSON: {e}")
        return record
    if isinstance(entry, dict):
        record["id"] = entry.get("id")
    schema_errors = sorted(validator.iter_errors(entry), key=lambda e: list(e.absolute_path))
    for e in schema_errors:
        where = "/".join(str(p) for p in e.absolute_path) or "(entry)"
        record["errors"].append(f"{where}: {e.message}")
    if not schema_errors:
        record["errors"].extend(cross_checks(path, entry))
    record["ok"] = not record["errors"]
    return record


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--schema", type=Path, default=ROOT / "schema" / "entry.schema.json")
    ap.add_argument("--log", type=Path, help="append the records to this file as well")
    args = ap.parse_args(argv)

    sink = open(args.log, "a", encoding="utf-8") if args.log else None

    def emit(record):
        line = json.dumps(record, sort_keys=True)
        print(line, flush=True)
        if sink:
            sink.write(line + "\n")
            sink.flush()

    try:
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except Exception as e:  # noqa: BLE001
        emit({"event": "validate_entries.cannot_run", "at": now(), "schema": str(args.schema), "error": str(e)})
        return 2
    validator = Draft202012Validator(schema)

    paths = args.paths or sorted((ROOT / "mods").glob("*.json"))
    bad = 0
    for path in paths:
        record = check_file(path, validator)
        bad += not record["ok"]
        emit(record)
    emit({"event": "validate_entries.done", "at": now(), "entries": len(paths), "invalid": bad})
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
