"""Vaults that are set up differently from the author's own."""
import io
import unittest
from contextlib import redirect_stdout

from vault_doctor.checks import run_checks
from vault_doctor.cli import main
from vault_doctor.vault import Vault, extract_md_links

from helpers import TempVault

FM = "---\ndate: 1\n---\n"


def broken(files):
    with TempVault(files) as root:
        return [(i.path, i.line, i.message.split("  →")[0]) for i in run_checks(Vault(root), ["broken-link"])]


class RelativeWikilinkTest(unittest.TestCase):
    """Obsidian's "relative path" link format writes [[../other/b]]."""

    def test_relative_wikilinks_resolve_from_the_note(self):
        files = {"folder/a.md": FM + "[[../other/b]] [[./c]] [[../other/b.md]]",
                 "other/b.md": FM + "x", "folder/c.md": FM + "x"}
        self.assertEqual(broken(files), [])

    def test_broken_relative_wikilink_is_reported_but_never_rewritten(self):
        files = {"folder/a.md": FM + "[[../elsewhere/b]]", "other/b.md": FM + "x"}
        with TempVault(files) as root:
            (issue,) = run_checks(Vault(root), ["broken-link"])
            self.assertIsNone(issue.suggestion)

    def test_cannot_escape_the_vault(self):
        self.assertEqual(len(broken({"a.md": FM + "[[../../etc/x]]"})), 1)


class MarkdownLinkTest(unittest.TestCase):
    def test_resolution(self):
        files = {
            "a.md": FM + "[ok](b.md) [no ext](b) [sub](sub/c.md) [root](/sub/c.md) "
                         "[enc](sub/d%20e.md) [anchor](b.md#h) [img](![x](img.png)",
            "b.md": FM + "x", "sub/c.md": FM + "x", "sub/d e.md": FM + "x", "img.png": b"\x89PNG",
        }
        self.assertEqual(broken(files), [])

    def test_missing_target_is_reported_with_line(self):
        files = {"a.md": FM + "第一行\n[坏](missing.md) 和 ![图](gone.png)"}
        got = broken(files)
        self.assertEqual([(p, l) for p, l, _ in got], [("a.md", 5), ("a.md", 5)])

    def test_external_and_special_links_are_ignored(self):
        text = ("[web](https://x.com/a.md) [mail](mailto:a@b.c) [proto](//cdn/x.js) "
                "[anchor](#top) [vault](obsidian://open?vault=v) `[code](nope.md)`")
        self.assertEqual(broken({"a.md": FM + text}), [])

    def test_title_and_angle_brackets(self):
        files = {"a.md": FM + '[t](b.md "标题") [sp](<my note.md>)', "b.md": FM + "x", "my note.md": FM + "x"}
        self.assertEqual(broken(files), [])

    def test_md_links_are_never_rewritten_by_fix(self):
        files = {"a.md": FM + "[坏](missing.md)"}
        with TempVault(files) as root:
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["fix", root, "--write"])
            self.assertIn("0 个文件", buf.getvalue())

    def test_extract_keeps_embed_flag(self):
        (link,) = extract_md_links("![图](a.png)")
        self.assertTrue(link.embed)


class PlaceholderTest(unittest.TestCase):
    def test_template_syntax_is_not_a_link(self):
        text = FM + "[[{{title}}]] [[<% tp.file.title %>]] [x]({{path}}) [[${name}]]"
        self.assertEqual(broken({"T_模板.md": text}), [])


class NoFrontmatterVaultTest(unittest.TestCase):
    def run_check(self, files):
        with TempVault(files) as root:
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["check", root])
            return buf.getvalue()

    def test_hint_when_vault_does_not_use_frontmatter(self):
        out = self.run_check({f"n{i}.md": "# 正文" for i in range(5)})
        self.assertIn("看起来这个库不用它", out)

    def test_no_hint_when_only_a_few_are_missing(self):
        files = {f"n{i}.md": FM + "x" for i in range(9)}
        files["x.md"] = "无"
        self.assertNotIn("看起来这个库不用它", self.run_check(files))


if __name__ == "__main__":
    unittest.main()
