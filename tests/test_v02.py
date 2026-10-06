"""v0.2: config file, fix suggestions, `fix` command."""
import io
import json
import os
import unittest
from contextlib import redirect_stdout

from vault_doctor.checks import run_checks
from vault_doctor.cli import main
from vault_doctor.config import ConfigError, load_config
from vault_doctor.checks import CHECKS
from vault_doctor.fixes import Suggester, render
from vault_doctor.vault import Vault, extract_links

from helpers import TempVault

FM = "---\ndate: 1\n---\n"


def run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(argv))
    return code, buf.getvalue()


def read(root, rel):
    with open(os.path.join(root, *rel.split("/")), "rb") as f:
        return f.read()


class ConfigTest(unittest.TestCase):
    def test_exclude_glob_and_disable(self):
        files = {
            "a.md": "无元数据",
            "导入/b.md": "无元数据",
            "导入/深/c.md": "无元数据",
            "d.md": b"\xef\xbb\xbf" + FM.encode() + b"x",
            ".vault-doctor.json": json.dumps({
                "checks": {"no-frontmatter": {"exclude": ["导入"]}, "bom": {"enabled": False}}}),
        }
        with TempVault(files) as root:
            vault = Vault(root)
            cfg = load_config(root, None, list(CHECKS))
            issues = run_checks(vault, config=cfg)
            self.assertEqual([(i.check, i.path) for i in issues], [("no-frontmatter", "a.md")])
            # --only overrides "enabled": false
            self.assertEqual([i.path for i in run_checks(vault, ["bom"], cfg)], ["d.md"])

    def test_config_ignore_dirs(self):
        files = {"a.md": FM + "x", "草稿/b.md": "无元数据",
                 ".vault-doctor.json": json.dumps({"ignore": ["草稿"]})}
        with TempVault(files) as root:
            self.assertEqual(run_cli("check", root)[0], 0)

    def test_bad_configs(self):
        bad = ['{"nope": 1}', '{"checks": {"zzz": {}}}', '{"checks": {"bom": {"enabled": "no"}}}',
               '{"ignore": "草稿"}', "[1]", "{broken"]
        for text in bad:
            with TempVault({".vault-doctor.json": text}) as root:
                with self.assertRaises(ConfigError, msg=text):
                    load_config(root, None, list(CHECKS))

    def test_bad_config_exit_code(self):
        with TempVault({"a.md": FM + "x", ".vault-doctor.json": "{broken"}) as root:
            self.assertEqual(run_cli("check", root)[0], 2)


class SuggestTest(unittest.TestCase):
    def suggest(self, files, source, link_text):
        with TempVault(files) as root:
            vault = Vault(root)
            note = next(n for n in vault.notes if n.path == source)
            (link,) = [l for l in note.links if l.raw == link_text]
            s = Suggester(vault).suggest(note, link)
            return s

    def test_alias(self):
        files = {"反脆弱——波动.md": "---\nalias:\n  - 反脆弱\n---\nx", "a.md": FM + "[[反脆弱|《反脆弱》]]"}
        s = self.suggest(files, "a.md", "[[反脆弱|《反脆弱》]]")
        self.assertEqual((s.kind, s.replacement), ("alias", "[[反脆弱——波动|《反脆弱》]]"))

    def test_alias_keeps_reader_text_when_no_display(self):
        files = {"反脆弱——波动.md": "---\naliases: [反脆弱, 别的]\n---\nx", "a.md": FM + "[[反脆弱]]"}
        s = self.suggest(files, "a.md", "[[反脆弱]]")
        self.assertEqual(s.replacement, "[[反脆弱——波动|反脆弱]]")

    def test_ambiguous_alias_is_not_suggested(self):
        files = {"甲.md": "---\nalias: 同名\n---\nx", "乙.md": "---\nalias: 同名\n---\nx",
                 "a.md": FM + "[[同名]]"}
        self.assertIsNone(self.suggest(files, "a.md", "[[同名]]"))

    def test_self_alias_is_not_a_fix(self):
        files = {"总地图.md": "---\nalias: 概况\n---\n[[概况]]"}
        self.assertIsNone(self.suggest(files, "总地图.md", "[[概况]]"))

    def test_moved_path(self):
        files = {"新/位置/笔记.md": "x", "a.md": FM + "[[旧/路径/笔记#小节|说明]]"}
        s = self.suggest(files, "a.md", "[[旧/路径/笔记#小节|说明]]")
        self.assertEqual((s.kind, s.replacement), ("moved", "[[笔记#小节|说明]]"))

    def test_moved_needs_a_unique_target(self):
        files = {"甲/笔记.md": "x", "乙/笔记.md": "x", "a.md": FM + "[[旧/笔记]]"}
        self.assertIsNone(self.suggest(files, "a.md", "[[旧/笔记]]"))

    def test_prefix_rename(self):
        files = {"课表——2026.md": "x", "a.md": FM + "[[课表|课表笔记]]"}
        s = self.suggest(files, "a.md", "[[课表|课表笔记]]")
        self.assertEqual((s.kind, s.replacement), ("prefix", "[[课表——2026|课表笔记]]"))

    def test_prefix_must_stop_at_a_separator(self):
        files = {"反脆弱性.md": "x", "a.md": FM + "[[反脆弱]]"}
        self.assertIsNone(self.suggest(files, "a.md", "[[反脆弱]]"))

    def test_prefix_ambiguous(self):
        files = {"概念——甲.md": "x", "概念——乙.md": "x", "a.md": FM + "[[概念]]"}
        self.assertIsNone(self.suggest(files, "a.md", "[[概念]]"))

    def test_render_keeps_table_pipe_and_embed(self):
        (link,) = extract_links("| [[旧\\|说明]] |")
        self.assertEqual(render(link, "新", False), "[[新\\|说明]]")
        (emb,) = extract_links("![[旧.png]]")
        self.assertEqual(render(emb, "新.png", True), "![[新.png]]")


class FixCommandTest(unittest.TestCase):
    FILES = {
        "目标——全名.md": "---\nalias: 目标\n---\nx",
        "来源.md": FM + "见 [[目标]] 和 [[旧/目标——全名]] 和 [[改过名|名]]\n`[[目标]]` 不动\n",
        "改过名——新.md": "x",
        "带BOM.md": b"\xef\xbb\xbf" + FM.encode() + b"ok",
        "win.md": (FM + "第二行 [[目标]]\n").replace("\n", "\r\n").encode(),
        "无关.md": FM + "没有问题\n",
    }

    def test_preview_changes_nothing(self):
        with TempVault(self.FILES) as root:
            before = {k: read(root, k) for k in self.FILES}
            code, out = run_cli("fix", root)
            self.assertEqual(code, 0)
            self.assertIn("预览", out)
            self.assertEqual(before, {k: read(root, k) for k in self.FILES})

    def test_write_applies_only_safe_kinds(self):
        with TempVault(self.FILES) as root:
            run_cli("fix", root, "--write")
            text = read(root, "来源.md").decode("utf-8")
            self.assertIn("[[目标——全名|目标]]", text)
            self.assertIn("[[目标——全名|旧/目标——全名]]".replace("|旧/目标——全名", ""), text)
            self.assertIn("[[改过名|名]]", text)          # prefix is not applied by default
            self.assertIn("`[[目标]]` 不动", text)       # code untouched
            self.assertFalse(read(root, "带BOM.md").startswith(b"\xef\xbb\xbf"))
            self.assertEqual(read(root, "无关.md"), (FM + "没有问题\n").encode())
            self.assertEqual([n for n in os.listdir(root) if n.endswith(".vd-tmp")], [])

    def test_crlf_is_preserved(self):
        with TempVault(self.FILES) as root:
            run_cli("fix", root, "--write")
            raw = read(root, "win.md")
            self.assertIn(b"[[\xe7\x9b\xae\xe6\xa0\x87\xe2\x80\x94\xe2\x80\x94\xe5\x85\xa8\xe5\x90\x8d|\xe7\x9b\xae\xe6\xa0\x87]]", raw)
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))

    def test_accept_prefix(self):
        with TempVault(self.FILES) as root:
            run_cli("fix", root, "--write", "--accept", "prefix")
            self.assertIn("[[改过名——新|名]]", read(root, "来源.md").decode("utf-8"))

    def test_second_run_is_a_no_op_and_check_is_clean(self):
        with TempVault(self.FILES) as root:
            run_cli("fix", root, "--write", "--accept", "alias", "--accept", "moved", "--accept", "prefix")
            snapshot = {k: read(root, k) for k in self.FILES}
            _, out = run_cli("fix", root, "--write", "--accept", "alias", "--accept", "moved", "--accept", "prefix")
            self.assertIn("0 个文件", out)
            self.assertEqual(snapshot, {k: read(root, k) for k in self.FILES})
            self.assertEqual(run_cli("check", root, "--only", "broken-link", "--only", "bom")[0], 0)

    def test_bom_kept_when_only_links_fixed(self):
        files = {"目标——全名.md": "---\nalias: 目标\n---\nx",
                 "a.md": b"\xef\xbb\xbf" + (FM + "[[目标]]").encode()}
        with TempVault(files) as root:
            run_cli("fix", root, "--write", "--no-bom")
            raw = read(root, "a.md")
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            self.assertIn("[[目标——全名|目标]]".encode(), raw)

    def test_config_exclude_protects_from_fix(self):
        files = dict(self.FILES)
        files[".vault-doctor.json"] = json.dumps({"checks": {
            "bom": {"exclude": ["带BOM.md"]}, "broken-link": {"exclude": ["来源.md"]}}})
        with TempVault(files) as root:
            run_cli("fix", root, "--write")
            self.assertTrue(read(root, "带BOM.md").startswith(b"\xef\xbb\xbf"))
            self.assertIn("[[目标]]", read(root, "来源.md").decode("utf-8"))

    def test_mixed_newlines_and_bad_utf8_are_skipped(self):
        files = {"目标——全名.md": "---\nalias: 目标\n---\nx",
                 "混用.md": (FM + "[[目标]]\r\n另一行\n").encode(),
                 "坏编码.md": FM.encode() + b"[[\xe7\x9b\xae\xe6\xa0\x87]] \xff\xfe"}
        with TempVault(files) as root:
            before = {k: read(root, k) for k in ("混用.md", "坏编码.md")}
            _, out = run_cli("fix", root, "--write")
            self.assertIn("跳过", out)
            self.assertEqual(before, {k: read(root, k) for k in before})

    def test_check_reports_suggestions(self):
        with TempVault(self.FILES) as root:
            _, out = run_cli("check", root, "--json", "--only", "broken-link")
            issues = json.loads(out)["issues"]
            kinds = {i["message"].split("找不到目标：")[1].split("  →")[0]: i.get("fix_kind") for i in issues}
            self.assertEqual(kinds["[[目标]]"], "alias")
            self.assertEqual(kinds["[[旧/目标——全名]]"], "moved")
            self.assertEqual(kinds["[[改过名|名]]"], "prefix")


if __name__ == "__main__":
    unittest.main()
