# 小规模读者任务评测：准备完成，独立评阅待进行

本批输入是 python-dotenv v1.1.0（`6a02ef5a1034d66338811757df07a113a1169af6`）和 platformdirs 4.3.8（`22089f1e1ff477037cd7b3e03ad38ae2bf251031`）。它们未出现在此前教程 2×2 实验中。四个读者任务、必要证据跨度与验收条件由助手在模型运行前起草；不是随机抽样、独立人工标注或已经完成的留出效果实验。原始源码、测试与许可证按固定提交复制，不运行项目安装脚本。

[spec.json](spec.json) 包含环境变量优先级、无副作用配置读取、Linux 示例首次复制、用户目录创建四项任务。前三项健康/缺陷判断都需人工复核；空 gold_issues 只是助手草稿中的健康假设，不能直接据此计算真实误报率。Linux `os` 导入问题也是待核对的局部判断。评阅者应检查完整快照，补充漏掉的问题及可替代证据；改变任务、跨度或问题清单后须另建冻结目录，保留旧版。

## 冻结、评阅与运行

```sh
# 从固定提交准备新输入和协议；只联网下载公开文本，不调用模型
python3 scripts/run_tutorial_evaluation.py prepare docs/task-evaluation/spec.json /tmp/reader-study

# 已有本地快照：复制 spec，调整 project.root，再冻结
python3 scripts/run_tutorial_evaluation.py freeze /path/to/spec.json /tmp/reader-frozen
```

冻结目录保存合格输入、许可、任务、原文跨度 SHA、文件范围、模型、请求设置、调用/用量/时间限制，以及完整实现。seal.json 覆盖协议与所有文件。相邻的 preflight-review-template.json 初始为未批准。独立人工评阅者须说明身份、自述未编写这些标注或候选，确认任务、必要证据和完整问题清单，再在冻结目录外提交评阅记录。声明不是身份认证；缺少真实评阅时保持待评阅，不由模型代填。

```sh
python3 scripts/run_tutorial_evaluation.py run /tmp/reader-study/frozen /tmp/reader-run \
  --review /path/to/independent-preflight-review.json --cloud-reviews /tmp/reader-cloud
# 首次生成各任务/策略的发送清单，不发模型请求。
# 人工检查后提供以 case-id-strategy 为键、审阅 SHA 为值的 JSON：
python3 scripts/run_tutorial_evaluation.py run /tmp/reader-study/frozen /tmp/reader-run \
  --review /path/to/independent-preflight-review.json --cloud-reviews /tmp/reader-cloud \
  --cloud-approvals /path/to/approved-hashes.json
```

运行前检查独立评阅、快照和实现一致性，完成所有云端预检。lexical 与 iterative 使用相同任务、索引、候选排序、文件范围和最终字符上限；每个任务轮换先运行的策略。评测专用 task_comparison 入口允许 lexical 接收任务，不改变普通 analyze 的 --task 限制，也不把冻结的验收条件、gold 问题或证据标注发送给模型。标注只用于事后覆盖统计。

## 指标与缺失值

每次分析保存原始请求、响应、输入/输出 token、实际请求数、分析耗时、必要证据覆盖和警告。相同字符上限不是相同 token 或费用；单次请求可能跨过累计用量停止阈值。

quality-review-template.json 必须逐条填写 supported / partial / unsupported / unassessable、理由和命中的冻结问题 ID。支持率和无支持建议占比的分母为全部建议，四类数量另列；问题召回率以冻结 gold 问题为分母，不以必要证据跨度代替问题数。无 gold 时召回率为 null；零建议时支持率为 null；不删除失败或未知用量记录。

```sh
python3 scripts/run_tutorial_evaluation.py summarize /tmp/reader-study/frozen /tmp/reader-run
python3 scripts/run_tutorial_evaluation.py summarize /tmp/reader-study/frozen /tmp/reader-run \
  --review /path/to/independent-quality-review.json
```

读者观察另填 participant、completed、elapsed_seconds；没有观察则任务完成率和耗时保持 null。机器检查通过不代替读者完成任务。报告按策略分开汇总，两个项目、四个任务不支持总体效果或显著性结论。当前交付不包含新实时模型结果、人工评分或读者实验结果。
