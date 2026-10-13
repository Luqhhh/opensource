# CPython 历史兼容性小型基准

本目录提供 6 个依据 CPython 官方移除记录自编的历史兼容性重现，以及 2 个正常对照。每个案例是一份普通 Markdown 中的独立 Python 代码块，只依赖标准库。它们扩展验证流程覆盖面，**不是从第三方开源仓库采集的真实缺陷，也不是模型未见测试集**。

案例、外部检查与候选均在本次开发中由 AI 辅助构造。`proposals.json` 保存预先编写的正确候选，用于实际执行的候选回放；本目录的首次验证没有调用模型。竞赛材料仍需团队审核来源、实现和结果，并如实披露 AI 工具参与。

## 案例与检查目标

| 文档 | 历史变化 | 移除版本 | 独立行为检查 |
|---|---|---|---|
| [base64_mime.md](cases/base64_mime.md) | `encodestring` / `decodestring` | 3.9 | MIME 换行、末尾换行、二进制往返及空输入 |
| [elapsed_clock.md](cases/elapsed_clock.md) | `time.clock` | 3.8 | 按秒计算、包含实际睡眠时间 |
| [array_bytes.md](cases/array_bytes.md) | `tostring` / `fromstring` | 3.9 | 二进制输出、原值保留、向数组追加 |
| [html_unescape.md](cases/html_unescape.md) | `HTMLParser.unescape` | 3.9 | 多种字符引用、未知引用、单次解码 |
| [integer_gcd.md](cases/integer_gcd.md) | `fractions.gcd` | 3.9 | 非负整数约分、互质数、含零输入 |
| [json_encoding.md](cases/json_encoding.md) | `json.loads(encoding=...)` | 3.9 | Unicode 文本、保留 Decimal 精度与有效参数 |
| [healthy_query.md](cases/healthy_query.md) | 正常对照 | 不适用 | 重复键、空值、百分号转义与往返 |
| [healthy_escape.md](cases/healthy_escape.md) | 正常对照 | 不适用 | 引号转义、Unicode、单次还原 |

`exampleproof.json` 为全部 8 例设置 `checks` 与 `expected_stdout`。这些检查在代码块之外维护；候选不能修改配置，也不能靠新增自己的断言获得独立验证。检查对编码器、解码器等可调用对象增加了其他输入，并检查中间值，减少只打印预期文本造成的假通过。正常对照不在 `proposals.json` 中，执行通过后不进入候选生成环节。

## 复现

在仓库根目录执行；需要 Linux、允许创建隔离命名空间的 Bubblewrap 和 `/usr/bin/python3`。示例始终经项目的失败即关闭隔离执行器运行，无宿主执行回退。目标版本为 CPython 3.10+，首次实际验证为 `/usr/bin/python3` 3.10.12。

```bash
python3 -m exampleproof check benchmarks/compatibility --output artifacts/compatibility-check
python3 -m exampleproof repair benchmarks/compatibility --proposals benchmarks/compatibility/proposals.json --output artifacts/compatibility-replay
```

第一条预期退出码为 `1`，结果为 `failed: 6, checked: 2`；第二条预期退出码为 `0`，结果为 `verified_repair: 6, checked: 2`。退出码 `2` 或 `blocked` 表示隔离环境等条件未满足，不能算作预期缺陷复现。修复命令仅导出 `verified.patch`，原始案例保留失效 API。

2026-10-13 的首次实测报告保存在 [evidence/check.json](evidence/check.json)、[evidence/replay.json](evidence/replay.json)、[evidence/verified.patch](evidence/verified.patch) 与 [evidence/validation.json](evidence/validation.json)。应用补丁只在临时副本中进行，复查得到 8 个 `checked`；两个健康对照均没有候选尝试，实时推理请求数为 0。报告带有选中文档及配置的 SHA-256，可用于对应输入核验。

另外，用 [negative_proposals.json](negative_proposals.json) 中 4 个刻意构造的错误候选检查行为约束是否起效：

| 错误改法 | 被破坏的行为 | 实际结果 |
|---|---|---|
| 改成 `base64.b64encode` | 缺少 MIME 换行与末尾换行 | 外部检查失败，退出码 22 |
| 改成 `time.process_time` | 不计入睡眠时间 | 外部检查失败，退出码 22 |
| JSON 同时删除 `parse_float=Decimal` | 小数变成二进制浮点数 | 外部检查失败，退出码 22 |
| 数组直接从字节重建 | 原有元素丢失，没有追加 | 外部检查失败，退出码 22 |

可通过下面的命令复现；预期命令退出码为 `1`，4 个有候选的案例为 `repair_failed`，另外 2 个失效案例没有提供候选，2 个正常对照保持 `checked`。原始记录见 [evidence/negative.json](evidence/negative.json)。这只是 4 个定向负例，不能报告为模型误修复率或通用防错率。

```bash
python3 -m exampleproof repair benchmarks/compatibility --proposals benchmarks/compatibility/negative_proposals.json --output artifacts/compatibility-negative
```

## 元数据约定

`metadata.json` 的 `schema_version` 为 `1`，`suite_id` 为 `cpython-compatibility-v1`。顶层记录构造方式、目标解释器和局限；`cases` 中每例包括：

- `id`：配置和报告共用的 `cases/<文档>.md#1` 标识。
- `expected_before`：6 例为 `failed`，2 个对照为 `checked`，采用流水线结果状态名。
- `category`：`historical_compatibility` 或 `healthy_control`。
- `expected_repair`：正确候选回放的预期状态，分别为 `verified_repair` 或 `checked`。
- `deprecated_since`、`removed_in`、`removed_api`：历史版本事实；对照为 `null`。
- `sources`、`behavior`：官方来源链接与独立检查约束的行为。

元数据描述基准，不是需要发送给模型的上下文。可调用接口的名字只为让外部检查检验多个输入；并不要求候选采用唯一文本形式。

## 来源与局限

历史事实来源于 [CPython 3.9 移除记录](https://docs.python.org/3.9/whatsnew/3.9.html#removed) 和 [CPython 3.8 移除记录](https://docs.python.org/3.10/whatsnew/3.8.html#api-and-feature-removals)，元数据为每例附有相关标准库接口文档。2026-10-13 核查以上来源，只记录链接与原创摘要，没有复制官方或第三方示例代码。官方文档适用 PSF License Version 2；本目录的自编文件随仓库 MIT 许可发布，权属及 AI 辅助内容的最终审核由团队承担。没有引入新的运行依赖、外部数据集或模型资源。

这 8 例不能代表大型项目、第三方依赖升级、异步或多文件问题。候选与检查在开发过程中共同构造且公开，回放通过率只能证明这些候选通过这些检查，不能衡量实时模型、盲测或泛化能力。未在历史解释器上重新运行，旧版本信息来自官方记录；实际观测限于当前解释器的失败和修复结果。`time.clock` 的旧平台语义并不统一，本例明确选择包含等待的经过时间；GCD 案例限定非负整数，避免扩大语义等价结论。

计时检查只设较宽松的下限以容忍系统调度，没有性能比较含义。外部检查与案例仍共享同一 Python 进程，不构成针对恶意篡改检查代码的完整安全边界。真实项目缺陷与独立评测集仍需后续按许可证、精确提交、复现环境和独立验证逐例采集。
