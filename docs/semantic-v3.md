# 自动修复增强：semantic-v3（2026-10-17）

基于已同步的 `2a4badf93ce1129ec1e4fe08ddd036be919e8a8b` 开发。新策略显式选择，不覆盖默认 legacy、semantic-v2、固定输入、旧检查或历史实验。

## 对应的实际失败

旧开发记录中，`collate` 候选即使找到了合适 API，也没有保留公开要求的可复用名称；通用字符串转换候选尝试定义适配函数，却超出旧版只接受直线代码的范围。v3 从工程上解决这两类阻碍，同时保留外部语义检查。没有因此声称全部历史失败可被修复。

1. **先检查公开名称要求。** 从示例公开上下文中的明确 `callable/function named/called NAME`、`reusable NAME(...) callable`、`reusable zero-argument NAME callable` 或中文“名为 NAME 的函数”识别可复用名称，仅接受原示例已经绑定的名称。缺失或被直接替换为常量/容器的名称会被拒绝，下一轮获得具体原因。普通别名和适配函数仍需通过原检查；静态预检不是语义证明。
2. **允许受限的适配函数。** 最多四个顶层 `def`，仅常量默认参数、可选 docstring、局部赋值和一个末尾 `return`。支持条件表达式，继续拒绝控制流语句、装饰器、注解、嵌套定义、动态执行、危险引用、双下划线访问和属性/下标赋值。原断言必须完整保留在顶层；函数内新增断言不能形成独立证据。
3. **利用实际失败重新查找源码。** 源码摘录预算为 4800 字符；上一轮候选在示例执行阶段出现异常时，分配新候选检索 1600 字符、原任务检索 3200 字符。另用最多 1200 字符补充已选完整函数签名的所属类/名称及原文签名，帮助区分同名方法；不引入未选函数的答案或隐藏检查。两部分总预算最多 6000 字符，原文、位置和所属类可从公开源码核对。
4. **有限预算内改变尝试。** 每次请求 seed 根据原始 seed 和完整轮次递增。原样返回已知失败代码的候选会在执行前拒绝，并明确要求改动失败操作；按 AST 识别注释、引号或空白变化后的重复候选，不重复执行，可继续使用原来的次数预算。请求只保留最近两轮候选与反馈，完整原始请求、响应、失败和成本仍在报告中。
5. **约束回答结构。** v3 使用 Ollama 的 JSON Schema 输出约束，要求同时返回字符串形式的 `code` 和 `rationale`。全过程仍执行断言保护、公开名称检查和原样/重复候选检测；不合格式的候选在原有预算内重试，服务故障停止。legacy/v2 请求格式不变。接口依据见 [Ollama generate](https://docs.ollama.com/api/generate) 和 [结构化输出](https://docs.ollama.com/capabilities/structured-outputs)；未引入 SDK 或第三方运行依赖。

新版使用独立通用提示词，不硬编码项目名、缺失 API 的答案或案例 ID。Qwen 等模型仍须自行从公开任务与源码提出候选。

## 使用

需要 Linux/WSL、可用 Bubblewrap 及同一执行环境内已运行的本地 Ollama 模型服务。工具不自动安装或下载模型。

```sh
python3 -m exampleproof doctor
python3 -m exampleproof repair examples/tutorial \
  --model YOUR_LOCAL_MODEL --repair-policy semantic-v3 \
  --max-attempts 3 --model-timeout 180 --output artifacts/semantic-v3-live
```

默认生成配置为 temperature 0.2、seed 17、num_ctx 8192、num_predict 2048。`--max-attempts` 仍默认 1，需显式增加。v3 只用于实时模型路径，不能与 `--proposals` 回放混用；历史参考补丁不能作为新版模型输出。

## 实时对比入口

```sh
python3 scripts/compare_repair_policies.py \
  benchmarks/semantic_v2/development/tinydb \
  benchmarks/semantic_v2/development/more_itertools \
  benchmarks/semantic_v2/development/markupsafe \
  --model YOUR_LOCAL_MODEL --seeds 17 29 43 \
  --max-attempts 3 --output artifacts/semantic-v3-comparison
```

该入口会先冻结明确选择的输入、模型摘要、当前实现和预算，再比较 v2/v3；归档同时保留输入来源记录、上游许可证与实现所含的许可文件，不复制参考候选或把归档材料加入源码检索。每个种子中两组使用相同的 seed 递增规则、最多三次调用和每次 2048 输出 token 上限。实际请求数和输入 token 不保证相同，均如实记录。种子之间交替执行顺序，保留失败与完整三阶段补丁复查。默认在标准错误输出逐例进度，`--quiet` 可关闭；标准输出仅给出最终概要。输出须为新目录；输入、实现或模型改变时停止并保留不完整状态，不填入看似有效的成功率。

这些是已经观察过的开发/回归案例。三组项目包含 6 个失败与 3 个健康对照；重复 seed 不是新增独立缺陷。v2 比较组也使用上述配对预算和递增 seed，与默认 CLI 配置或历史实验不完全相同，应以本次同条件比较为准。v3 同时改变提示词、结构范围、预检、反馈利用和输出格式，不能把差异归因于某一个因素，也不能冒充新的留出实验。命令退出 0 表示对比完整，不表示全部案例修复成功；模型或环境不完整返回 2。

配对入口另为两组共同设置 `repeat_penalty: 1.1`，依据 [Ollama 参数说明](https://docs.ollama.com/modelfile#valid-parameters-and-values)，用于降低小模型退化成连续重复 token 的风险。该参数写入冻结协议和每次请求；普通 `repair` 命令的生成参数保持原样。首轮 1.5B 对比因模型服务报 `prediction aborted, token repeat limit reached` 中止，保留不完整记录；调整共用参数后须在新目录重跑完整对比，不拼接成功子集或把服务错误改记为零分。

## 当前验证与限制

新增 29 项回归覆盖：适配函数的支持边界、原断言保留、公开名称预检、拒绝反馈、种子递增、重复候选预算、历史裁剪、公开异常检索、隐藏检查不泄露、源码切片合并、对比协议、归档许可和排除参考候选、逐例进度、结构约束请求、不合格式响应处理，以及公开名称新表述、原样返回拒绝、结构等价重复和原文签名所属类；其中三项在真实 Bubblewrap 中执行候选、拒绝错误语义并完成补丁应用复查。模拟回答全部标记为模拟，不计为真实模型修复。

已校验并准备 Ollama 0.40.5 和 Qwen2.5-Coder 1.5B。完整开发过程、逐题结果及原始证据见 [1.5B 实测记录](evidence/semantic-v3-1p5b/README.md)。第三轮冻结实现中，v3 为 3/18、配对 v2 为 2/18，两组正常对照均 9/9；但两组修复的是不同缺陷类型，v3 调用更多。后续分阶段实验退步，已撤回；旧策略在重复完整实验中为 2～3/18，因此不能据此宣称稳定或显著提升。后续增加独立的 [v4 按行修复策略](semantic-v4.md)，不改写此前冻结证据。默认仍为 legacy；历史 7B 和旧留出记录保持原样。

本机便携环境保存在忽略的 `artifacts/local-runtime/`。需要再次使用时，可在 WSL 的仓库根目录启动服务（不安装系统服务）：

```sh
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS="$PWD/artifacts/local-runtime/models" \
  artifacts/local-runtime/ollama/bin/ollama serve
```

另一个 WSL 终端可使用上面的 `repair` 命令，将模型名替换为 `qwen2.5-coder:1.5b`。修复结果仍须复验和人工审核；普通 repair 参数与配对实测的专用生成配置不同。
