#!/usr/bin/env python3
"""Turns inspect_submission.py's report into the submission's comment and labels. Runs in the job
that may write issues; it never runs anything from the submission, and treats the report's text as
untrusted (it can quote the submitted repo).

    report_submission.py report.json

Reads ISSUE_NUMBER, GH_TOKEN, GITHUB_REPOSITORY and, if set, VT_API_KEY from the environment.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

MARKER = "<!-- echo-mods-check -->"
REPO = os.environ.get("GITHUB_REPOSITORY", "EchoTools/echo-mods")
ICONS = {"ok": "✅", "warning": "⚠️", "error": "❌"}


def clean(text, limit=600):
    """Text from the report, made safe to put into markdown: no HTML, no mentions, no closing of the
    code spans it goes in, bounded length."""
    text = str(text)[:limit]
    return (text.replace("<", "&lt;").replace(">", "&gt;").replace("@", "@​")
            .replace("\r", "").replace("|", "\\|"))


def virustotal(sha):
    key = os.environ.get("VT_API_KEY")
    if not key or not sha:
        return None
    req = urllib.request.Request(f"https://www.virustotal.com/api/v3/files/{sha}", headers={"x-apikey": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            stats = json.load(r)["data"]["attributes"]["last_analysis_stats"]
        return stats
    except urllib.error.HTTPError as e:
        return {"unknown": True} if e.code == 404 else None
    except Exception:  # noqa: BLE001
        return None


def comment_body(report):
    items, facts = report["items"], report["facts"]
    vt = virustotal(facts.get("sha256"))
    if vt is not None:
        if vt.get("unknown"):
            items.append(["warning", "VirusTotal doesn't know the file yet."])
        elif vt.get("malicious", 0) or vt.get("suspicious", 0):
            items.append(["warning", f"VirusTotal: {vt.get('malicious', 0)} engines say malicious, "
                                     f"{vt.get('suspicious', 0)} suspicious (new DLLs often get false positives)."])
        else:
            items.append(["ok", "VirusTotal: no engine flags it."])
    passed = not any(level == "error" for level, _ in items)

    lines = [MARKER, "## Automatic check: " + ("passed" if passed else "something to fix"), ""]
    for level, text in items:
        lines.append(f"- {ICONS.get(level, '•')} {clean(text)}")
    lines += ["", "<details><summary>What the check found</summary>", "", "| | |", "|---|---|"]
    for key in ("repo", "tag", "version", "prerelease", "kind", "file", "sha256", "size", "capabilities", "target",
                "visibility", "license", "imports", "attested_commit", "account_age_days", "echovrce"):
        if key in facts:
            value = facts[key]
            if isinstance(value, list):
                value = ", ".join(map(str, value))
            lines.append(f"| {key} | `{clean(value, 300).replace('`', '')}` |")
    if facts.get("release_url", "").startswith("https://github.com/"):
        lines.append(f"| release | {clean(facts['release_url'], 200)} |")
    lines += ["", "</details>", ""]
    if passed:
        lines.append("A maintainer reviews the mod next. Nothing to do for now.")
    else:
        lines.append("Fix what's marked ❌, then edit this issue or comment `/check` to run the check again.")
    return "\n".join(lines), passed


def gh(*args, input_text=None):
    return subprocess.run(["gh", *args], input=input_text, capture_output=True, text=True, check=True).stdout


def main():
    report = json.load(open(sys.argv[1], encoding="utf-8"))
    number = os.environ["ISSUE_NUMBER"]
    body, passed = comment_body(report)

    comments = json.loads(gh("api", f"repos/{REPO}/issues/{number}/comments?per_page=100"))
    mine = [c for c in comments if c["user"]["login"] == "github-actions[bot]" and MARKER in c["body"]]
    payload = json.dumps({"body": body})
    if mine:
        gh("api", "-X", "PATCH", f"repos/{REPO}/issues/comments/{mine[-1]['id']}", "--input", "-", input_text=payload)
    else:
        gh("api", "-X", "POST", f"repos/{REPO}/issues/{number}/comments", "--input", "-", input_text=payload)

    add, remove = ("checks-passed", "checks-failed") if passed else ("checks-failed", "checks-passed")
    gh("issue", "edit", number, "-R", REPO, "--add-label", add, "--remove-label", remove)


if __name__ == "__main__":
    main()
