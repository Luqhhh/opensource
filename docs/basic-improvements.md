# 基础优化（2026-10-15）

基于提交 `2201a5d748a318f03ac4d774933431685e4e37e2` 实施本轮改进。没有新增 Python 运行依赖，没有下载或运行 AI 模型。已有模型实验、检查、来源和原始记录保持冻结，本轮验证属于工程测试与明确标记的候选回放。

## 改进内容

1. **环境诊断与 Windows 入口。** 帮助、版本与 Markdown 提取可以在 Windows 使用。`python -m exampleproof doctor` 显示 Linux、资源限制、Bubblewrap 和系统 Python 的检查结果及处理建议；Linux 前置条件齐全后，还用可信 `pass` 代码运行实际隔离探测。`doctor --json` 返回结构化信息，就绪返回 0，未就绪返回 2。项目示例仍只能通过 Bubblewrap 执行。
2. **候选格式错误重试。** 完成的模型响应中，候选 JSON 解析或结构不合格时记为 `candidate_format_error`，在原有 `--max-attempts` 预算内重试。失败原文、请求、响应、耗时和有效 token 计数继续保留。HTTP、超时、无效服务协议和用量字段错误仍直接停止。原始异常类型保持不变；检查和参考输出不进入请求。
3. **进度提示。** 命令行在标准错误中显示示例总数、当前位置、当前轮次与结果；评测额外显示基线、修复、补丁复查阶段。`--quiet` 关闭进度提示，保留结果和错误；库函数默认不输出。需要集成时可传入 `progress` 回调，事件以字典传递，不包含 evaluator 检查内容。
4. **源码分析缓存。** `SemanticOllamaProvider` 拥有独立缓存，只保留最近一份源码内容和一次标准库词项统计。源码内容变化会失效；每项任务重新计算排序，缓存结构不会被排序污染。检索仍返回原始源码切片，字符预算与检查不变。
5. **报告操作建议。** HTML 优先排列需处理项，默认展开这些项；按状态及行为失败类别提供下一步建议，汇总 token。未知用量显示“未提供”。JSON 仍保留原文档顺序，HTML 仍转义外部内容并禁用脚本和外部资源。

配置按 UTF-8 读取。仓库新增 `.gitattributes` 禁止自动换行转换，避免 Windows 检出改变冻结证据、第三方源码、索引和补丁的原始字节。

## 使用

在仓库目录中，Windows 可运行：

```powershell
python -m exampleproof --help
python -m exampleproof scan examples/tutorial
python -m exampleproof doctor
```

实际执行请在准备好的 Linux/WSL 环境中运行：

```sh
python3 -m exampleproof doctor
python3 -m exampleproof check examples/tutorial --output artifacts/check
python3 -m exampleproof repair examples/tutorial \
  --proposals examples/tutorial/proposals.multiround.json \
  --max-attempts 3 --output artifacts/repair
```

上述 `check` 故意包含三个已知失败，预期退出 1；修复命令是已记录候选的回放，不是实时模型推理。需要安静执行时在命令末尾加 `--quiet`。

## 本轮验证

- WSL Ubuntu、Python 3.12.3、Bubblewrap 0.9.0：完整 213 项测试通过，无跳过，包含实际隔离执行、完成凭据、网络/源码保护、补丁应用复查、模型协议模拟和新增回归。
- Windows Python 3.13：帮助、提取和环境诊断入口实测。Windows 的执行条件报告未就绪，不会降级到宿主机执行示例。
- 原演示检查得到 3 个失败、1 个通过、1 个跳过、1 个缺少行为检查；多轮回放修复 3 个失败，保留其余分类，未改变原文档。
- 模拟模型验证了候选格式错误后成功、预算耗尽、失败用量计入、私有检查不泄露，以及服务故障不自动重试。这些模拟不计为真实模型效果。
- 缓存回归验证了同一内容只分析一次、内容改变重新分析、任务间排序独立、标准库词项复用和缓存实例隔离；没有据此宣称端到端速度或修复率提升。

本轮修改了当前实现；历史实验请对照各自保存的实现归档复核：

```sh
python3 scripts/verify_real_project_study.py docs/evidence/real-projects-20261013 --archived-only
python3 scripts/verify_real_project_study.py docs/evidence/semantic-v2-development-20261013 --archived-only
python3 scripts/verify_real_project_study.py docs/evidence/semantic-v2-development-02-20261013 --archived-only
python3 scripts/verify_real_project_study.py docs/evidence/semantic-v2-holdout-20261013 --archived-only
```

新增错误状态是 JSON schema 2 的状态扩展。外部集成应将 `candidate_format_error` 视为可评估的修复失败，而将 `provider_error` 视为服务/协议失败；退出码仍分别为普通失败 1、评测基础设施不完整 2。新模型实验必须重新冻结当前方法并使用新的输出目录；旧留出案例已被观察，不能重新包装成新的留出结果。
