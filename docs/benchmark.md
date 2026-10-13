# 可复现评测协议

`benchmark` 在相同输入快照上运行原始检查与修复，再仅对临时副本执行 `git apply --check` 和 `git apply`，重新提取并隔离执行修复后的完整文档。用户项目保持只读，候选仍需人工审核。此复查能发现补丁应用、Markdown 提取或上下文变化问题；它不是与原检查独立的语义验证器。

## 输入与复现

项目按普通 `check` / `repair` 配置，额外提供 `metadata.json`：

```json
{
  "schema_version": 1,
  "suite_id": "my-suite-v1",
  "cases": [
    {"id": "README.md#1", "expected_before": "failed"},
    {"id": "README.md#2", "expected_before": "checked"}
  ]
}
```

清单必须恰好覆盖所有示例且不可重复，至少包含一个预期失败。每例必须配置非空 `checks` 或 `expected_stdout`，不可跳过。建议同时提供健康对照，以及每例来源、分类、行为和适用版本。清单和外部检查不放入模型请求。案例文档自身提供的功能说明是任务上下文，不是保密检查。

运行示例见 [README](../README.md)。要求已有 Linux Bubblewrap、Python 和 Git；工具不会安装依赖或下载模型。`--max-attempts` 和 `--model-timeout` 与 `repair` 相同。

输出必须是尚不存在的目录，防止覆盖失败记录。`inputs/` 保存选定文档、源码、规范化配置及原始元数据；回放模式另保存标准化候选列表 `proposals.json`，可将该快照作为项目再次评测。实时模式的请求、响应在 `repair/report.json` 中，模型权重和运行服务需另行准备。报告保存实现文件摘要；对正式实验还应保留 Git commit、操作系统、执行解释器、Bubblewrap、模型版本及模型摘要。

## 指标口径

| 字段 | 定义 |
|---|---|
| `baseline_valid` | 每例原始状态均符合清单中的 `failed` / `checked`；不符时不调用模型 |
| `detected_failures` / `expected_failures` | 原始检查失败的预期错误案例数 / 清单预期错误数 |
| `healthy_false_alarms` | 原始检查实际为 `failed` 的健康对照数；环境不可用或结果缺失不计为误报 |
| `evaluation_complete` | 基线符合预期，修复和补丁复查均有完整可评估结果，且没有基础设施错误 |
| `infrastructure_errors` | 记录不可用、缺失或模型服务错误的阶段/案例/状态；阶段异常另含类型及错误信息 |
| `verified_repairs` | 修复候选通过原始有限检查的错误案例数 |
| `patch_confirmed_repairs` | 候选通过检查且补丁应用后的文档再次成为 `checked` 的错误案例数 |
| `repair_rate` | `evaluation_complete` 时，补丁复查通过数 / 预期错误数；其余情况为 `null` |
| `healthy_preserved` | 修复阶段没有生成候选，且补丁应用后仍为 `checked` 的健康对照数 |
| `all_passed` | 基线有效、所有错误案例补丁复查通过、全部健康对照保持通过 |
| `repair.inference_requests` | 实际留下请求记录的推理调用数；候选回放为 0 |
| `duration_seconds` | 包括快照、原始检查、修复、补丁应用、文档复查和各阶段报告写入的耗时（不含前置配置校验和最后摘要文件自身写入） |

没有执行或相关组证据不可用的修复、补丁复查和健康保留计数，以及未知 token 数，使用 `null`，不补成零。模型服务错误也使修复率不可用。`verified_repairs` 不等于独立人工评审的“正确修复”，健康对照数量也不足以推断真实项目误报率。当前没有通用误修复率估计。

评测专属退出码：`0` 表示全部通过；`1` 表示可评估修复未全部通过或 Git 拒绝补丁；`2` 表示配置/基线不符、执行环境/模型服务不可用、阶段异常或报告 I/O 错误。普通 `repair` 的模型调用失败仍为 `1`。创建输出目录后发生阶段异常，会尽力保存带 `stage`、`error`、耗时的摘要；Git 拒绝补丁另留 `patch_error`。最终摘要本身无法写入时向调用方报 I/O 错误，不承诺文件存在。

## 当前案例边界

[compatibility](../benchmarks/compatibility/README.md) 是根据上游发布说明重新编写的历史兼容性案例，全部来自 CPython 标准库，按已知变更选择，不是从多项目随机抽样。它们扩展了开发验证覆盖面，不应表述为未见评测集，也不能用于推断真实仓库修复成功率。包含 MIME 换行、数组追加、墙钟计时、实体解码、整数最大公约数和 JSON 数值类型等行为约束。

公平对比应冻结案例、配置、模型、提示词、推理参数和硬件，保留全部尝试；多轮与单轮需报告调用预算差异。失败后修订案例或提示词的实验应另起版本，不覆盖原证据。

## 真实项目的冻结对照

[真实项目案例集](../benchmarks/real_projects/README.md) 来自 TinyDB、more-itertools、MarkupSafe 的官方旧版文档或 docstring，固定原版和目标版 commit。三项目共 5 个迁移失败、3 个健康对照；同一行为检查在原版全部通过，在目标版得到预期失败。代码仅作已记录的 doctest / RST 到 Markdown 机械转换。输出补丁适用于这些规范化 Markdown，不是已向上游提交的补丁。

`scripts/run_real_project_study.py` 提供专门的三组对照，协议和 [原始证据](evidence/real-projects-20261013/README.md) 与普通 `repair` 的交互式停止规则分开记录：

| 条件 | 原示例、上下文及原始错误 | 目标版本源码摘录 | 前轮候选与反馈 |
|---|---|---|---|
| direct | 有 | 无 | 无 |
| source | 有 | 有 | 无 |
| source_feedback | 有 | 有 | 有 |

三组都使用同一外部检查选择首个通过候选，每例最多 3 次请求；前两组未通过后的请求是独立采样，第三组才接收历史。模型放弃、结构拒绝、重复候选或生成的 JSON 无效均消耗预算，允许继续；首次通过或基础设施故障立即停止。健康对照不调用模型。首次通过率与最多 3 次调用内通过率分别报告，因此不会把多次尝试结果当作单次性能。

模型固定为 Qwen2.5-Coder 7B Q4_K_M 的具体摘要，temperature=0.2、num_ctx=8192、num_predict=1024、超时 180 秒。重复种子为 17、29、43，同一案例各组第 k 次请求使用种子 `seed + k - 1`。每个种子轮换组顺序。相同的最大调用数与生成 token 上限不意味着相同实际输入 token 或耗时；源码与历史的成本全部统计。该小样本重复测量只有 5 个独立失败案例，不是 15 个独立缺陷。

源码摘录由定义签名和原代码/初始错误的词项重合度自动选择，最多 12000 字符（标签与源码合计），不是完整库。生成后的逐例摘录在推理前保存并冻结。参考补丁、原始档案和检查虽随输入快照公开保存，但 provider 仅接收实际请求中列出的示例、上下文、错误、源码窗口及允许的历史，不向模型发送参考答案或隐藏检查。

```sh
# 新目录；只读取模型元数据、执行基线，不产生模型推理
python3 scripts/run_real_project_study.py freeze \
  benchmarks/real_projects/tinydb \
  benchmarks/real_projects/more_itertools \
  benchmarks/real_projects/markupsafe \
  --output artifacts/real-project-study

# 固定全部输入后进行真实推理；已有 runs/ 时拒绝覆盖或悄悄重试
python3 scripts/run_real_project_study.py run artifacts/real-project-study

# 重新统计已保存的证据，不调用模型
python3 scripts/run_real_project_study.py summarize artifacts/real-project-study
```

`protocol.json` 保存提示词、模型/软件版本、实现摘要、输入/基线/源码窗口摘要、预算和顺序；`protocol.sha256` 用于检测本地误改，并非第三方时间戳或外部预注册。运行前后核对模型元数据及冻结输入。`runs/<seed>/<arm>/<project>/inference.json` 保存每次真实请求、响应、执行结果及停止位置。`selected.json` 仅保存模型实际选中的首个通过候选；`patch_validation/` 明确为该候选的回放应用复查，不增加真实推理样本。

协议执行完且证据完整时退出 0，即使存在模型未修好的案例；配置、模型服务、隔离执行或记录中断返回 2 并隐藏整体成功率。此退出码与单项目 `benchmark` 的“未全部修好返回 1”不同。模型生成无效内容属于已发生的失败尝试；服务传输或响应协议异常属于不完整实验。缺失 token 计数保留未知，不填零。

这些案例在 v1 冻结前没有用于调整本应用提示词，但公开上游内容可能存在于基础模型预训练中。v1 的案例与结果已经被开发者看到；本轮基于它们扩展的案例均属于开发集。它们按已知迁移问题选择，不能代表当前上游缺陷分布，也没有人工盲审或维护者采纳证明。

当前实现已增加 v2 模块，与旧实验实现摘要不同。审计旧冻结记录必须使用 `--archived-only`，核对归档实现、冻结输入及原始请求，而不是要求当前代码仍与旧实现相同：

```sh
python3 scripts/verify_real_project_study.py \
  docs/evidence/real-projects-20261013 --archived-only
```

该选项不会运行模型或改写旧实验。它只免除当前工作区实现与归档实现相同的要求，保留对归档实现、协议、输入、请求、预算与结果的一致性审计。若要重新推理，须创建新实验目录，不能覆写旧证据。

## 语义评测与五组对照 v2

`repair` 和 `benchmark` 的实时模型路径提供可选参数 `--repair-policy semantic-v2`。默认仍为 `legacy`；记录候选回放不能选择模型策略。普通命令中的 legacy 使用原提示词和明确选定的源码，semantic-v2 使用通用任务/调用对象检索、6000 字符的源码摘录、新版提示词及后续分类反馈。策略开关不改变沙箱、候选守卫和外部检查，也不改变普通 `repair` 的停止条件。

专门的实验入口为 `scripts/run_semantic_study.py`。以下五组用于区分整体方法修改、历史反馈和固定失败类别的作用，均通过 `StudyProvider` 发送实际请求：

| 条件 | 提示词 | 源码摘录上限 | 前轮候选与反馈 |
| --- | --- | ---: | --- |
| `legacy_source` | 原 `SYSTEM` | 原检索，12000 字符 | 无，失败后独立采样 |
| `legacy_feedback` | 原 `SYSTEM` | 原检索，12000 字符 | 候选历史及原通用反馈 |
| `source_v2` | 新版 `SYSTEM_V2` | 新检索，6000 字符 | 无，失败后独立采样 |
| `generic_feedback_v2` | 新版 `SYSTEM_V2` | 新检索，6000 字符 | 候选历史及原通用反馈 |
| `feedback_v2` | 新版 `SYSTEM_V2` | 新检索，6000 字符 | 候选历史、固定失败类别与通用指导 |

字符预算包括源码位置标签及原文，不能当作 token 数。legacy 两组首轮 payload 相同，v2 三组首轮 payload 相同；分类只作用于后续候选反馈，不增加首轮信息。`source_v2` 与 `generic_feedback_v2` 的区别是是否提供历史；后者与 `feedback_v2` 的区别是是否增加分类。`legacy_source` 与 `source_v2` 同时改变检索、上下文上限和提示词，不能把差异单独归因于检索算法。`legacy_feedback` 与 `feedback_v2` 衡量完整方法升级的差异。

新检索读取原示例、模型可见的行为说明、已脱敏的原始错误、目标源码和固定的标准库 API 索引。它结合词项相关性与调用对象/类范围，返回有精确行号且不重复的源码窗口，过滤未被原调用或错误明确引用的私有 API。参考候选和外部检查不参与检索。分类反馈由执行器记录的阶段和完成凭据决定：例如 `example_exception`、`behavior_check`、`stdout_mismatch`、`timeout`，不是从隐藏检查的异常文本中提取答案。行为检查失败、输出不符等情形仍隐藏检查内容、预期值和实际隐藏输出；共享解释器的限制仍然存在。

方法修订 2 在原始 `ImportError: cannot import name ...` 与示例的 `from` 导入、选定项目包一致时，固定分配 4000 字符项目源码和 2000 字符标准库索引；未触发时全部 6000 字符供项目源码使用。索引来自 CPython 3.10.12 官方发行归档的 153 个公开平面 Python 模块、999 个顶层公开函数，按统一规则静态提取签名/docstring，不导入或执行这些模块，不手工指定迁移答案。原始语料、摘要、许可证和生成器均保存；完整索引及许可随实现参与冻结和包分发。它不包含 C 内置函数、类方法或子包，不代表全部标准库 API。新增语料是整体方法的一部分，不能把其收益写成反馈增益。

五组沿用每个失败案例最多 3 次调用、temperature=0.2、num_ctx=8192、num_predict=1024、请求超时 180 秒，以及第 k 次请求使用 `seed + k - 1` 的规则。第一次通过或基础设施故障即停止，其他失败尝试完整保留；健康对照不调用模型。开发集使用种子 17，留出集使用 17、29、43。固定的是最大调用数和最大生成 token，实际输入 token、输出 token、耗时及失败均须分别报告；源码更短并不自动意味着成功率提高或总成本降低。

### 开发集与留出集

[development_v2](../benchmarks/semantic_v2/development/README.md) 来自已看过的三个 v1 项目，包含 6 个失败和 3 个健康对照。MarkupSafe 新增明确要求保留 `convert` 的通用转换任务；TinyDB 增加可复用表操作、多记录、重复调用和持久化检查；`collate` 增加 key/reverse、重复项、一次性迭代器和惰性检查。新增绑定任务和行为约束是评测者编写的适配，不是新发现的官方文档机械摘录。原 v1 展示回归及原得分保留。

开发集工程验证中，旧运行时同检查 9/9 通过；目标运行时出现预期的 6 个失败、3 个健康。参考候选的补丁应用复查修复 6/6，健康 3/3 保留。9 个刻意错误候选均通过格式守卫，执行完示例后被外部语义检查拒绝，8 个仍有完全相同的显示输出；这些回放共 0 次模型请求，不构成模型效果结果。

新留出项目应由独立采集流程准备。实现负责人先完成开发和 `lock-method`，再查看留出案例细节；随后冻结输入、检查和模型信息，在第一次推理前保存协议。`metadata.split` 必须匹配 `development_v2` / `holdout_v2`；留出项目必须明确声明未用于方法优化，并拒绝已看过案例结果或已执行实时模型的冲突标记。分组检查在读取模型元数据前执行。此处“留出”只针对本应用方法开发，不保证未进入模型预训练，也不是双盲评测。

开发集可按下列命令新建实验：

```sh
python3 scripts/run_semantic_study.py freeze \
  benchmarks/semantic_v2/development/tinydb \
  benchmarks/semantic_v2/development/more_itertools \
  benchmarks/semantic_v2/development/markupsafe \
  --split development --output artifacts/semantic-v2-development
python3 scripts/run_semantic_study.py run artifacts/semantic-v2-development
python3 scripts/run_semantic_study.py summarize artifacts/semantic-v2-development
```

开发结束、尚未查看新留出案例细节时锁定方法。下面的 `path/to/heldout-project` 应换成已按协议准备的留出项目，多个项目可依次列出：

```sh
python3 scripts/run_semantic_study.py lock-method artifacts/semantic-v2-method.json
python3 scripts/run_semantic_study.py freeze path/to/heldout-project \
  --split holdout --method-lock artifacts/semantic-v2-method.json \
  --output artifacts/semantic-v2-holdout
python3 scripts/run_semantic_study.py run artifacts/semantic-v2-holdout
python3 scripts/run_semantic_study.py summarize artifacts/semantic-v2-holdout
```

方法锁记录实现摘要、完整五组设计和时间，另存 `.sha256`。锁后改变实现或设计、改写锁文件、将开发集冒充留出集均会拒绝冻结。它是可复查的本地记录，不是第三方时间戳；“何时查看案例”仍需如实披露，不能由文件哈希独立证明。开发与留出实验分别保存协议和结果，不能混合分母或把重复种子当作新的独立案例。

本轮实时结果、原始失败、token 成本与独立审计集中记录于 [semantic-v2 实验报告](evidence/semantic-v2-20261013/README.md)。本文只说明方法和已完成的工程验证，不预先宣称分类反馈优于通用反馈。
