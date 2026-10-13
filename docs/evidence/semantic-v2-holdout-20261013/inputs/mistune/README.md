# Mistune 历史文档迁移留出

上游为 [lepture/mistune](https://github.com/lepture/mistune)，许可 BSD-3-Clause。原文来自 0.8.4 README，`docs/index.rst` 原样包含该 README。目标为 3.1.3，两版本源码均保留原字节。Python 3.10 所需 `typing_extensions` 固定为 4.12.2，使用其 PSF-2.0 许可证原文，未改变上游代码。

| 案例 | 官方原文 | 目标失败 | 外部语义检查 |
|---|---|---|---|
| `reusable_html` | README.rst 70–73 | 无 renderer 的 `Markdown()` 返回 token 列表，而旧例契约为 HTML 字符串 | 保留 `markdown` 可复用调用；空串、纯文本、强调、Unicode、软换行、原始 HTML、重复调用 |
| `renderer_options` | README.rst 87–90 | `Renderer` 已不在目标公开 API | 保留 `markdown` 可复用调用；HTML 转义、硬换行、旧版 `<br>` 输出格式、空串、Unicode、`&` |
| `simple_html` | README.rst 61–64 | 健康对照 | convenience function 的空串、普通文本、强调、Unicode、HTML 转义 |

原始代码只做 RST 缩进剥离，保留源语句、注释、顺序和原本在脚本中不打印的表达式。第二例原文使用未定义占位变量 `text`，配置 setup 明确补 `import mistune` 与固定文本；这属于公开记录的执行适配，不是原文新增的错误。每例上下文明确说明该 setup。

检查在旧 0.8.4 源码全部通过。目标 3.1.3 的语义差异和异常分别被检出，参考候选需同时恢复接口与格式。负例分别为固定 HTML 常量、关闭硬换行，均被多输入外部检查拒绝。

文件入口：[provenance.json](provenance.json)、[metadata.json](metadata.json)、[exampleproof.json](exampleproof.json)、[参考候选](proposals.json)、[负例](negative_proposals.json)、[最终运行证据](../validation-final/mistune/validation.json)。原始准备中的依赖缺失和 `<br>`／`<br />` 误判记录在 `evidence/*initial*`；它们没有进入最终冻结案例的通过统计。
