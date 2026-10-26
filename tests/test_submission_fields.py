"""The submission form's media and credits fields, and that the check reads every field the form has.

    python3 -I -m unittest discover -s tests -v
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import inspect_submission  # noqa: E402
import submission_fields as sf  # noqa: E402

BODY = """### Repository

https://github.com/you/my-cool-mod

### Mod id

my-cool-mod

### EchoVRCE username

You

### What does it do?

Things.

### Screenshots

https://example.com/menu.png | The menu in the lobby
https://example.com/hud.png | The HUD during a match

### Video

https://example.com/demo.mp4

### Credits

You | Wrote the mod | https://github.com/you
Dualgame | Wrote the original rad-links

### Rules

- [x] ok
"""


class Form(unittest.TestCase):
    def test_every_form_field_is_read_by_the_check(self):
        form = (ROOT / ".github" / "ISSUE_TEMPLATE" / "submit-mod.yml").read_text(encoding="utf-8")
        # top-level field labels are indented by 6; checkbox option labels start with `- label:`
        labels = set(re.findall(r"^      label: (.+)$", form, re.M)) - {"Rules"}
        self.assertEqual(labels, set(inspect_submission.SUBMISSION_HEADINGS), labels)

    def test_the_new_fields_parse_from_an_issue_body(self):
        fields = inspect_submission.parse_form(BODY)
        self.assertEqual(sf.parse_screenshots(fields["screenshots"])[0], [
            {"url": "https://example.com/menu.png", "alt": "The menu in the lobby"},
            {"url": "https://example.com/hud.png", "alt": "The HUD during a match"}])
        self.assertEqual(sf.parse_video(fields["video"]), ("https://example.com/demo.mp4", []))
        self.assertEqual(sf.parse_credits(fields["credits"])[0], [
            {"name": "You", "role": "Wrote the mod", "url": "https://github.com/you"},
            {"name": "Dualgame", "role": "Wrote the original rad-links"}])

    def test_unanswered_fields_are_empty(self):
        body = (BODY.split("### Screenshots")[0]
                + "### Screenshots\n\n_No response_\n\n### Video\n\n_No response_\n\n### Credits\n\n_No response_\n")
        fields = inspect_submission.parse_form(body)
        self.assertEqual(sf.parse_screenshots(fields["screenshots"]), ([], []))
        self.assertEqual(sf.parse_video(fields["video"]), ("", []))
        self.assertEqual(sf.parse_credits(fields["credits"]), ([], []))


class Screenshots(unittest.TestCase):
    def errors(self, text):
        return sf.parse_screenshots(text)[1]

    def test_http_refused(self):
        self.assertTrue(self.errors("http://example.com/a.png | x"))

    def test_not_a_link_refused(self):
        self.assertTrue(self.errors("menu.png | x"))

    def test_alt_required(self):
        self.assertTrue(self.errors("https://example.com/a.png"))
        self.assertTrue(self.errors("https://example.com/a.png |  "))

    def test_alt_length(self):
        self.assertTrue(self.errors("https://example.com/a.png | " + "x" * 201))

    def test_at_most_eight(self):
        many = "\n".join(f"https://example.com/{i}.png | x" for i in range(9))
        self.assertEqual(self.errors(many), ["Screenshots: at most 8"])

    def test_a_bad_line_does_not_hide_the_good_ones(self):
        items, errors = sf.parse_screenshots("https://example.com/a.png | ok\nbad")
        self.assertEqual(len(items), 1)
        self.assertEqual(len(errors), 1)


class Video(unittest.TestCase):
    def test_one_https_link(self):
        self.assertEqual(sf.parse_video("https://youtu.be/x")[1], [])

    def test_http_refused(self):
        self.assertTrue(sf.parse_video("http://youtu.be/x")[1])

    def test_two_links_refused(self):
        self.assertEqual(sf.parse_video("https://a.example/x\nhttps://b.example/y")[1], ["Video: one link only"])


class Credits(unittest.TestCase):
    def errors(self, text):
        return sf.parse_credits(text)[1]

    def test_role_required(self):
        self.assertTrue(self.errors("Dualgame"))
        self.assertTrue(self.errors("Dualgame | "))

    def test_name_required(self):
        self.assertTrue(self.errors(" | wrote it"))

    def test_link_must_be_https(self):
        self.assertTrue(self.errors("Dualgame | wrote it | http://github.com/Dualgame"))

    def test_too_many_parts(self):
        self.assertTrue(self.errors("a | b | https://example.com | d"))

    def test_at_most_twenty(self):
        many = "\n".join(f"P{i} | did a thing" for i in range(21))
        self.assertEqual(self.errors(many), ["Credits: at most 20"])


if __name__ == "__main__":
    unittest.main()
