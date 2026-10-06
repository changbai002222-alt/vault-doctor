import io
import json
import unittest
from contextlib import redirect_stdout

from vault_doctor.checks import run_checks
from vault_doctor.cli import main
from vault_doctor.vault import Vault

from helpers import TempVault

DEMO = {
    "好笔记.md": "---\ntags: [a]\n---\n见 [[另一篇]]、![[图.png]]、`[[代码里]]`",
    "另一篇.md": "---\ndate: 1\n---\n正文",
    "断链.md": "---\ndate: 1\n---\n第一行\n[[不存在的笔记|别名]]",
    "无元数据.md": "只有正文",
    "空笔记.md": "---\ndate: 1\n---\n\n   \n",
    "带BOM.md": b"\xef\xbb\xbf---\ndate: 1\n---\nok",
    "_attachments/图.png": b"\x89PNG",
}


def by_check(issues):
    out = {}
    for i in issues:
        out.setdefault(i.check, []).append(i)
    return out


class ChecksTest(unittest.TestCase):
    def test_each_check_finds_exactly_its_problem(self):
        with TempVault(DEMO) as root:
            got = by_check(run_checks(Vault(root)))
        self.assertEqual(set(got), {"broken-link", "no-frontmatter", "empty-note", "bom"})

        (broken,) = got["broken-link"]
        self.assertEqual((broken.path, broken.line), ("断链.md", 5))
        self.assertIn("不存在的笔记", broken.message)

        self.assertEqual([i.path for i in got["no-frontmatter"]], ["无元数据.md"])
        self.assertEqual([i.path for i in got["empty-note"]], ["空笔记.md"])
        self.assertEqual([i.path for i in got["bom"]], ["带BOM.md"])

    def test_only(self):
        with TempVault(DEMO) as root:
            issues = run_checks(Vault(root), ["bom"])
        self.assertEqual({i.check for i in issues}, {"bom"})

    def test_clean_vault(self):
        with TempVault({"a.md": "---\ndate: 1\n---\n[[b]]", "b.md": "---\ndate: 1\n---\nx"}) as root:
            self.assertEqual(run_checks(Vault(root)), [])


class CliTest(unittest.TestCase):
    def run_cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(list(argv))
        return code, buf.getvalue()

    def test_json_output_and_exit_code(self):
        with TempVault(DEMO) as root:
            code, out = self.run_cli("check", root, "--json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["notes"], 6)
        self.assertEqual(data["counts"], {"broken-link": 1, "no-frontmatter": 1, "empty-note": 1, "bom": 1})

    def test_clean_exit_zero(self):
        with TempVault({"a.md": "---\ndate: 1\n---\nx"}) as root:
            code, out = self.run_cli("check", root)
        self.assertEqual(code, 0)
        self.assertIn("合计 0 个问题", out)

    def test_text_report_limit(self):
        files = {f"n{i}.md": "无元数据" for i in range(5)}
        with TempVault(files) as root:
            _, out = self.run_cli("check", root, "--only", "no-frontmatter", "--limit", "2")
        self.assertIn("还有 3 条", out)

    def test_ignore_dir(self):
        with TempVault({"a.md": "---\ndate: 1\n---\nx", "草稿/b.md": "无元数据"}) as root:
            code, _ = self.run_cli("check", root, "--ignore", "草稿")
        self.assertEqual(code, 0)

    def test_missing_dir(self):
        self.assertEqual(self.run_cli("check", "Z:/definitely/not/here")[0], 2)


if __name__ == "__main__":
    unittest.main()
