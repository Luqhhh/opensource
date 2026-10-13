# Werkzeug 历史文档迁移留出

上游为 [pallets/werkzeug](https://github.com/pallets/werkzeug)，许可 BSD-3-Clause。原文为 2.2.3 的公开函数 docstring，Sphinx 的 `docs/wsgi.rst` 与 `docs/urls.rst` 发布这些 API。目标为 3.0.6，两版本源码保留原字节。运行时依赖 MarkupSafe 2.1.5 的原生 Python 回退实现，两个版本使用同一固定依赖；这里没有测试 MarkupSafe 的迁移。

| 案例 | 官方原文 | 目标失败 | 外部语义检查 |
|---|---|---|---|
| `pop_path_info` | `src/werkzeug/wsgi.py` 243–275 docstring | 已移除的导入 | 复用函数；PATH_INFO 到 SCRIPT_NAME 的副作用、空／缺失路径、根斜线、重复斜线、无关字段、WSGI Latin-1 字符串中的 UTF-8、`charset=None` 字节 |
| `peek_path_info` | 同文件 310–332 docstring | 已移除的导入 | 复用函数；不修改环境、重复调用、空／缺失路径、重复斜线、UTF-8 解码、`charset=None` 字节 |
| `iri_to_uri` | `src/werkzeug/urls.py` 759–795 docstring | 健康对照 | Unicode 主机名与路径、空 URL、空格、已有百分号转义 |

实际精确行范围以 [provenance.json](provenance.json) 为准。docstring 的每个 `>>>` 语句按原顺序提取；有 REPL 期望输出的表达式机械改为 `print(repr(...))`，原期望文本作为 stdout oracle；补充显式公开导入，所有操作均由 `verify_provenance.py` 重做核对。

上下文显式要求保留公开 callable 名称。旧版 `peek_path_info` 文档概述说空路径返回 `None`，但固定原始实现实际上返回 `''`，本套件以可复现的固定实现为行为基准并在任务上下文披露该边界，未静默把它改成另一种行为。

检查在旧 2.2.3 全部通过。参考候选以直线代码中的 lambda 保留有限契约；不建议把这个迁移展示当成生产代码风格指南。一个负例使用标准库 `shift_path_info`，虽通过原文正常路径输出，却改变重复斜线语义而被拒绝；另一个只返回固定 `'a'`，被空输入等检查拒绝。

入口：[provenance.json](provenance.json)、[metadata.json](metadata.json)、[exampleproof.json](exampleproof.json)、[参考候选](proposals.json)、[负例](negative_proposals.json)、[最终运行证据](../validation-final/werkzeug/validation.json)。这些补丁作用于适配后的 Markdown，不等同于可直接应用到上游 RST/Python 文件的 PR。
