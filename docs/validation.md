# 验证记录

验证日期：2026-10-13。环境：Linux、Python 3.10.12、Bubblewrap 0.6.1。

## 自动验证

```sh
EXAMPLEPROOF_SANDBOX_TESTS=1 python3 -m unittest discover -s tests -v
```

v1 冻结时归档结果：148 项通过，其中 134 项核心测试、14 项真实沙箱集成测试，无跳过。[完整运行日志](evidence/real-projects-20261013/unittest.txt)。当时未开启 `EXAMPLEPROOF_SANDBOX_TESTS` 时为 134 项通过、14 项跳过。覆盖 Markdown 提取、路径约束、断言保留、失败状态、HTML 转义、模型协议模拟，以及网络隔离、源码只读、子进程限制、运行超时、输出限制、提前退出与错误输出检查。兼容性开发验证的 118 项测试日志也保留于原证据目录。新版实现的验证与实验单独记录，见本文 v2 段落及 [新版证据](evidence/semantic-v2-20261013/README.md)。

新增 23 项冻结对照回归：三组真实请求结构隔离、参考答案与检查不泄露、对应种子及最大预算、首成功停止、放弃耗预算、生成内容错误与服务协议错误区分、源码窗口真实行号/长度、输入/基线/协议误改拒绝，以及运行终态、模型变化和成本缺失时不虚报成功率。测试使用模拟响应，不计入实时推理样本。

另有 7 项独立审计回归：源码/检查/历史泄漏、种子或 token 预算篡改、人工改写候选、补丁上下文不符、未完成证据不放行。审计器直接读取原始记录并独立汇总，未调用模型或执行示例。

本轮新增：未知配置字段必须在执行前拒绝；UTF-8 BOM 文档提取、行号、SHA-256及补丁字节往返；评测清单完整覆盖；基线不符时不调用模型；环境/模型不可用的未知指标；运行与报告异常保留失败阶段；真实沙箱中的输入快照、临时补丁应用、完整文档复查及快照重放。

新增回归覆盖：多轮失败反馈与重试上限、拒绝/重复/候选耗尽/服务错误的停止条件、模型断言不能新增独立证据、token 数据不完整时不虚报总量、外部检查反馈脱敏、禁代理及重定向、解包赋值和危险引用完整性、低层退出的完成凭据校验、报告硬链接保护，以及 Markdown 缩进、CRLF、无文件末尾换行和候选内嵌围栏。补丁测试对一次性副本执行 `git apply --check` 和实际应用，再重新提取或隔离执行。

推理取证回归另覆盖可调 socket 超时、原始请求/响应保存、超时与解析失败的报告、HTTP 服务错误正文、无效 Unicode、复杂 AST 拒绝、原始错误不重复发送，以及解析失败后仍统计服务返回的 token 消耗。GitHub workflow 配置 Python 3.10–3.14 核心矩阵和强制无跳过的 Bubblewrap 集成测试；[首轮 CI](https://github.com/Luqhhh/opensource/actions/runs/38348590555) 的 6 个任务全部成功（commit 30fed20，当时 104 项测试），后续提交以 Actions 实际状态为准。

端到端测试还将生成的统一补丁应用到临时副本，重新执行检查，确认三个修复在完整文档中生效，原始演示文件未修改。

## 演示结果

```sh
python3 -m exampleproof repair examples/tutorial \
  --proposals examples/tutorial/proposals.json --output artifacts/demo
```

| 状态 | 数量 | 含义 |
|---|---:|---|
| verified_repair | 3 | 已记录的候选补丁通过原有断言与外部行为检查 |
| checked | 1 | 原始示例通过检查 |
| skipped | 1 | 配置明确说明缺少数据集 |
| runnable_unverified | 1 | 可以运行，但未提供行为检查 |

命令退出码为 0，生成 HTML、JSON 与统一补丁。`git apply --check --directory=examples/tutorial artifacts/demo/verified.patch` 通过。每次运行可在本地重新生成报告；耗时和时间戳随环境变化。

## 多轮回放验证

```sh
python3 -m exampleproof repair examples/tutorial \
  --proposals examples/tutorial/proposals.multiround.json \
  --max-attempts 3 --output artifacts/multiround
git apply --check --directory=examples/tutorial artifacts/multiround/verified.patch
```

退出码为 0，最终状态与上述六例相同。三个失败示例共返回 4 个候选：`README.md#2` 先 `repair_failed`，再 `verified_repair`；另两个示例各一轮通过。JSON schema 2 和独立 HTML 均保留逐轮记录；最终补丁仅包含通过检查的候选，应用检查通过。回放不产生模型调用，token 计数为 null。

`python3 -m compileall -q exampleproof tests` 及针对自有实现、测试、脚本和主文档的 `git diff --check` 通过。上游原样源码/doctest、统一补丁的空白上下文行，以及 CSV 的 CRLF 按原字节保存；整批证据的空白提示不作清洗，以免改变来源摘要或补丁内容。演示及测试没有修改原始文档和源码。

## 真实 Ollama 推理

Ollama 0.40.3 + `qwen2.5-coder:7b`（Q4_K_M），在 RTX 4070 Laptop GPU 上对相同开发样例完成三次实时运行。原提示词的单轮和三轮上限两次运行均修复 2/3 个失败示例，另 1 例为模型主动放弃，退出码 1。调整通用提示词并删除重复堆栈后，修复 3/3 个失败示例，退出码 0；输入 token 从 2440 降至 1977（约 19%）。原始失败记录完整保留。

优化后三处补丁应用到临时副本后，重新隔离执行得到 4 个 checked、1 个 skipped、1 个 runnable_unverified，退出码 0。案例、完整请求/响应、模型摘要、耗时与对比局限见 [真实推理证据](evidence/ollama-20261013/README.md)。这是基于已见开发样例的提示词迭代，不是未见项目成功率评测；本次成功候选均为第一轮，不能据此证明多轮反馈提升。

## 新增兼容性开发基准

8例中6个历史兼容性重现、2个健康对照；仍全部为CPython标准库自编案例，非从真实项目抽样。记录候选回放修复6/6，应用补丁后8例checked，推理请求0；4个刻意错误候选均被外部行为检查拒绝，不能换算为通用误修复率。

使用同一Qwen模型，旧提示词单轮与三轮上限均修复2/6，健康对照2/2保持通过。完善通用提示词后，在三轮上限内修复4/6，实际请求11次，输入/输出token为9292/1456；补丁应用后6例checked、2例failed，退出1。计时案例在第3轮成功，Base64换行和HTML可调用绑定仍未通过既定检查，失败与重复候选均保留。[完整结果及局限](evidence/compatibility-20261013/README.md)。没有改写检查或模型候选；这是已见开发案例的提示词迭代，调用预算亦增加，不能归因于单一因素或解释为未见修复率。

## 真实项目与公平对照

已完成 TinyDB、more-itertools、MarkupSafe 三项目官方历史文档采集，固定两版 commit、原文位置、许可与 SHA、原始错误、参考补丁和复查。旧版本同一检查 8/8 通过；目标版本原始为 5 failed、3 checked，参考回放应用复查 8/8 checked，0 次模型请求。补丁针对规范化 Markdown 副本，未提交上游。[逐例证据](../benchmarks/real_projects/README.md)

随后冻结全部输入、提示词、模型摘要、三个配对种子和每例最多 3 次请求，完成 27 个实验单元、92 次真实请求。每组 5 个失败案例 × 3 个种子，首次/预算内通过数分别为：直接模型 4/15、7/15；加源码 8/15、9/15；加源码及反馈 8/15、8/15。每组健康复查 9/9。全部通过候选均完成补丁应用复查，失败和结构拒绝未删除。来源、逐例轮次、成本与完整限制见 [实测报告](evidence/real-projects-20261013/README.md)。

本次源码组通过数多 2 次，但输入 token 约为直接组的 5.20 倍；没有观察到反馈的额外收益，三组至少一次通过的独立案例覆盖均为 3/5。MarkupSafe 的通过候选保持固定 Markup 输入的行为，未证明通用 soft_unicode 迁移；TinyDB 一个反馈案例仅因额外 stdout 不符而失败。没有事后改检查或补模型答案。[独立原始证据审计](evidence/real-projects-20261013/independent-audit.json) 为 passed，27/27 单元完整，15/15 对源码/反馈首轮 payload 一致，0 不一致项。

上述 v1 目录保持冻结，不因 v2 增强检查而追溯改分。当前实现与归档实现不同，复查旧证据应明确使用归档模式；不能为通过当前实现摘要检查而改写旧 `protocol.json`：

```sh
python3 scripts/verify_real_project_study.py \
  docs/evidence/real-projects-20261013 --archived-only
```

## 语义验证与方法对照 v2

新增可选实时模型路径 `--repair-policy semantic-v2`，适用于 `repair` 与 `benchmark`；默认 `legacy` 保持不变。新路径使用 6000 字符的任务/调用对象源码检索、新版通用提示词和后续失败分类，继续使用同一个沙箱、结构守卫及 evaluator 检查。`--proposals` 回放与模型策略开关不能混用。新版类别由宿主观察的执行阶段、完成凭据和 stdout 比较产生，不读取外部检查断言来生成建议；检查错误和预期输出仍不发送给模型。

[新版开发集](../benchmarks/semantic_v2/development/README.md) 明确标记 `development_v2`，共 6 个迁移失败、3 个健康对照。它基于已看过的 v1 案例扩展，不能算新留出样本。MarkupSafe 新增可复用 `convert` 任务，独立检查普通/空/Unicode/HTML 字符串、str 子类、Markup identity、数字、布尔、None 及自定义对象；TinyDB 检查不同表范围、多记录、空表、缺失表、重复调用、ID 重置、缓存及持久化；`collate` 检查 key/reverse、重复项、一次性迭代器和惰性。所有可复用绑定与输出契约均在模型可见的任务上下文中说明；新任务属于评测者编写的语义适配，不假称官方原文摘录。

工程验证结果记录在 [validation-02](../benchmarks/semantic_v2/development/evidence/validation-02/validation.json)：

| 验证 | 结果 |
| --- | ---: |
| 原始代码配旧版本，同一套新版检查 | 9/9 通过 |
| 原始代码配目标版本 | 6 个预期失败、3 个健康 |
| 人工参考候选经补丁应用复查 | 6/6 修复、3/3 健康保留 |
| 错误候选通过格式守卫后，被外部语义检查拒绝 | 9/9 |
| 被拒绝但显示 stdout 完全匹配的候选 | 8/9 |
| 上述工程回放中的模型请求 | 0 |

负例包括 TinyDB 错删范围和只执行一次的空 callable、`collate` 急切排序和错误去重、MarkupSafe 用 `escape` 替代转换、将 None 当空串、重建 Markup 导致 identity 丢失。9 例均由外部 `AssertionError` / returncode 22 拒绝，未将语法或格式不支持计为语义覆盖。原 MarkupSafe 显示回归仍保留其有限适用范围，不宣称新增检查可以追溯证明原候选具备通用转换正确性。

新增 `tests/test_semantic_study.py` 的 11 项协议回归已通过，包括 2 项实际 Bubblewrap 生命周期测试：五组冻结、10 次模拟 HTTP 请求、stdout 分类、候选复验、补丁应用、完整文档复查和成本统计；另外验证首轮实际 payload 配对相同、legacy 不受 v2 提示词污染、隐藏检查/输出不泄露、对应种子与最大预算、健康案例零调用、方法锁篡改拒绝，以及开发/已见/已调用模型的案例不能冒充留出集。测试只使用自写临时 fixture 和模拟模型响应，不读取实际留出答案，不计为真实模型推理。单项复现命令：

```sh
EXAMPLEPROOF_SANDBOX_TESTS=1 python3 -m unittest discover -s tests -p test_semantic_study.py -v
```

新版实验比较五组：`legacy_source`、`legacy_feedback`、`source_v2`、`generic_feedback_v2`、`feedback_v2`。实验内 legacy 两组使用原提示词与 12000 字符摘录，v2 三组使用新版提示词与 6000 字符摘录；组内首轮配对请求一致，分类仅进入后续反馈。各组固定相同模型、最多 3 次调用和每次 1024 生成 token 上限，实际输入/输出 token 与耗时分别计量。开发阶段使用种子 17；新留出项目使用 17、29、43，先锁方法再接触案例详情、冻结输入后才开始推理。开发与留出分别统计，不混合分母，也不将重复种子当作独立缺陷。

协议、方法锁、源码窗口、逐轮失败、token 成本及最终实时结果见 [semantic-v2 实验记录](evidence/semantic-v2-20261013/README.md)。上述工程验证不预先说明模型收益；反馈是否有帮助、缩短上下文是否节省总成本，应以各组真实结果为准。方法锁和协议 SHA 是本地可复查记录，并非外部时间戳，也不能保证公共案例不在模型预训练数据中。

## 安装包验证

semantic-v2 最终方法的 [195 项测试](evidence/semantic-v2-20261013/unittest.txt) 全部通过，包含真实 Bubblewrap 执行、固定索引离线重建、检索范围、反馈脱敏、冻结协议及独立审计。当前方法的两轮开发实验各 52 次请求，新项目留出实验 180 次请求，均保存完整终态并通过独立审计。留出五组均为 0/12，不能把工程测试通过当作模型修复效果通过；[完整结果及失败](evidence/semantic-v2-20261013/README.md) 分开记录。

最终 [安装包记录](evidence/semantic-v2-20261013/package.json) 验证 wheel、sdist、仓库外安装的 16 个 Python 模块与方法锁 SHA 一致，CLI 与模块入口、`pip check` 和 TinyDB 参考回放均通过，无新增运行依赖。发布复审发现后另补全 Apache-2.0、CPython 许可及 public-domain/no-warranty 归属文本，作为 package-data 在 wheel/sdist/安装后逐字节核对；未改变冻结 Python 方法。早期包的工程成功记录仍保留为 `package-pre-license.json`，不作为最终分发包。最终 wheel SHA-256 为 `ddda55267bb21ab72074f6750234b9b54b74247ee1d18dd3c3e7950f85adb0bc`。

上一轮临时 venv 使用已声明的隔离构建依赖 setuptools 84.0.0 生成含11个Python文件的wheel，摘要为 `7927a4188f97248f1bd4de19c231dadd06a9838b73b70912c3bccefcc5916e0d`。

兼容性基准阶段在干净venv重新构建 `aic_exampleproof-0.1.0-py3-none-any.whl`，12个Python模块（含benchmark）与当时工作区逐字节一致，元数据名称/版本正确且无运行依赖。仓库外安装后，模块来源确认为venv的site-packages，console入口、版本、benchmark帮助及真实回放闭环通过。该wheel SHA-256：`695a730ee8e93ce8b16dfbcc8d5f1e7e48205dba51e060a3675fb3b4213e9459`。摘要仅标识对应构建，不保证不同构建时间字节一致。

先前直接调用本机系统pip22.0.2曾错误生成空的 `UNKNOWN-0.0.0` 包且退出0。调查确认系统setuptools59.6仍出现在pip隔离构建路径并优先被导入，忽略pyproject项目元数据。使用干净venv解决，系统Python包没有升级；错误wheel已排除。README补充安装步骤，CI新增严格wheel校验及仓库外安装，现有沙箱CI补充兼容性回放。以上为推送前的本地验证记录，远端结果以具体 [Actions 运行](https://github.com/Luqhhh/opensource/actions/workflows/tests.yml)为准。

v1 冻结对照新增 `study.py` 后，再使用两个全新 venv 构建和安装。wheel 与 sdist 内 13 个模块 SHA 均与当时冻结实现一致，无运行依赖；仓库外 CLI、模块入口、`pip check` 和已安装包的 TinyDB 回放闭环通过（2 个修复+1 个健康，补丁复查 3 checked，0 次模型调用）。[构建记录](evidence/real-projects-20261013/package.json) 与 [命令清单](evidence/real-projects-20261013/commands.json) 已归档；wheel SHA-256 为 `e3b2aa9642e007ce42c2d2cef7f08f943ce638cd7fcf1704a558d89f5c4f7638`。CI 增加三个真实项目的来源校验及参考补丁复查，但没有把模型下载或在线调用作为 CI 依赖；本段旧版本构建与本地测试结果不代替 v2 产物验证或远端 CI 状态。

## 尚未验证

- 尚未验证更多模型、CPU 推理和长上下文项目。
- 真实项目案例仍是人工/AI 辅助选择的历史迁移，规模小；没有当前上游缺陷的随机样本或总体成功率估计。
- 没有独立人工盲审、维护者采纳、通用误修复率、用户节省时间或费用/能耗测量；自动安装依赖、编译扩展环境尚未支持。
- 通过有限行为检查不证明一般语义等价；补丁仍需人工审核。
