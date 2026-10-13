# 三个真实项目的冻结对照实测

2026-10-13 完成 **3 个项目、5 个历史迁移失败、3 个健康对照**的取证，以及 **3 种条件 × 3 个种子**的实时模型实验。27 个实验单元全部完成，92 次请求全部保留，无模型服务或沙箱中断。

**本次结果：加入源码的预算内通过数为 9/15，直接模型为 7/15；加入反馈为 8/15，没有显示额外收益。** 这些是通过冻结行为检查并完成补丁应用复查的次数，不是一般语义正确率，也不是比赛评分。每组 15 次运行仍只对应 5 个失败案例。

## 真实项目证据

| 项目 | 官方文档版本 → 目标源码版本 | 旧版同一检查 | 目标版原始检查 | 参考补丁应用复查 |
|---|---|---:|---|---:|
| [TinyDB](../../../benchmarks/real_projects/tinydb/README.md) | 3.15.2 → 4.8.2 | 3/3 | 2 失败、1 健康 | 3/3 |
| [more-itertools](../../../benchmarks/real_projects/more_itertools/README.md) | 5.0.0 → 9.0.0 | 3/3 | 2 失败、1 健康 | 3/3 |
| [MarkupSafe](../../../benchmarks/real_projects/markupsafe/README.md) | 1.1.1 → 2.1.5 | 2/2 | 1 失败、1 健康 | 2/2 |

[逐例索引](../../../benchmarks/real_projects/README.md) 记录固定 commit、原文 URL/行号、原样文件及许可证、SHA-256、机械转换、原始错误、参考候选和复查。原版同一检查 8/8 通过，证明原始文档在声明的旧版条件下可运行。历史源码均在当前 CPython 3.10.12 沙箱内运行，不声称重建了发布当年的完整系统环境；MarkupSafe 使用上游纯 Python 实现，more-itertools 旧版控制另使用固定 six 1.16.0 源码。

参考补丁是模型实验前准备的工程候选，回放不调用模型。实时模型修复另存于本目录的 `runs/`。所有补丁只适用于带来源映射的规范化 Markdown，不能直接应用到上游 RST/docstring，也没有作为上游 PR 提交。三个项目是本轮工作目标，不是赛事规定的数量。

## 冻结条件与公平性

- 三组都获得同一原示例、周边文档和初始错误；`direct` 没有源码或历史，`source` 增加目标源码摘录，`source_feedback` 再增加此前候选和反馈。
- 使用既有应用提示词，没有根据本批实时输出调整。外部检查和参考补丁不进入请求；外部检查失败的具体断言被隐藏。TinyDB 的初始夹具和 collate 可复用绑定要求在冻结前已写入任务上下文。
- 每例最多 3 次请求、每次最多 1024 个生成 token，首次通过即停止；三组均由同一检查选择候选。前两组后续为独立采样，只有第三组接收历史。放弃、重复、结构拒绝及无效生成内容都耗预算；基础设施异常会使实验不完整。
- 模型 `qwen2.5-coder:7b`，Q4_K_M，摘要 `dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`；Ollama 0.40.3、RTX 4070 Laptop GPU 8 GB、temperature=0.2、num_ctx=8192、num_predict=1024、超时 180 秒、单并行请求。
- 种子 17、29、43，第 k 次请求使用 `seed + k - 1`，各组配对相同。按项目与种子轮换组顺序。源码窗口由词项匹配和 API 签名自动选择，源码及标签合计最多 12000 字符，推理前保存冻结；它不等于完整源码。
- 冻结时间与开始/结束时间分别保存在 [protocol.json](protocol.json)、[started.json](started.json)、[finished.json](finished.json)。输入、基线错误、源码窗口、提示词、实现和预算均固定。开始和结束均核对模型摘要及输入。协议 SHA-256 为 `3f04390bca570862d412c4318be85be4b002ebba3facdc1297f4c7419d0ec7a4`；本地摘要用于检测误改，不是外部预注册或第三方时间戳。

“未用于本应用调提示词”不表示基础模型预训练时未见过公开文本。案例是按易复现的历史 API 迁移人工/AI 辅助选择，非当前上游缺陷的随机样本；TinyDB 两例也具有相关性。

## 实测结果与成本

以下分母仅含失败案例：5 例 × 3 个配对种子 = 15 次。每组另有 9 次健康案例复查，全部通过且未调用模型。

| 条件 | 首次调用通过 | 最多 3 次调用内通过 | 请求数 | 输入 token | 输出 token | 请求累计秒 | 单元累计秒 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 直接模型 | 4/15（26.7%） | 7/15（46.7%） | 35 | 24,926 | 4,513 | 139.9696 | 148.7099 |
| 加入源码 | 8/15（53.3%） | 9/15（60.0%） | 28 | 129,525 | 4,177 | 145.1755 | 153.8261 |
| 源码＋执行反馈 | 8/15（53.3%） | 8/15（53.3%） | 29 | 140,668 | 4,669 | 150.1530 | 159.0571 |

来源：[summary.json](summary.json)，逐次案例结果：[outcomes.csv](outcomes.csv)。请求累计秒含请求中的冷启动/加载等待；单元累计秒还包括候选执行、报告、补丁应用与完整文档复查，不含前置冻结工作。不同输入长度、缓存、输出长度及宿主负载影响耗时，不能据此声称推理速度改善。没有测量电力或货币成本。

源码组本次多通过 2 次案例运行，输入 token 约为直接组的 5.20 倍。反馈组相比源码组少通过 1 次，输入 token 进一步增加约 8.60%；本轮没有反馈挽救首轮失败的案例。直接组通过独立重采样额外修好 3 次，源码组额外修好 1 次，所以预算内指标不能当作单次性能。

## 逐例结果与失败

表中每格依次为种子 17 / 29 / 43 的首次成功轮次，`×` 表示预算耗尽仍未通过。三组“至少一个种子成功”的不同案例覆盖均为 **3/5**，不是源码组扩大了不同缺陷的覆盖数量。

| 项目 / 失败案例 | 直接模型 | 加入源码 | 源码＋反馈 |
|---|---|---|---|
| TinyDB / purge_default | 1 / 1 / 1 | × / × / × | × / × / × |
| TinyDB / purge_named_table | × / × / × | 1 / 2 / 1 | 1 / × / 1 |
| more-itertools / collate | × / × / × | × / × / × | × / × / × |
| more-itertools / grouper | 2 / 2 / 3 | 1 / 1 / 1 | 1 / 1 / 1 |
| MarkupSafe / safe_string | × / × / 1 | 1 / 1 / 1 | 1 / 1 / 1 |

- **源码也会干扰修复。** TinyDB 默认表案例中，直接组使用 `db.truncate()` 通过；源码组反复使用 `db.drop_table('default')`，没有清空真实默认表，行为检查失败。参见 [source / seed17](runs/17/source/tinydb/inference.json)。因此不能把增加上下文写成必然提升。
- **行为错误与格式错误分别说明。** TinyDB 命名表直接组未找到正确调用；源码组能够使用 `drop_table`。反馈组 seed29 后续虽采用正确表操作，却新增 `print(table.all())`，违背冻结的空 stdout 契约，仍计失败；这不等于表删除操作本身错误。参见 [source_feedback / seed29](runs/29/source_feedback/tinydb/inference.json)。没有事后放宽检查来提高成绩。
- **collate 全部失败。** 直接组把排序归并误换为 `sort_together`，出现参数/行为不匹配；源码组导入其他函数后仍调用未定义的 `collate`。反馈组仍未形成通过候选，其中一次新增函数定义被 v0.1 直线代码限制拒绝。完整记录见 [direct](runs/17/direct/more_itertools/inference.json)、[source](runs/17/source/more_itertools/inference.json)、[source_feedback](runs/17/source_feedback/more_itertools/inference.json)。拒绝也计成本，不能都归为模型 API 知识不足。
- **grouper 的源码信息有效。** 两个源码条件均首轮通过，而直接组需要第二或第三次独立采样；这没有执行反馈参与。参见 [direct / seed43](runs/43/direct/more_itertools/inference.json)。
- **MarkupSafe 仅验证本例。** 接受的模型候选使用 `escape(value)` 或嵌套 `escape`，没有采用参考候选的 `soft_str`。对本例已经是 `Markup` 的输入，输出与冻结检查通过；这不证明保留了 `soft_unicode` 对所有输入的通用转换语义。参见 [source / seed17](runs/17/source/markupsafe/inference.json)。仍按原协议计通过，并明确有限检查的边界。

全部 92 次请求中，24 次候选通过、66 次执行/行为复验失败、2 次结构拒绝；24 个通过候选均完成补丁应用复查。结构拒绝与失败没有删除，也没有用参考候选补足模型成绩。

## 独立核对与复现

[独立审计](independent-audit.json) 直接读取请求、响应与补丁，不依赖 study 的汇总函数：27/27 完整单元、15/15 对源码组与反馈组首轮 payload 完全相同，模型/参数/种子/预算一致，检查与参考答案未进入请求，选中候选来自实际模型响应，成本与汇总一致。补丁在内存中另行应用，结果与复查文档哈希一致。它不再次调用模型或执行上游代码。

第二份 [逐例复核记录](review-audit.json) 另记录候选内容和检查边界。固定种子不保证实际字节输出完全一致：15 对同输入首轮中，9 对原始响应相同、5 对代码相同但其他文本不同、1 对代码不同；对应首轮通过状态全部一致。服务响应的最大输入＋输出计数为 6162，最大返回 context 长度为 6161，均低于 8192，全部 `done_reason=stop`。这些是返回计数的核对，没有完整服务器日志或独立 tokenizer 证明，不作绝无截断的更强主张。

```sh
# 从仓库根目录执行：无需模型服务，仅核对保存的证据
python3 scripts/verify_real_project_study.py docs/evidence/real-projects-20261013

# 重新统计保存的记录，不覆盖原始推理
python3 scripts/run_real_project_study.py summarize docs/evidence/real-projects-20261013
```

重新推理须先用新目录执行 freeze，再 run，命令见 [评测协议](../../benchmark.md)。归档的 [implementation](implementation/) 保存与协议哈希一致的 13 个模块及运行脚本；未来应用实现变化时，可用 `python3 docs/evidence/real-projects-20261013/implementation/scripts/run_real_project_study.py` 调用本次实现，仍应使用新的实验目录。原始上游输入与许可随 `inputs/` 保存。

逐轮证据入口是 `runs/<seed>/<arm>/<project>/inference.json`；`selected.json` 是模型实际选中候选；`patch_validation/repair/verified.patch` 为导出的补丁；`patch_validation/patched/report.json` 为应用后的复查。该目录中的 `patch_validation` 属于已选真实候选的回放，不增加推理次数。`run.log` 保存全部单元执行状态。

工程验证另见 [测试日志](unittest.txt) 和 [安装包验证](package.json)。这些测试及参考回放不增加实时模型样本。结果补齐了“真实项目来源”和“可核验受控对照”两条证据；对创新性的表述应限于可审查工作流与此次观察，不能写成已证明执行反馈增益、一般修复正确率或上游采纳。
