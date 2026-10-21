# 例证 · ExampleProof

开源项目教程质量分析与改进工具，帮助读者理解教程、完成首次运行并有效使用项目。保留 Python 文档示例的隔离验证与修复能力。面向 AIC 2026「AI+开源」主题赛的 **AI开发工具与开源协作** 方向。

## 面向学习者的项目入口

运行 `python3 -m exampleproof learn`，在浏览器打开 `http://127.0.0.1:8765/`。导入公开 GitHub 仓库或项目 ZIP，填写学习目标和基础水平，即可查看项目评估、入门路线、原文与源码入口；支持保存进度和导出指南。配置 `DEEPSEEK_API_KEY` 后，可在查看发送片段后用 AI 细化路线；没有模型配置时仍可使用本地原文整理。也支持显式配置本地 Ollama。

这是可交互的本机单用户应用，前端不包含评测审批和评分表单。项目文件不会被执行，AI 路线与自己记录的进度不等于已验证的学习效果。安装、数据位置与部署边界见 [学习入口说明](docs/learning-app.md)。

已完成[首条真实教程任务改进闭环](docs/real-tutorial-task.md)：复用 TinyDB 固定提交的既有真实诊断，由助手编写明确 RST 候选，验证原始首次运行失败、修改后持久化任务通过、补丁应用复查通过，并拒绝仅使用内存数据库的负例。新增 `task-check` 承接明确候选与冻结任务合同；这是助手参与的单例工程结果，独立人工评审和上游采纳仍待完成，不改写旧对照的零文字补丁记录。

仓库：<https://github.com/Luqhhh/opensource>

## 本轮交付优化

新增 [task-improve](docs/task-improvement.md) 将已有建议与冻结任务合同连接，生成候选后进行隔离验证和补丁应用复查。默认云端发送需要精确请求清单确认；也可显式回放候选。已有 TinyDB 回放通过，未新增实时模型成功结果。

[小规模任务评测](docs/task-evaluation/README.md) 已准备两个新项目、四个任务的草稿协议与评阅模板。独立人工评阅前不运行正式模型对照，准确性、召回率与读者任务结果保持未知。lexical 默认不变；iterative 增加累计用量停止阈值、POSIX 硬时限和逐轮必要证据覆盖统计，见 [限制说明](docs/iterative-retrieval.md)。

发布校验改为从实际源码生成清单，逐字节核对 wheel/sdist/安装目录及许可证，并在仓库外检查新增命令。历史实验采用持久归档与逐文件摘要，见 [交付验证与证据索引](docs/delivery-validation.md)。

## 项目级教程分析

`analyze` 自动发现项目文档、源码及依赖声明，无需先编写 `exampleproof.json`。默认从 GitHub 地址或 `OWNER/REPO` 获取公开仓库，也支持本地目录。默认使用 DeepSeek `deepseek-flash`＋规则检索（`lexical`，AST＋关键词），需预先在环境中配置 `DEEPSEEK_API_KEY`。不需要本地模型或 Bubblewrap，不会运行项目代码或安装依赖。云端会接收选中的项目内容；无密钥或服务失败时明确报错，不自动切换服务或静态模式。以下命令的输出目录必须尚不存在，且位于被分析项目之外。

```sh
# 默认 Flash＋规则检索；首次仅生成清单，不发送模型请求
python3 -m exampleproof analyze OWNER/REPO --output /tmp/tutorial-flash

# 检查 /tmp/tutorial-flash-cloud-review.json 的文件与脱敏原文后确认
python3 -m exampleproof analyze OWNER/REPO --output /tmp/tutorial-flash \
  --approve-cloud REVIEW_SHA256

# 本地项目
python3 -m exampleproof analyze /path/to/project --output /tmp/tutorial-local

# 纯静态检查：无需密钥，不调用模型
python3 -m exampleproof analyze OWNER/REPO --static --output /tmp/tutorial-static

# 可选 AI 上下文选择，额外发起一次选择请求
python3 -m exampleproof analyze OWNER/REPO \
  --context-strategy ai --output /tmp/tutorial-ai

# 保留本地 Ollama，模型必须已安装
python3 -m exampleproof analyze /path/to/project --provider ollama \
  --model YOUR_LOCAL_MODEL --output /tmp/tutorial-ollama
```

输出 `analysis.html`、`analysis.json`、`suggestions.md`，以及仅供审阅的 `suggestions.patch` 和 `edits.json`。静态模式当前检查 Markdown 本地链接目标；模型模式进一步分析安装前提、步骤顺序、概念解释、跨文件一致性和错误处理。文字补丁限于精确匹配的 Markdown 正文段落，保护代码块、行内代码和链接，不自动应用；没有合格修改时补丁为空。AI 建议均标记为未经验证；证据引用只确认指向原文，不证明判断正确。报告不表示学习效率已提升，也不自动生成已验证的教程补丁。

DeepSeek 教程分析（含 `compare`）首次只生成 `OUTPUT-cloud-review.json` 并退出 2。清单列出候选文件、摘要及脱敏后的完整可发送片段；人工检查后传 `--approve-cloud` 和清单中的 `sha256`。可用 `--cloud-review PATH` 指定清单位置，用 `--redact-values PATH` 读取额外敏感值的 JSON 字符串数组。自动脱敏覆盖常见凭据赋值、Bearer、URL 凭据及私钥块，仍需逐项人工检查。确认绑定快照、模型、范围、提示词及预算；内容变化后需用新清单重新审阅，原清单保持只读。首次预览仍需有效的模型配置和密钥；获取 GitHub 输入会联网，模型请求在确认前不会发送。此机制适用于教程 `analyze/compare`；原有 `repair/benchmark` 流程保持独立。

教程范围默认增加 `Dockerfile`、`Containerfile`、`Makefile`、`GNUmakefile`。`--include-tests` 纳入普通测试目录，`--include-path '.github/**'` 可显式纳入隐藏路径，`--exclude-path 'docs/archive/**'` 优先排除；Git 元数据、`.env`、已知敏感文件名和 evaluator 配置仍被排除。本地读取与 GitHub 快照使用相同范围；这些参数不改变原有修复器的输入策略。

`lexical` 和 `ai` 保留最多 40 个初始候选及一次选择。新增 `--context-strategy iterative`：AI 在分析中描述证据缺口，程序按文件路径、Python 符号或关键词检索完整的合格静态索引，将新增原文送回下一轮分析，可以超出初始候选集合。默认最多补充 3 轮、最多 4 次模型请求；`--max-retrieval-rounds 1..5` 控制上限。每轮仍受 `--context-chars` 限制，不执行仓库代码或模型命令。详情见[按证据缺口继续检索](docs/iterative-retrieval.md)。

```sh
# 本地模型；将任务词项用于初始排序，并允许按证据缺口补充检索
python3 -m exampleproof analyze /path/to/project --provider ollama --model YOUR_LOCAL_MODEL \
  --context-strategy iterative --task '配置项目并调用需要该配置的 API' \
  --include-tests --max-retrieval-rounds 3 --output /tmp/tutorial-iterative
```

云端使用相同策略时，首次清单覆盖整个合格索引中的可检索片段；审阅后再用 `--approve-cloud SHA256` 确认。确认绑定任务的脱敏视图和检索轮数，后续轮次也只发送清单允许的脱敏内容。输出增加 `retrieval.json`，记录每轮缺口、命中、上下文和停止原因。`--task` 目前只用于 `iterative`，无需任务时仍可基于通用上下文发现缺口。

`--evidence-requirements PATH` 按独立标注测量必要证据覆盖，输出 `evidence-coverage.json`；无标注时保持 `not_measured`。迭代模式额外记录检索到的片段及扩展后的可用证据。按任务、测试/文档/源码等路径角色统计遗漏，原因不明时保留未知。标注中的 `task` 是评测说明，不会代替显式 `--task` 或发送标注答案。工程测试验证流程，不证明建议正确或真实任务召回率提高。

默认的 `--context-strategy lexical` 使用 AST 与关键词候选直接选择原文；`ai` 先让模型选择候选 ID，再分析原文，最多两次模型请求。两种策略分别配置模型供应商；字符预算不等于 token 总预算。云端模式会发送选中的项目内容，名称过滤无法保证清除全部秘密。DeepSeek 默认模型为 `deepseek-flash`，可用 `--model` 替换；密钥只从环境读取，不写入请求证据或日志。详细范围、成本口径和公平对照要求见[下一阶段基线](docs/next-stage.md)。

可以用同一个项目快照直接对照两种策略，调用前保存协议及输入摘要，最多发起三次模型请求：

```sh
python3 -m exampleproof compare OWNER/REPO --output /tmp/tutorial-comparison
python3 -m exampleproof compare-audit /tmp/tutorial-comparison
```

`comparison.html` 比较实际上下文、耗时与 token，`review-template.json` 留待独立评审。快照和实现源码随协议归档，审计命令不调用模型。固定最终字符上限并不意味着总 token 成本相同；建议数量不代表准确率。已完成的小规模 Flash 实测及失败记录见[Flash 对照记录](docs/flash-comparison.md)。

已完成[模型与上下文选择的 2×2 对照](docs/factorial-experiments.md)：三个公开项目、每组合两次，共 36 次正式模型请求；Flash 与本机 Qwen 7B 的原始结果、助手原文核对及局限分别保存，不以生成数量替代准确率。

上述默认配置适用于项目级 `analyze`，`compare` 仍只对照 lexical 与 ai，历史结果不包含新迭代模式。`--static` 不可与模型、服务地址或 AI/iterative 策略混用。

下面保留的 v0.1 描述、实验数字和复现命令属于历史 Python 示例验证链路，不代表新教程分析功能的效果评测。`repair` / `benchmark` 保持原有 Ollama 默认及候选回放语义；需要云端修复时显式传入 `--provider deepseek`。

**当前状态：v0.1 原型。** 提取 Markdown 中的 Python 示例，在 Linux Bubblewrap 隔离环境中执行，接收修复候选并复验，生成 JSON、HTML 报告及统一补丁。支持本地 Ollama；工具不自动下载模型。随附候选回放演示**不代表实时模型推理结果或真实项目修复成功率**。已有 [Qwen2.5-Coder 7B 开发验证](docs/evidence/ollama-20261013/README.md)、[三个真实项目的历史文档迁移证据](benchmarks/real_projects/README.md) 与 [冻结三组对照](docs/evidence/real-projects-20261013/README.md)。本轮新增 [多输入语义开发集 v2](benchmarks/semantic_v2/development/README.md) 和可选的 `semantic-v2` 修复策略；新版五组实验与旧结果分开保存，见 [新版实验记录](docs/evidence/semantic-v2-20261013/README.md)。

## 工作流程

2026-10-15 已增加环境诊断、候选格式错误重试、进度提示、源码分析缓存和报告操作建议。详见 [基础优化与验证说明](docs/basic-improvements.md)。这属于工程改进；旧模型实验保持冻结，复核旧记录须使用 `--archived-only`，不能把旧成绩当作当前代码的新实验结果。

文档与选定源码 → 示例提取 → 隔离执行 → 源码/错误信息辅助修复 → 断言完整性检查 → 行为复验 → 报告与补丁。

- 原文档和源码保持只读，补丁需由使用者审核后应用。
- 保留原始断言。移除断言、将断言移入条件分支、吞异常、提前退出等候选会被拒绝或无法通过检查。
- **运行成功不等于行为正确。** 未配置输出/行为检查且无原始顶层断言的示例只标记为可运行，其候选不进入 `verified.patch`。
- `verified_repair` 只表示通过有限检查，并非一般语义等价证明。仍需人工审核修复是否保留原任务。

## 本地运行

帮助、版本查看、`scan` 和环境诊断支持 Windows。执行示例需要 Linux（Windows 可使用 WSL Ubuntu）、Python 3.10+、`/usr/bin/python3` 和可创建用户/网络命名空间的 Bubblewrap。执行器没有退回宿主机执行的模式。v0.1 仅支持单进程、单线程示例，运行环境只含 Python 标准库及配置中明确列出的 `.py` 源码；可以显式选择第三方纯 Python 源码，暂不支持自动安装依赖或加载编译扩展。

先检查环境；Linux 上会用可信的 `pass` 代码做一次真实隔离探测，不调用模型或执行项目示例：

```sh
python3 -m exampleproof doctor
# 供自动化读取；环境未就绪返回 2
python3 -m exampleproof doctor --json
```

Windows 可将上述 `python3` 换为 `python`；实际执行命令请在已准备好的 WSL/Linux 环境内运行。

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

`check`、`repair`、`benchmark` 默认在标准错误中显示当前示例、修复轮次和结果；`benchmark` 另显示基线、修复、补丁复查阶段。添加 `--quiet` 可关闭进度提示，结果及错误仍保留。`scan` 的标准输出仍是 JSON。HTML 报告优先展示需处理项，自动展开错误，提供下一步建议与 token 汇总；JSON 结果顺序仍按原文档顺序。

支持基于失败反馈的多轮修复，每个失败示例默认尝试 1 轮，可用 `--max-attempts 1..5` 调整。以下演示故意先回放一个错误候选，再回放修正候选：

```sh
python3 -m exampleproof repair examples/tutorial \
  --proposals examples/tutorial/proposals.multiround.json \
  --max-attempts 3 --output artifacts/multiround
```

每轮都重新检查原始断言并在独立沙箱中复验。拒绝、执行失败或模型候选格式错误会在原定 `--max-attempts` 预算内进入下一轮；成功、缺少行为检查、候选重复、候选耗尽、服务错误或执行环境不可用时停止。完成的模型响应中，候选 JSON 无法解析或缺少 `code` / `rationale` 字符串时记录为 `candidate_format_error`，保留原响应、用量与拒绝原因，不执行该候选。HTTP 错误、超时、无效服务响应和用量字段错误仍为 `provider_error`，不会自动重试。JSON 和 HTML 保留逐轮候选、拒绝理由、执行结果及停止原因，补丁只包含最终通过检查的候选。候选文件仍是记录回放，不能计为实时模型推理。

已有本地 Ollama 模型时，可改为实时修复（将模型名替换为本机实际安装的名称）：

```sh
python3 -m exampleproof repair examples/tutorial \
  --model YOUR_LOCAL_MODEL --max-attempts 3 --model-timeout 180 --output artifacts/live
```

默认 `--repair-policy legacy` 保持原有提示词、所选源码及通用执行反馈。也可在 `repair` 或 `benchmark` 的实时模型路径显式选择新版策略：

```sh
python3 -m exampleproof repair examples/tutorial \
  --model YOUR_LOCAL_MODEL --repair-policy semantic-v2 \
  --max-attempts 3 --model-timeout 180 --output artifacts/live-semantic-v2
```

`semantic-v2` 按任务语义与调用对象检索最多 6000 字符的原文摘录（包括位置标签）。确认项目缺失导入时，预算分为项目源码 4000 字符与固定 CPython 3.10.12 标准库索引 2000 字符；其他情况全部用于项目源码。策略使用新版通用提示词，并向后续尝试提供固定的失败类别，例如示例异常、行为检查失败或 stdout 不匹配。它沿用相同的沙箱、候选守卫、外部检查和补丁复查；不改写用户检查。策略开关只适用于 `--model`，与 `--proposals` 同用会拒绝执行。索引有明确的版本和范围限制，细节见 [评测协议](docs/benchmark.md#语义评测与五组对照-v2)。

每个新版模型提供者缓存当前选定源码的 AST 分析及固定标准库索引的词项统计，跨示例、跨轮复用；源码内容改变时重新分析，仅保留最近一份源码快照。排序仍逐任务计算，缓存不会改变摘录内容、字符预算或评测检查。

模型收到原始示例、周边文档、所选源码或检索摘录，以及此前候选的拒绝或执行反馈。外部检查和预期输出不放入请求；配置检查失败、超时或异常退出的反馈会隐藏 evaluator 细节，仅在确认 setup/示例异常时保留详细错误。分类反馈来自宿主记录的执行阶段，不解析外部检查的异常文本来生成提示。Ollama 仅支持回环地址，禁用环境代理和 HTTP 重定向。协议测试和真实模型调用结果见 [验证记录](docs/validation.md)。

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

需要已运行的本地 Ollama 和对应模型；已有实验目录不可覆盖。上述命令创建新实验，不能用新版实现覆盖或重新解释已冻结的 v1 记录。三种子重复的每组 15 次案例运行仍只对应 5 个失败案例，不能据此估计真实项目总体成功率。[协议、结果与局限](docs/evidence/real-projects-20261013/README.md)

旧 v1 实现已经归档；当前代码增加了 v2 模块，审计旧冻结记录须使用归档实现模式：

```sh
python3 scripts/verify_real_project_study.py \
  docs/evidence/real-projects-20261013 --archived-only
```

新版开发集包含 6 个迁移失败和 3 个健康对照，扩展 MarkupSafe 通用转换、TinyDB 表操作以及 `collate` 的多输入、边界和惰性行为检查。旧运行时同检查 9/9 通过，参考补丁修复 6/6 且健康 3/3 保留；9 个有意错误候选均通过格式检查后被外部语义检查拒绝，其中 8 个显示输出仍正确。这些是工程回放结果，模型请求为 0；已见案例明确标记 `development_v2`，不能充作新的留出评测。

新版公平对照比较 `legacy_source`、`legacy_feedback`、`source_v2`、`generic_feedback_v2`、`feedback_v2` 五组。实验内 legacy 摘录上限 12000 字符，v2 为 6000 字符；两种上限均为标签与原文合计，不是 token 上限。五组固定相同模型、每例最多 3 次调用和每次生成上限，分别报告首次/预算内结果及实际 token 成本。开发集与新留出项目分开冻结、分开统计；留出实验先锁定方法，再接触案例内容并冻结输入。详细复现命令与各对比能回答的问题见 [新版评测协议](docs/benchmark.md#语义评测与五组对照-v2)，结果见 [新版实验记录](docs/evidence/semantic-v2-20261013/README.md)。不能仅凭增加反馈或缩短上下文就宣称效果提高。

本轮两次开发实验各 52 次、新留出实验 180 次请求已全部完成。新方法修复了已见 TinyDB 默认表案例，但 `collate` 的可复用绑定和通用字符串转换仍未通过；新留出五组均为 **0/12**，健康对照均为 **6/6**。新无反馈组的输入 token 比旧无反馈组少 **40.32%**，没有证明修复或反馈收益。多输入语义检查能拒绝本轮准备的 13 个错误候选，这属于检查器验证，不是模型成功率。

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


工作台、任务模板、证据分类和 RST 渲染范围见 [教程任务工作台](docs/tutorial-workbench.md)。首批四任务的真实基线与局限见 [任务评测记录](docs/task-evaluation/README.md)。
