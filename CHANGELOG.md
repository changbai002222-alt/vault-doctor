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
- 适配不同风格的库：
  - 认 Obsidian「相对路径」链接格式：`[[../other/笔记]]`、`[[./笔记]]` 相对当前笔记解析；相对链接只报告，不自动改写。
  - 检查 Markdown 风格链接 `[文字](路径.md)` 和 `![图](路径.png)`（关闭 wikilink 的库常见）：支持相对路径、`/` 开头的库根路径、`%20` 编码、`<带空格路径>`、可省略 `.md`；网址、`mailto:`、`#锚点` 不算。这类链接只报告，不自动改写。
  - 模板语法（`{{title}}`、`<% tp.file.title %>`、`${name}`）不当成链接。
  - 如果超过 80% 的笔记都没有 frontmatter，报告末尾提示可以在配置里关掉这项检查。

## 0.1.0

- 首个版本：`check` 命令，四项检查（断链、缺 frontmatter、空笔记、BOM）。
