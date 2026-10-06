"""Command line entry: vault-doctor check|fix <vault> [options]."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

from . import __version__
from .checks import CHECKS, TITLES, enabled_checks, run_checks
from .config import CONFIG_NAME, ConfigError, load_config
from .fixes import ALL_KINDS, KIND_TITLES, SAFE_KINDS, plan_fixes, write_fix
from .vault import DEFAULT_IGNORE, Vault


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("vault", help="库的根目录")
    p.add_argument("--ignore", action="append", default=[], metavar="DIR",
                   help="额外跳过的目录名，可重复（. 开头的隐藏目录和 node_modules 总是跳过，与 Obsidian 一致）")
    p.add_argument("--config", metavar="FILE",
                   help=f"配置文件路径（默认读库根目录的 {CONFIG_NAME}，没有就用默认值）")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vault-doctor", description="Obsidian 知识库体检工具")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="体检一个库（只读，不改任何文件）")
    _common(c)
    c.add_argument("--only", action="append", choices=list(CHECKS), metavar="CHECK",
                   help=f"只跑某项检查，可重复；可选：{', '.join(CHECKS)}")
    c.add_argument("--json", action="store_true", help="输出 JSON，方便接脚本")
    c.add_argument("--limit", type=int, default=20,
                   help="每项最多列出多少条，0 = 全部（默认 20；--json 不受影响）")

    f = sub.add_parser("fix", help="修复能确定答案的问题：默认只预览，加 --write 才写盘")
    _common(f)
    f.add_argument("--write", action="store_true", help="真的写入文件（先确认库已用 git 等备份）")
    f.add_argument("--accept", action="append", choices=list(ALL_KINDS), metavar="KIND",
                   help=f"接受哪些断链修复，可重复；默认 {' '.join(SAFE_KINDS)}，"
                        f"prefix（按名字前缀猜改名）需显式加上")
    f.add_argument("--no-links", action="store_true", help="不修断链")
    f.add_argument("--no-bom", action="store_true", help="不去 BOM")
    return p


def _load(args):
    """Return (vault, config) or raise ConfigError."""
    config = load_config(os.path.abspath(args.vault), args.config, list(CHECKS))
    ignore = DEFAULT_IGNORE | set(config.ignore) | set(args.ignore)
    return Vault(args.vault, ignore=ignore), config


def _print_report(vault: Vault, config, issues, names: List[str], limit: int) -> None:
    print(f"体检：{vault.root}")
    if config.path:
        print(f"配置：{config.path}")
    print(f"共 {vault.file_count} 个文件，其中笔记 {len(vault.notes)} 篇\n")
    for name in names:
        group = [i for i in issues if i.check == name]
        mark = "[OK]" if not group else "[!!]"  # ASCII: GBK consoles can't print ✔
        print(f"{mark} {TITLES[name]}（{name}）：{len(group)}")
        shown = group if limit <= 0 else group[:limit]
        for i in shown:
            where = f"{i.path}:{i.line}" if i.line else i.path
            print(f"    {where}  {i.message}")
        if len(shown) < len(group):
            print(f"    …还有 {len(group) - len(shown)} 条，用 --limit 0 看全部")
    fixable = [i for i in issues if i.fix_kind]
    print(f"\n合计 {len(issues)} 个问题")
    missing = sum(1 for i in issues if i.check == "no-frontmatter")
    if vault.notes and missing and missing / len(vault.notes) > 0.8:
        print(f"提示：{missing}/{len(vault.notes)} 篇都没有 frontmatter，看起来这个库不用它。"
              f"可在 {CONFIG_NAME} 里关掉：{{\"checks\": {{\"no-frontmatter\": {{\"enabled\": false}}}}}}")
    if fixable:
        safe = sum(1 for i in fixable if i.fix_kind in SAFE_KINDS)
        print(f"其中 {len(fixable)} 处断链有修复建议（{safe} 处可直接用 vault-doctor fix 修）")


def cmd_check(args) -> int:
    vault, config = _load(args)
    names = enabled_checks(config, args.only)
    issues = run_checks(vault, args.only, config)
    if args.json:
        out = {
            "vault": vault.root,
            "config": config.path,
            "files": vault.file_count,
            "notes": len(vault.notes),
            "counts": {n: sum(1 for i in issues if i.check == n) for n in names},
            "issues": [i.to_dict() for i in issues],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        _print_report(vault, config, issues, names, args.limit)
    return 1 if issues else 0


def cmd_fix(args) -> int:
    vault, config = _load(args)
    link_rule, bom_rule = config.for_check("broken-link"), config.for_check("bom")
    accept = args.accept or list(SAFE_KINDS)
    # A path a check excludes must not be touched by that check's fix either.
    fixes, skipped = plan_fixes(
        vault, vault.notes, accept,
        fix_bom=lambda p: not args.no_bom and bom_rule.enabled and not bom_rule.excludes(p),
        fix_links=lambda p: not args.no_links and link_rule.enabled and not link_rule.excludes(p))

    mode = "写入" if args.write else "预览（加 --write 才会真的改）"
    print(f"修复：{vault.root}  ·  {mode}")
    print(f"接受的断链修复：{'、'.join(KIND_TITLES[k] for k in accept)}\n")
    for fix in fixes:
        print(fix.path)
        for change in fix.changes:
            print(f"    {change}")
    for s in skipped:
        print(f"跳过：{s}")
    total = sum(len(f.changes) for f in fixes)
    print(f"\n{len(fixes)} 个文件，{total} 处修改")

    if args.write:
        bom_by_path = {n.path: n.has_bom for n in vault.notes}
        for fix in fixes:
            write_fix(vault, fix, bom_by_path[fix.path])
        print("已写入。")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    # Piped output on Windows uses the ANSI code page; never crash on odd file names.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if not os.path.isdir(args.vault):
        print(f"错误：目录不存在：{args.vault}", file=sys.stderr)
        return 2
    try:
        return cmd_check(args) if args.command == "check" else cmd_fix(args)
    except ConfigError as e:
        print(f"配置错误：{e}", file=sys.stderr)
        return 2
