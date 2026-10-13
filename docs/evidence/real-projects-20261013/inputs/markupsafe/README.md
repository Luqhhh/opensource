# MarkupSafe：官方文档版本迁移证据

取自 MarkupSafe **1.1.1** 的官方 API 文档（`docs/escaping.rst` 的 autodoc 函数文档），在固定 **2.1.5** 源码上验证。`soft_unicode` 在 2.1.0 被移除，官方要求改用 `soft_str`。这里明确记录旧示例升级新版本的兼容问题，不声称发现现行文档缺陷。

- 文档 commit：`22c946de28c2f5916f8c88a983a3e48e1cdbd2fd`；实现 commit：`fbba4acd0312826cec9cfe18371c7df07962cb65`。
- `safe_string`：原始 API 调用不改，因缺少 `soft_unicode` 失败；参考候选仅替换为 `soft_str`。
- `optional_values`：`escape_silent` 健康对照，预期无需调用模型。
- 完整来源、精确行号、文件及片段 SHA-256、路径映射和转换记录见 [provenance.json](provenance.json)。
- 许可证为 BSD-3-Clause，两版本原始许可证均保存在 `upstream/`，复制源码仍属于上游项目。

`original_snippets/` 保留原始 docstring（含缩进及 doctest 结果）。`cases/` 仅机械提取：去提示符，给带输出的表达式加 `print(repr(...))`，将原输出放入外部 oracle。`setup` 为 `from markupsafe import *`，提供文档中默认的模块作用域；原始与修复运行使用相同 setup。只映射源码的 `src/` 前缀，源码内容逐字节不变。无编译扩展，使用官方纯 Python fallback。

在仓库根目录复现工程候选回放：

```sh
python3 -m exampleproof benchmark benchmarks/real_projects/markupsafe \
  --proposals benchmarks/real_projects/markupsafe/proposals.json \
  --output /tmp/markupsafe-replay-new
```

`proposals.json` 是人工/AI 辅助整理的正确参考补丁，只用于工程回放，不是实时模型成绩。对照实验的模型请求不得包含该文件、外部 checks 或预期输出。案例制作期间没有调用或调整实时模型。

已记录旧版本正控制：同样的两个原始示例与检查，在固定 1.1.1 的纯 Python 源码上均通过，见 [旧版本报告](evidence/old-version-control/check/report.json)。新版本原始检查为 1 失败、1 通过；参考修复后 2 个均通过，补丁在临时副本应用并复查成功，见 [工程回放报告](evidence/verified/benchmark.json) 及 [修复补丁](evidence/verified/repair/verified.patch)。这是回放验证，不是模型效果。

运行 `python3 benchmarks/real_projects/markupsafe/verify_provenance.py` 会从保存的官方 docstring 重新机械提取并核对每个上游文件 SHA、原始片段、示例代码与预期输出；不执行上游代码。
