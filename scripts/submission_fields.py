"""Parses the submission form's media and credits fields into the shapes the entry schema
(schema/entry.schema.json: media, credits) takes. One item per line, parts separated by ` | `:

    Screenshots   https://example.com/menu.png | The mod's menu in the lobby
    Video         https://example.com/demo.mp4
    Credits       Dualgame | Wrote the original rad-links | https://github.com/Dualgame

Every function returns (value, errors): errors are sentences for the author, never exceptions. The limits
are the schema's. Python 3.9+, standard library only.
"""
import re

HTTPS = re.compile(r"^https://[^\s/]+(?:/\S*)?$")
MAX_URL, MAX_SCREENSHOTS, MAX_CREDITS = 500, 8, 20


def lines(text):
    """The non-empty lines of a form answer; an unanswered field is none."""
    text = (text or "").strip()
    return [] if text == "_No response_" else [l.strip() for l in text.splitlines() if l.strip()]


def url_error(url):
    if not HTTPS.match(url) or len(url) > MAX_URL:
        return f"`{url[:80]}` isn't an https:// link"
    return None


def parse_screenshots(text):
    items, errors = [], []
    for line in lines(text):
        url, _, alt = (p.strip() for p in line.partition("|"))
        if url_error(url):
            errors.append(f"Screenshots: {url_error(url)}; write `https://link | what it shows`")
        elif not alt or len(alt) > 200:
            errors.append(f"Screenshots: say in a few words what {url[:60]} shows (up to 200 characters), after a `|`")
        else:
            items.append({"url": url, "alt": alt})
    if len(items) > MAX_SCREENSHOTS:
        errors.append(f"Screenshots: at most {MAX_SCREENSHOTS}")
    return items, errors


def parse_video(text):
    found = lines(text)
    if not found:
        return "", []
    if len(found) > 1:
        return "", ["Video: one link only"]
    return ("", [f"Video: {url_error(found[0])}"]) if url_error(found[0]) else (found[0], [])


def parse_credits(text):
    items, errors = [], []
    for line in lines(text):
        parts = [p.strip() for p in line.split("|")]
        name, role, url = (parts + ["", ""])[:3]
        if len(parts) > 3 or not name or len(name) > 80 or not role or len(role) > 120:
            errors.append(f"Credits: `{line[:80]}` isn't `name | what they did | link (optional)`")
        elif url and url_error(url):
            errors.append(f"Credits: {url_error(url)} (the link for {name})")
        else:
            items.append({"name": name, "role": role, **({"url": url} if url else {})})
    if len(items) > MAX_CREDITS:
        errors.append(f"Credits: at most {MAX_CREDITS}")
    return items, errors
