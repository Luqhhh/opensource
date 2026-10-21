# 小规模读者任务评测：已完成首批调用与人工质评

本批输入是 python-dotenv v1.1.0（`6a02ef5a1034d66338811757df07a113a1169af6`）和 platformdirs 4.3.8（`22089f1e1ff477037cd7b3e03ad38ae2bf251031`）。它们未出现在此前教程 2×2 实验中。四个读者任务、必要证据跨度与验收条件由助手在模型运行前起草；不是随机抽样、独立人工标注或已经完成的留出效果实验。原始源码、测试与许可证按固定提交复制，不运行项目安装脚本。

[spec.json](spec.json) 包含环境变量优先级、无副作用配置读取、Linux 示例首次复制、用户目录创建四项任务。草稿中的空 gold_issues 和 Linux `os` 导入问题最初均为助手提出的判断；本批已由用户核对完整快照并确认清单，才用于下方的质量统计。后续新批次仍须核对健康假设、漏掉的问题及可替代证据；改变任务、跨度或问题清单后须另建冻结目录，保留旧版。

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

读者观察另填 participant、completed、elapsed_seconds；没有观察则任务完成率和耗时保持 null。机器检查通过不代替读者完成任务。报告按策略分开汇总，两个项目、四个任务不支持总体效果或显著性结论。2026-10-21 已完成本批实时调用与用户逐条质评；尚无本批实际读者观察。详见下面的结果。


## 2026-10-21 首批基线结果

用户先逐项核对原始四任务及完整问题清单，运行后再逐条核对并认可 38 条建议的质评。质评理由由助手起草后交由用户确认，属于单一人工评阅者的非盲审，不是多个独立标注者一致性实验。记录保留两次明确确认原文。前端只用于结果展示，不承担人工审批。

| 指标 | lexical | iterative |
| --- | ---: | ---: |
| 建议数 | 21 | 17 |
| supported / partial / unsupported | 2 / 10 / 9 | 3 / 9 / 5 |
| 建议支持率 | 9.52% | 17.65% |
| 无支持建议占比 | 42.86% | 29.41% |
| 冻结问题召回率 | 0/1 | 0/1 |
| 实际请求数 | 4 | 4 |
| 实际输入 / 输出 token | 16,133 / 2,573 | 17,185 / 2,214 |
| 分析总耗时 | 14.43 秒 | 12.76 秒 |
| 真实读者完成率 / 耗时 | 未观测 | 未观测 |

两组均漏掉 Linux 示例的 os 导入问题。iterative 四次都没有实际请求补充检索，不能把此结果解释为多轮检索收益。已有说明被重复说成缺失的建议按错误或部分支持处理；体验建议有事实依据也不自动计作冻结缺陷。

运行严格使用原冻结实现，输入 seal 为 `bc989897ca1dcdfa9c8f4fe809521e12d4fafdcca923dbcbbc8e5e525d187fdc`。原模型调用保存于外部工程交付 `baseline-run/`，失败的网络沙箱尝试保留于 `baseline-run-sandbox-restricted/`，未知 token 未填零。人工记录为 `human-preflight-approved.json` 和 `human-quality-approved.json`。较大生成报告需要新版汇总器的 16 MB 读取上限；项目输入的默认 256 KB 上限保持不变，原分析结果未改写。

新增方法应另建冻结协议。原四任务已用于开发，重新冻结不使它们成为未见留出集；当前尚未取得新数据上的独立误报/漏报效果结论。
