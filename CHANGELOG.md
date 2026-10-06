# Changelog

## 0.2.0

- 新增 `fix` 命令：自动修复有唯一答案的断链和 BOM。默认只预览，加 `--write` 才写盘。
  - 断链修复三类：`alias`（目标是某篇笔记的别名）、`moved`（文件搬了位置）、`prefix`（笔记改过名，旧名是新名的前缀）。默认只应用 `alias` 和 `moved`，`prefix` 要显式 `--accept prefix`。
  - 保留 `#标题`、`^块`、显示文字、表格里的 `\|`、`![[嵌入]]`，保留原文件的换行符（CRLF/LF）。
  - 混用 CRLF/LF 或不是合法 UTF-8 的文件会跳过并说明原因；写入是原子的。
- 新增配置文件 `.vault-doctor.json`：`ignore` 跳过目录；`checks.<名称>.enabled` 关闭某项检查；`checks.<名称>.exclude` 按路径通配符豁免（`check` 和 `fix` 都遵守）。`--config` 可指定路径。
- `check` 的断链结果会附上修复建议；`--json` 里带 `suggestion` 和 `fix_kind`。
- 解析 frontmatter 的 `alias` / `aliases`（行内列表和多行列表都支持）。
- 隐藏目录（`.` 开头）总是跳过，与 Obsidian 一致。

## 0.1.0

- 首个版本：`check` 命令，四项检查（断链、缺 frontmatter、空笔记、BOM）。
