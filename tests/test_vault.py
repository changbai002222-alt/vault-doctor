import unittest

from vault_doctor.vault import Vault, extract_links, split_frontmatter

from helpers import TempVault


class SplitFrontmatterTest(unittest.TestCase):
    def test_reads_top_level_keys(self):
        fm, body = split_frontmatter("---\ntags:\n  - a\ndate: 2026-10-07\n---\n# 标题\n")
        self.assertEqual(set(fm), {"tags", "date"})
        self.assertEqual(fm["date"], "2026-10-07")
        self.assertEqual(body, "# 标题\n")

    def test_no_block(self):
        fm, body = split_frontmatter("# 只有正文\n")
        self.assertIsNone(fm)
        self.assertEqual(body, "# 只有正文\n")

    def test_unclosed_block_is_body(self):
        fm, _ = split_frontmatter("---\ntags: a\n正文没有结束线\n")
        self.assertIsNone(fm)

    def test_empty_block(self):
        fm, body = split_frontmatter("---\n---\n正文")
        self.assertEqual(fm, {})
        self.assertEqual(body, "正文")


class ExtractLinksTest(unittest.TestCase):
    def targets(self, text):
        return [l.target for l in extract_links(text)]

    def test_alias_heading_block(self):
        text = "[[甲|显示名]] [[乙#小节]] [[丙^abc]] [[丁#小节|别名]]"
        self.assertEqual(self.targets(text), ["甲", "乙", "丙", "丁"])

    def test_escaped_pipe_in_table(self):
        self.assertEqual(self.targets("| [[笔记\\|别名]] | x |"), ["笔记"])

    def test_embed_flag(self):
        (link,) = extract_links("![[图.png]]")
        self.assertTrue(link.embed)
        self.assertEqual(link.target, "图.png")

    def test_same_note_heading_is_skipped(self):
        self.assertEqual(self.targets("[[#本页小节]]"), [])

    def test_code_is_ignored(self):
        text = "`[[行内]]`\n```\n[[代码块]]\n```\n~~~md\n[[波浪线]]\n~~~\n[[真的]]"
        self.assertEqual(self.targets(text), ["真的"])

    def test_line_numbers_survive_code_blocks(self):
        text = "第一行\n```\na\nb\n```\n[[目标]]"
        (link,) = extract_links(text)
        self.assertEqual(link.line, 6)


class VaultTest(unittest.TestCase):
    def test_loads_and_resolves(self):
        files = {
            "笔记甲.md": "---\ndate: 1\n---\n[[子目录/笔记乙]]",
            "子目录/笔记乙.md": "正文",
            "_attachments/图.png": b"\x89PNG",
            ".obsidian/workspace.md": "应该被跳过",
            ".backup/旧笔记.md": "隐藏目录同样跳过",
            "node_modules/x.md": "也跳过",
        }
        with TempVault(files) as root:
            v = Vault(root)
            self.assertEqual(sorted(n.path for n in v.notes), ["子目录/笔记乙.md", "笔记甲.md"])
            for target in ["笔记乙", "子目录/笔记乙", "笔记乙.md", "图.png",
                           "_attachments/图.png", "笔记甲", "子目录\\笔记乙"]:
                self.assertTrue(v.resolves(target), target)
            for target in ["不存在", "图", "其他目录/笔记乙", "workspace", "旧笔记", "x"]:
                self.assertFalse(v.resolves(target), target)

    def test_case_insensitive(self):
        with TempVault({"Personal AI OS.md": "x"}) as root:
            self.assertTrue(Vault(root).resolves("personal ai os"))

    def test_bom_and_crlf(self):
        with TempVault({"a.md": b"\xef\xbb\xbf---\r\ndate: 1\r\n---\r\n\xe6\xad\xa3\xe6\x96\x87\r\n"}) as root:
            (note,) = Vault(root).notes
            self.assertTrue(note.has_bom)
            self.assertEqual(note.frontmatter, {"date": "1"})
            self.assertEqual(note.body.strip(), "正文")


if __name__ == "__main__":
    unittest.main()
