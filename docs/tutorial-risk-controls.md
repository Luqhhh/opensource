# 教程分析风险控制与验收范围

本次保留覆盖测量与既有一次选择基线，新增显式启用的受限迭代检索，不扩展文字编辑格式。没有调用真实模型，没有新的质量评测或读者实验结果；新增验证全部是合成夹具和 HTTP 接口模拟。

## 当前实现与研究目标

lexical/ai 基线先通过静态文件过滤、分块及 Python AST 索引定位源码，再使用通用安装/配置词项与文档标题排序，保留最多 40 个候选。ai 只做一次摘要选择，返回 1–12 个已展示的 ID；程序可补入教程锚点，随后按字符预算保留完整片段，进行一次语义分析。这两种基线不会要求查找候选之外的函数或在分析后继续检索。

新增 iterative 已实现“分析缺口—静态检索—补充原文—再次分析”循环，可在完整冻结索引内查询候选之外的文件、Python 符号和关键词；可选 --task 同时影响初始词项排序及每轮分析。它有固定轮数、单轮查询及证据预算，不执行任意工具或仓库代码。标注中的 task 仍只描述评测任务，不会隐式提供答案或替代 --task。报告按实际策略记录 task_conditioned 和 outside_candidate_search，详见[完整协议](iterative-retrieval.md)。

测试目录可能包含关键 API 行为证据，通用查询也可能漏掉任务相关实现。这两点是可测量的研究假设；当前没有真实项目上的独立必要证据标注和遗漏分布，不能据此认定需要全仓库 AI Agent。

| 风险 | 本次处理 | 仍需人工或后续工作 |
| --- | --- | --- |
| 基线最多 40 个候选 | 分层测量覆盖；iterative 可按缺口查找完整冻结索引 | 独立评估新增策略的召回率、正确性和成本 |
| 通用过滤遗漏教程上下文 | 教程独立范围配置，默认识别无后缀构建文件，本地与 GitHub 一致 | 使用者选择必要测试、隐藏路径和额外文件 |
| 仅修改少量 Markdown 正文 | 保留完整段落、代码、断言与链接保护；补丁只导出供审阅 | 人工确认措辞正确；MDX/RST 和结构编辑暂不扩展 |
| 云端可能收到敏感内容 | 首次预览清单、自动与自定义脱敏、按 SHA-256 显式确认 | 检查每项可发送内容，自动检测无法找齐所有秘密 |
| 审计无法证明建议正确 | 审计明确输出 `quality_passed: null`；建议与文字编辑均留人工评审模板 | 独立人工判断正确性、证据支持度和可操作性 |

## 必要证据覆盖

先用 `analyze PROJECT --static --output OUT` 获取 `analysis.json` 中的 `coverage.snapshot_id`。在被分析项目之外编写标注 JSON，再通过 `--evidence-requirements PATH` 传入；标注在任何模型请求之前校验并绑定快照。`compare` 还将标注写入冻结协议。

```json
{
  "schema_version": "tutorial-evidence-requirements-1",
  "snapshot_id": "COPY_FROM_ANALYSIS",
  "evidence_kind": "human_annotation",
  "annotator": "独立人工标注者",
  "cases": [{
    "id": "first-run-configuration",
    "task": "完成首次配置并成功调用需要该配置的 API",
    "required": [
      {"path": "README.md", "start_line": 5, "end_line": 12},
      {"path": "src/config.py", "start_line": 10, "end_line": 25}
    ]
  }]
}
```

仅真实人工标注使用 `human_annotation`；程序生成的夹具必须标记 `synthetic_fixture`，不能因为字段名称而宣称独立人工证据。每项必须覆盖整个闭区间；多个连续片段可共同覆盖，有空洞或只相交不算完整。每阶段记录覆盖的范围数和所有必要范围都齐全的案例数，分别定位输入/分块遗漏、40 候选截断、AI 选择可见范围限制及最终预算遗漏。`shown_to_selector` 表示相应片段 ID 和有限预览被展示，不表示选择器读过全文。范围未被读入或行号超出当前快照都会记为未覆盖，不据此认定原项目缺失。

没有标注时不产生覆盖率估计。这里测的是原始行范围出现与否，脱敏仍可能移除信息，不证明语义足够、全项目问题召回率或建议正确。人工标注应在读取模型结果前完成，并单独记录独立性；模型新增断言、自评或助手审阅不能冒充独立人工质量证据。

## 遗漏分布与归因边界

覆盖报告 v2 在每个标注跨度上记录首个可观察的遗漏环节，并汇总到 `omissions.by_first_gap`；`by_path_role` 按路径启发式区分测试、文档、构建文件、配置及其他源码，`cases` 保留具体任务和各自汇总。统计单位是“标注案例中的跨度出现次数”，同一原文被多个任务引用会重复计数，不等于独立缺陷数量。

| first_gap | 能观察到的事实 | 不能直接推出的原因 |
| --- | --- | --- |
| input_policy_exclusion | 该路径不符合冻结的输入策略 | 被排除文件已被读取、确实存在或一定包含唯一必要证据 |
| input_not_indexed_unknown | 路径允许，但冻结索引里没有文件 | 文件不存在、超限、不可读或下载省略中的某一个确定原因 |
| chunk_index_omission | 文件已读取，但标注跨度没有完整进入片段索引 | 仅凭聚合标记认定是总片段上限还是超长单行 |
| candidate_pool_omission | 跨度已索引，但未完整进入候选集合 | 一定因为通用查询不匹配任务，而不是排序、候选上限等因素 |
| selector_visibility_limit | AI 选择实际生效，但所需片段 ID 未全部展示给选择器 | 模型理解错误；被展示 ID 也不表示模型读过全文 |
| ai_selection_omission | 片段可见，但没完整进入 AI 选择及锚点组成的预算前集合 | 模型语义判断一定错误或最终建议一定错误 |
| not_retrieved_from_index | iterative 的必要跨度未进入初始候选及后续命中的可用集合 | 断言项目没有相关实现或必然需要更多轮 |
| iterative_context_selection_omission | 扩展可用范围包含跨度，但最终分析的预算前集合未完整包含 | 唯一认定是模型保留策略、控制器选择还是失败恢复的原因 |
| context_budget_omission | 片段进入预算前集合，未完整进入最终证据 | 排序模型未选中该片段 |
| final_context_omission_unknown / pre_budget_omission_unknown | 存在遗漏，但缺少足够的阶段记录 | 自动补出唯一原因 |

已经进入最终上下文的跨度不记为遗漏；AI 选择失败后按实际 lexical 回退诊断，不把未展示给 AI 的片段一律归咎于选择器。超出已索引文件行数的标注记为 `invalid_annotation`，单独计数，不进入阶段覆盖分母或检索遗漏计数；包含无效标注的案例不进入完整案例分母。未读文件的行号无法在此核对，仍保留未知。审计能从冻结标注、范围和预算前 ID 重算这些统计，但不能确认标注本身正确。

`omissions.causal_conclusions` 始终为 `not_established`。本次合成测试覆盖各条分支，尚未测得真实项目中这些类别的比例。标注跨度没有出现也可能存在等价的替代证据；当前格式是指定跨度的全部满足关系，不支持替代证据组，需人工复核后才能将跨度遗漏解释为任务证据不足。

## 先测量，再选择改进方式

1. 冻结项目 commit、实现、输入清单、预算和具体读者任务，在读取检索/模型结果前由独立人工标注所需证据，并记录文件及原文摘要。标注应覆盖文档、实现、配置与测试中的必要内容，注明可替代证据。
2. 先运行当前通用查询基线，按任务和文件角色检查遗漏发生在输入、分块、候选、选择还是预算；抽查每类原文。输入未索引但原因不明时保留未知，不能从跳过总数反推单个文件原因。
3. 分别做范围、查询和多轮对照，每次只改变一个因素，固定候选上限、每轮上下文、模型配置与最多请求数，报告实际读取量及 token。任务词项已作为 iterative 的显式选项实现，仍未给出收益结论；可先在同一 iterative 策略内对照是否提供任务。范围变化会改变输入 snapshot_id，应绑定同一上游 commit，并单独封存各范围快照；保持人工任务、原文摘要和必要证据标签一致，不能声称两组输入快照相同。
4. 根据预先确定的验收标准判断是否值得使用新增能力。测试文件被策略排除，就评估调整范围；已索引的任务证据难以进入候选，就评估任务查询与排序；最终主要受预算限制，就评估分配。受限多轮检索已经提供工程实现，是否提高真实任务表现仍需对照；不要把任务词项、范围扩大和额外请求数的联合变化归因为单一因素。

上述步骤是尚待完成的实证研究流程，不是已有评测结果。候选覆盖、模型建议正确性与读者任务成功率分别测量；不能用工程测试通过或生成数量替代。

## 文件范围

教程默认额外包含 Dockerfile、Containerfile、Makefile、GNUmakefile。原有 `project_input.eligible(path)` 通用策略与修复配置不变；教程在调用时传专用 `EvidenceScope`。`project_input` 的教程入口及本地发现共享配置，避免下载阶段就丢掉稍后希望索引的文件。

`--include-tests` 允许普通 test/tests 目录；`--include-path PATTERN` 可重复，采用相对 POSIX 路径的 fnmatch 匹配，`*` 可跨目录；显式匹配的普通 UTF-8 文件也允许无支持后缀。隐藏目录只有被显式纳入时才遍历。`--exclude-path PATTERN` 优先；不能使用绝对路径、越界路径或反斜线。`.git/.hg/.svn`、`.env/.env.*`、已知敏感文件名、私钥及 evaluator 配置不能由纳入规则覆盖；符号链接与各项大小上限继续生效。

普通项目测试可作为源码契约上下文，但工具不会执行它们，也不会把模型修改后的断言当作独立证据。包含测试时仍需检查是否有项目自己的私密 evaluator 内容。

## 云端审阅

```sh
# 第一次：只有清单，退出 2，不发模型请求
python3 -m exampleproof analyze /path/to/project --output /tmp/tutorial \
  --cloud-review /tmp/tutorial-review.json --redact-values /path/to/local-redactions.json

# 人工检查文件清单与每个 permitted_evidence 后使用其中 sha256
python3 -m exampleproof analyze /path/to/project --output /tmp/tutorial \
  --cloud-review /tmp/tutorial-review.json --redact-values /path/to/local-redactions.json \
  --approve-cloud REVIEW_SHA256
```

自定义脱敏文件是非空字符串的 JSON 数组，仅在本地读取。自动规则覆盖常见 API key/password/token 赋值、Bearer、URL 中的用户名密码及 PEM 私钥；先对整文件脱敏再按原行号切片，以保护跨片段私钥及预览边界。自动规则是启发式检测，无法识别任意格式的秘密、业务资料或个人信息；确认前必须人工阅读完整候选原文的脱敏视图。若仍有敏感内容，补充脱敏值或排除文件并生成新清单。

清单绑定原始快照摘要、文件摘要、范围、脱敏内容、模型端点、提示词、策略与字符预算。lexical/ai 的确认范围是最多 40 个候选，摘要只从已脱敏全文生成；iterative 的确认范围覆盖整个合格片段索引，并额外绑定任务的脱敏视图和补充检索轮数。实际模型请求始终只包含预算内子集。首次即使传入确认字符串也不会发送；必须先有完全匹配的清单。改变内容或配置时旧清单拒绝复用，不自动覆盖，不自动批准，不自动换服务。

仅真正发出的脱敏证据计入云端证据字符预算；本地报告仍引用原始快照，推理请求记录则保存实际发送的脱敏内容。模型基于脱敏段落提出的编辑可能因无法精确匹配原文被拒绝，这是保守编辑边界。清单、快照和输出报告均是本地产物，可能含路径或未经发送的原文，分享前仍需审阅。

静态和回环 Ollama 不需要云端确认。`analyze_snapshot` 与 `run_comparison` 的 DeepSeek 库接口也拒绝没有 `review_cloud` 授权包装的客户端；传入包装时应复用同一个冻结 `ProjectSnapshot`。通用 JSON 传输和旧修复流程的 API-key 保护不等于通用项目隐私扫描器。

新冻结的 factorial 脚本会先为所有云端项目生成 `cloud-reviews/PROJECT.json`，所有预览确认完成前不启动任一供应商的请求。审阅后用 `run OUTPUT --cloud-approvals PATH` 提供项目名到 SHA-256 字符串的 JSON 映射。历史实验必须使用原归档实现及协议；补丁没有重新执行它们。

## Markdown 与质量评审

已有闭环测试在临时副本应用导出的 Markdown 补丁，核对受保护代码仍一致；不改用户原件。最多两个正文段落的限制保持不变。`accepted` 只表示通过原文匹配及保护规则，`validation_scope` 和 `quality_review_status` 明确记录这个边界。

`review-template.json` 的 `items` 留建议评审，`edits` 留文字补丁评审，人工字段初始为 null。`compare-audit` 仍只核对归档的一致性；新增覆盖数可从冻结标注重新计算。审计返回 `quality_review_status: not_assessed_by_audit`、`quality_passed: null`，不会更新人工评审状态或选出质量优胜者。录制候选回放、合成夹具、历史兼容重现与实时模型结果继续分开记录；此次没有重跑或改写历史实验。
