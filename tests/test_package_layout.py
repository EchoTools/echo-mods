"""The submission check reads the plugin-release layout (release-signer docs/plugin-release.md section 4).
A fixture release in that shape is built here; every rule has a negative control.

    python3 -I -m unittest discover -s tests -v
"""
import hashlib
import io
import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import inspect_submission  # noqa: E402
import package_layout  # noqa: E402

DLL = b"MZ" + b"\0" * 200
MANIFEST = {"schema": 1, "id": "example-mod", "name": "Example mod", "summary": "x", "author": "a", "version": "0.1.0",
            "kind": "mod", "file": "ExampleMod.dll", "api": 5, "capabilities": ["observes-only"], "target": "client",
            "license": "MIT", "package": "example-mod-v0.1.0-windows.zip", "source": {"repo": "a/example-mod"}}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sums(files):
    return "".join(f"{sha(d)}  {n}\n" for n, d in files.items()).encode()


class Rep:
    def __init__(self):
        self.errors = []

    def error(self, text):
        self.errors.append(text)

    def warn(self, text):
        pass


def zip_bytes(members):
    """members: [(name, bytes, mode or None)]"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data, mode in members:
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = (mode or 0o100644) << 16
            zf.writestr(info, data)
    return buf.getvalue()


def release(tmp, members=None, manifest=None, outer=None, extra_assets=()):
    """Writes a release into `tmp` as the download step would; returns (manifest, asset names)."""
    manifest = dict(MANIFEST, **(manifest or {}))
    body = {"ExampleMod.dll": DLL, "LICENSE": b"MIT\n", "NOTICE": b"credits\n"}
    if members is None:
        members = [(n, d, None) for n, d in body.items()] + [("SHA256SUMS", sums(body), None)]
    package = zip_bytes(members)
    manifest_bytes = json.dumps(manifest).encode()
    (tmp / "echo-mod.json").write_bytes(manifest_bytes)
    name = f"{manifest['id']}-v{manifest['version']}-windows.zip"
    (tmp / name).write_bytes(package)
    (tmp / "SHA256SUMS").write_bytes(outer if outer is not None else sums({name: package, "echo-mod.json": manifest_bytes}))
    return manifest, [name, "echo-mod.json", "SHA256SUMS", *extra_assets]


class Package(unittest.TestCase):
    def check(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            manifest, assets = release(tmp, **{k: v for k, v in kw.items() if k != "assets"})
            rep = Rep()
            dll = package_layout.check_package(tmp, manifest, kw.get("assets", assets), rep)
            return rep.errors, (dll.read_bytes() if dll else None)

    def fails(self, expect, **kw):
        errors, _ = self.check(**kw)
        self.assertTrue(any(expect in e for e in errors), f"{expect!r} not in {errors}")

    def test_the_fixture_release_passes_and_unpacks_the_dll(self):
        errors, dll = self.check()
        self.assertEqual(errors, [])
        self.assertEqual(dll, DLL)

    def test_notice_is_optional(self):
        body = {"ExampleMod.dll": DLL, "LICENSE": b"MIT\n"}
        members = [(n, d, None) for n, d in body.items()] + [("SHA256SUMS", sums(body), None)]
        self.assertEqual(self.check(members=members)[0], [])

    def test_settings_file_is_required_when_declared(self):
        self.fails("has no ExampleMod.plugin.json", manifest={"settings": {"schema": 1, "settings": {}}})

    def test_package_name_must_match(self):
        self.fails("\"package\" is 'other.zip'", manifest={"package": "other.zip"})

    def test_exactly_three_assets(self):
        self.fails("exactly", extra_assets=["ExampleMod.dll"])

    def test_manifest_carries_no_digests(self):
        self.fails("has \"sha256\"", manifest={"sha256": "0" * 64})
        self.fails("has \"size\"", manifest={"size": 5})

    def test_manifest_needs_source(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            manifest, assets = release(tmp)
            manifest.pop("source")
            rep = Rep()
            package_layout.check_package(tmp, manifest, assets, rep)
        self.assertIn("no \"source\" object", " ".join(rep.errors))

    def test_outer_sums_must_match_the_zip(self):
        self.fails("doesn't match SHA256SUMS", outer=sums({"example-mod-v0.1.0-windows.zip": b"x", "echo-mod.json": b"{}"}))

    def test_outer_sums_must_not_name_others(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            manifest, assets = release(tmp)
            (tmp / "SHA256SUMS").write_bytes((tmp / "SHA256SUMS").read_bytes() + sums({"extra.dll": b"x"}))
            rep = Rep()
            package_layout.check_package(tmp, manifest, assets, rep)
        self.assertIn("names files it shouldn't", " ".join(rep.errors))

    def test_zip_is_flat(self):
        self.fails("is in a folder", members=[("dir/ExampleMod.dll", DLL, None), ("LICENSE", b"x", None)])

    def test_link_entries_refused(self):
        self.fails("a link, a special entry", members=[("ExampleMod.dll", b"target", 0o120777), ("LICENSE", b"x", None)])

    def test_unlisted_entry_refused(self):
        body = {"ExampleMod.dll": DLL, "LICENSE": b"x", "evil.exe": b"x"}
        members = [(n, d, None) for n, d in body.items()] + [("SHA256SUMS", sums(body), None)]
        self.fails("'evil.exe' isn't one of", members=members)

    def test_license_required(self):
        body = {"ExampleMod.dll": DLL}
        self.fails("has no LICENSE", members=[("ExampleMod.dll", DLL, None), ("SHA256SUMS", sums(body), None)])

    def test_dll_required(self):
        body = {"LICENSE": b"x"}
        errors, dll = self.check(members=[("LICENSE", b"x", None), ("SHA256SUMS", sums(body), None)])
        self.assertIsNone(dll)
        self.assertTrue(any("has no ExampleMod.dll" in e for e in errors))

    def test_inner_sums_must_match(self):
        body = {"ExampleMod.dll": DLL, "LICENSE": b"x"}
        wrong = {"ExampleMod.dll": b"other", "LICENSE": b"x"}
        members = [(n, d, None) for n, d in body.items()] + [("SHA256SUMS", sums(wrong), None)]
        self.fails("ExampleMod.dll doesn't match", members=members)

    def test_inner_sums_must_cover_every_entry(self):
        members = [("ExampleMod.dll", DLL, None), ("LICENSE", b"x", None), ("SHA256SUMS", sums({"ExampleMod.dll": DLL}), None)]
        self.fails("has no line for LICENSE", members=members)

    def test_names_compare_without_case(self):
        body = {"ExampleMod.dll": DLL, "LICENSE": b"x"}
        members = [(n, d, None) for n, d in body.items()] + [("license", b"y", None), ("SHA256SUMS", sums(body), None)]
        self.fails("there twice", members=members)

    def test_windows_device_names_refused(self):
        self.fails("isn't a name the zip may hold", members=[("ExampleMod.dll", DLL, None), ("NUL.txt", b"x", None)])

    def test_dll_size_cap(self):
        old, package_layout.MAX_DLL = package_layout.MAX_DLL, 100
        try:
            self.fails("is over", )
        finally:
            package_layout.MAX_DLL = old

    def test_not_a_zip(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            manifest, assets = release(tmp)
            (tmp / assets[0]).write_bytes(b"not a zip")
            rep = Rep()
            self.assertIsNone(package_layout.check_package(tmp, manifest, assets, rep))
        self.assertIn("isn't a zip", " ".join(rep.errors))


class Inspect(unittest.TestCase):
    """The check picks the layout from echo-mod.json, and the manifest and tag rules still apply."""

    def test_layout_follows_package(self):
        self.assertEqual(inspect_submission.release_layout(MANIFEST), "package")
        loose = {k: v for k, v in MANIFEST.items() if k != "package"}
        self.assertEqual(inspect_submission.release_layout(loose), "loose")
        self.assertEqual(inspect_submission.release_layout(dict(MANIFEST, package=None)), "loose")

    def run_release(self, tag="v0.1.0", prerelease=False):
        calls = []
        check_mod = types.SimpleNamespace(
            check_manifest=lambda m, r, root, published: calls.append(("manifest", published)),
            SEMVER=__import__("re").compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$"),
            is_prerelease=lambda v: "-" in v)
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            manifest, assets = release(tmp)
            rep = Rep()
            dll = inspect_submission.check_package_release(check_mod, tmp, manifest, tag, prerelease, assets, rep)
        return calls, rep.errors, dll

    def test_fixture_release_passes(self):
        calls, errors, dll = self.run_release()
        self.assertEqual((calls, errors), ([("manifest", True)], []))
        self.assertEqual(dll.name, "ExampleMod.dll")

    def test_tag_must_match_the_version(self):
        self.assertTrue(any("doesn't match" in e for e in self.run_release(tag="v0.2.0")[1]))

    def test_prerelease_flag_must_match(self):
        self.assertTrue(any("prerelease flag" in e for e in self.run_release(prerelease=True)[1]))


if __name__ == "__main__":
    unittest.main()
