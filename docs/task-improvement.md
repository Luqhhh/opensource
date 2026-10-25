# 从已有建议到任务验证

新增 task-improve 将一条已有分析建议、明确文档候选和调用者冻结的任务合同关联起来。它支持现有 Markdown Python 围栏和有限 RST Python/pycon 块；优先用于局部路径配置、初始化顺序和简单 API 用法。不会替用户或模型生成、放宽任务检查。

```sh
python3 -m repopath task-improve /path/to/project \
  --analysis /path/to/analysis.json --finding 1 \
  --contract /path/to/task.json --output /tmp/task-improvement
```

finding 从 0 开始。默认 DeepSeek；首次生成精确请求的 cloud-review 清单，审阅后使用 --approve-cloud SHA。可使用 --cloud-review PATH、--redact-values PATH；清单绑定模型、任务合同摘要、原始分析摘要、建议序号和待发送正文。检查代码、setup 和预期输出不进入模型请求。Ollama 需显式 --provider ollama --model NAME。

流程依次校验诊断快照和引用原文、冻结任务与输入、隔离检查原示例、请求一次候选、执行结构守卫，再通过 task-check 的前后验证及补丁应用复查。原任务已通过或环境被阻塞时不请求模型。成功只表示有限任务检查通过，补丁仍为 human_review_pending。

候选只能返回 original、replacement、rationale。候选不能改任务合同、其他 Python 块、RST 指令、既有断言或记录的 REPL 输出。拒绝、模型失败、放弃和验证失败均保存结果，不自动重试、应用到原项目或向上游提交。

也可以明确回放原先记录的候选：

```sh
python3 -m repopath task-improve /path/to/project \
  --analysis /path/to/analysis.json --finding 1 --contract /path/to/task.json \
  --proposal /path/to/recorded-proposal.json --output /tmp/task-replay
```

回放 JSON 同样只含 original、replacement、rationale；origin 由程序记录为 recorded_candidate，模型请求为 0。模型生成候选记录为 live_model_candidate；合成接口测试记录为 synthetic_candidate。输出包括 binding.json、原合同、诊断、输入、实现、候选、模型记录（若有）、validation/ 和 improvement.json；只有前后任务及补丁复查通过且原输入未变时才在顶层生成 adoptable.patch。

本轮已用既有 TinyDB 诊断与候选完成这条新入口的工程回放，未产生新的实时推理成功样本。原合同逐字复用，SHA 为 1fc251e279190784cecef1c5f8df0a933668197fa07e857adf65dc48b788a8e4。独立质量评阅、完整安装/渲染和上游采纳仍待完成。
