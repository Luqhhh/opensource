# 例证 · ExampleProof

开源文档示例验证与修复助手。面向 AIC 2026「AI+开源」主题赛的 **AI开发工具与开源协作** 方向。

仓库：<https://github.com/Luqhhh/opensource>

**当前状态：v0.1 原型。** 提取 Markdown 中的 Python 示例，在 Linux Bubblewrap 隔离环境中执行，接收修复候选并复验，生成 JSON、HTML 报告及统一补丁。支持本地 Ollama；工具不自动下载模型。随附候选回放演示**不代表实时模型推理结果或真实项目修复成功率**。已有 [Qwen2.5-Coder 7B 开发验证](docs/evidence/ollama-20261013/README.md)，另新增 [三个真实项目的历史文档迁移证据](benchmarks/real_projects/README.md) 与 [冻结三组对照](docs/evidence/real-projects-20261013/README.md)，保留原始请求、失败及补丁复查结果。

## 工作流程

文档与选定源码 → 示例提取 → 隔离执行 → 源码/错误信息辅助修复 → 断言完整性检查 → 行为复验 → 报告与补丁。

- 原文档和源码保持只读，补丁需由使用者审核后应用。
- 保留原始断言。移除断言、将断言移入条件分支、吞异常、提前退出等候选会被拒绝或无法通过检查。
- **运行成功不等于行为正确。** 未配置输出/行为检查且无原始顶层断言的示例只标记为可运行，其候选不进入 `verified.patch`。
- `verified_repair` 只表示通过有限检查，并非一般语义等价证明。仍需人工审核修复是否保留原任务。

## 本地运行

需要 Linux、Python 3.10+、`/usr/bin/python3` 和可创建用户/网络命名空间的 Bubblewrap。执行器没有退回宿主机执行的模式。v0.1 仅支持单进程、单线程示例，运行环境只含 Python 标准库及配置中明确列出的 `.py` 源码；可以显式选择第三方纯 Python 源码，暂不支持自动安装依赖或加载编译扩展。

在仓库目录运行，无需安装 Python 依赖：

```sh
# 只提取，不执行
python3 -m exampleproof scan examples/tutorial

# 检查原文档；演示内有已知错误，预期退出码 1
python3 -m exampleproof check examples/tutorial --output artifacts/check

# 使用记录的候选补丁复验；不调用模型
python3 -m exampleproof repair examples/tutorial \
  --proposals examples/tutorial/proposals.json --output artifacts/demo
```

输出为 `report.html`、`report.json` 和 `verified.patch`。HTML 为可直接打开的独立文件，不依赖网络或 JavaScript。

支持基于失败反馈的多轮修复，每个失败示例默认尝试 1 轮，可用 `--max-attempts 1..5` 调整。以下演示故意先回放一个错误候选，再回放修正候选：

```sh
python3 -m exampleproof repair examples/tutorial \
  --proposals examples/tutorial/proposals.multiround.json \
  --max-attempts 3 --output artifacts/multiround
```

每轮都重新检查原始断言并在独立沙箱中复验。拒绝或执行失败会进入下一轮；成功、缺少行为检查、候选重复、候选耗尽、服务错误或执行环境不可用时停止。JSON 和 HTML 保留逐轮候选、拒绝理由、执行结果及停止原因，补丁只包含最终通过检查的候选。候选文件仍是记录回放，不能计为实时模型推理。

已有本地 Ollama 模型时，可改为实时修复（将模型名替换为本机实际安装的名称）：

```sh
python3 -m exampleproof repair examples/tutorial \
  --model YOUR_LOCAL_MODEL --max-attempts 3 --model-timeout 180 --output artifacts/live
```

模型收到原始示例、周边文档、明确选择的源文件，以及此前候选的拒绝或执行反馈。外部检查和预期输出不放入请求；配置检查失败、超时或异常退出的反馈会隐藏 evaluator 细节，仅在确认 setup/示例异常时保留详细错误。Ollama 仅支持回环地址，禁用环境代理和 HTTP 重定向。协议测试和真实模型调用结果见 [验证记录](docs/validation.md)。

候选 JSON 按示例 ID 映射到 `{"code": "...", "rationale": "..."}`；多轮回放时将该值改成按轮次排列的对象数组。文件上限为 2 MB。JSON 报告当前为 `schema_version: 2`，保留结果级最终候选字段并新增 `attempts`、`stop_reason` 和项目级 `repair` 统计。token 总量仅在所有尝试均提供相应计数时给出，否则为 `null`；服务已返回用量但候选解析失败时也计入统计。

`--model-timeout` 设置 HTTP 连接/读取空闲超时，默认 60 秒，可为冷启动或 CPU 推理调高；它不是整轮墙钟时间上限。每次 Ollama 请求保存实际 payload、响应、UTC 时间、耗时及超时配置，见 `inference_evidence`。失败时也保留可获得的响应或最多 256 KB 的错误正文；HTTP 错误展示模型服务提供的原因。`repair.inference_duration_seconds` 包括有记录的失败请求，`proposal_duration_seconds` 仅统计成功解析的候选。报告含用户选择的源码与文档，分享前应检查内容。

## 配置一个项目

在目标项目根目录创建 `exampleproof.json`。Python 示例按文档内出现顺序编号，从 `#1` 开始；可先运行 `scan` 查看编号。

```json
{
  "documents": ["README.md"],
  "source_files": ["sdk/__init__.py"],
  "timeout_seconds": 5,
  "examples": {
    "README.md#1": {
      "setup": "from sdk import double",
      "checks": "assert result == 6",
      "expected_stdout": "6\n"
    },
    "README.md#2": {"skip": "需要未提供的数据集"}
  }
}
```

`setup` 与 `checks` 由使用者明确配置。示例之间不共享状态。无法独立执行的片段应配置初始化代码或说明跳过原因。普通围栏支持 0–3 个前导空格，提取时移除围栏缩进，输出补丁时恢复；保留文档的 LF/CRLF 和文件末尾无换行状态。候选字符串包含关闭围栏时，自动加长外围围栏。列表嵌套、无围栏的缩进代码块、Notebook、跨代码块自动上下文推导暂未支持。

输入路径必须为规范的相对路径，例如 `docs/guide.md`，不接受 `./docs/guide.md`、重复斜杠、隐藏路径或符号链接。报告以临时文件写入后替换，避免通过既有硬链接改写输入。

配置严格校验字段名；例如误写 `check` 或 `expected_output` 会直接报错，避免漏跑行为检查。支持带 UTF-8 BOM 的 Markdown，生成补丁时保留原始 BOM、换行和文件末尾状态。

退出码：`0` 为没有失败或未验证修复候选（仍应阅读 skipped / runnable_unverified 计数）；`1` 为执行、检查、模型或候选失败；`2` 为配置/隔离环境错误、无示例或全部跳过。

## 测试

```sh
python3 -m unittest discover -s tests -v
# 完整执行测试，需要系统允许 Bubblewrap 创建命名空间
EXAMPLEPROOF_SANDBOX_TESTS=1 python3 -m unittest discover -s tests -v
```

首批演示包括一个 Python 真实兼容性变更的重现、两个自制 SDK 变更案例、一个正常案例、一个上下文缺失片段及一个无行为检查的案例。它们用于验证工程流程，不能计为 6 个真实开源缺陷。[案例来源](docs/cases.md)

## 可复现评测

新增 8 个标准库案例：6 个历史兼容性重现、2 个健康对照。每例具有外部行为检查和 CPython 官方来源；它们不代表 8 个真实项目缺陷。

```sh
# 回放：检查基线、复验候选、在临时副本应用补丁、重新检查完整文档
python3 -m exampleproof benchmark benchmarks/compatibility \
  --proposals benchmarks/compatibility/proposals.json --output artifacts/benchmark-replay

# 实时推理：使用已安装模型，保留完整请求、响应和失败结果
python3 -m exampleproof benchmark benchmarks/compatibility \
  --model qwen2.5-coder:7b --max-attempts 3 --model-timeout 180 \
  --output artifacts/benchmark-live
```

每次评测须使用新的输出目录。`benchmark.json` 明确记录候选回放或实时推理模式、基线是否符合预期、修复数、补丁应用后通过数、健康对照、token 与耗时；`inputs/` 保存本次输入快照，`baseline/`、`repair/`、`patched/` 分别保存三阶段报告。基线不符时返回 `2` 并停止调用模型；环境、模型服务或记录异常也返回 `2`，指标保留未知状态。可评估修复或补丁复查未全部通过返回 `1`，全部通过返回 `0`。[评测协议与指标](docs/benchmark.md)

新增 TinyDB、more-itertools、MarkupSafe 官方历史文档案例，固定旧版/目标版源码、原文位置与许可，合计 5 个迁移失败、3 个健康对照。旧版本同一检查 8/8 通过，目标版本参考补丁应用复查 8/8 通过；参考候选属于工程回放，模型效果另见真实对照。

三组对照比较直接模型、加入目标源码摘录、再加入执行反馈。推理前冻结案例、提示词、模型摘要、种子和每例 3 次调用上限；三组均报告首次及预算内通过数、失败、token 与耗时。复现入口：

```sh
python3 scripts/run_real_project_study.py freeze \
  benchmarks/real_projects/tinydb benchmarks/real_projects/more_itertools \
  benchmarks/real_projects/markupsafe --output artifacts/real-project-study
python3 scripts/run_real_project_study.py run artifacts/real-project-study
```

需要已运行的本地 Ollama 和对应模型；已有实验目录不可覆盖。三种子重复的每组 15 次案例运行仍只对应 5 个失败案例，不能据此估计真实项目总体成功率。[协议、结果与局限](docs/evidence/real-projects-20261013/README.md)

## 参赛资料

- [项目范围、评分对应与开发安排](docs/competition.md)
- [资源与 AI 使用记录](docs/resources.md)
- [架构与执行边界](docs/architecture.md)
- [验证记录与当前局限](docs/validation.md)
- [参赛材料草稿与提交缺项](docs/submission/README.md)
- [开发、案例贡献与维护约定](CONTRIBUTING.md)

## 构建与安装

源码目录可直接运行；需要安装包时使用干净的虚拟环境构建，再从仓库外验证入口：

```sh
python3 -m venv .venv-build
.venv-build/bin/python -m pip wheel --no-deps --wheel-dir dist .
.venv-build/bin/python -m pip install --no-deps dist/aic_exampleproof-0.1.0-py3-none-any.whl
.venv-build/bin/exampleproof benchmark --help
```

已在本机发现系统 pip 22.0.2 的构建隔离仍导入旧 setuptools，可能返回成功却生成 `UNKNOWN-0.0.0` 空包。正确产物名应为 `aic_exampleproof-0.1.0-py3-none-any.whl`；CI另检查元数据、源码内容、入口和仓库外安装，不能只凭构建退出码判断成功。[安装验证](docs/validation.md)

许可证：MIT。报告与参赛材料需如实披露使用的第三方组件、模型及 AI 辅助开发情况。
