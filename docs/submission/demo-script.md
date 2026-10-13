# 演示视频脚本（目标 4 分 20 秒，尚未录制）

作品：例证——开源文档智能验证助手。用于 3–5 分钟 MP4 录屏；最终体积须不超过 300 MB。时间轴是拍摄计划，不能替代视频实测。

## 录制准备

在可运行 Bubblewrap 的 Linux 环境打开终端、仓库和独立 HTML 报告。终端提示符只显示项目名，关闭账号页面和通知，隐藏无关桌面内容。视频、片头片尾及画面中不得出现参赛单位名称、标志或指导信息。现场推理前核对服务版本与模型 manifest；仅在模型已安装时执行，不在录屏中下载 4.7 GB 权重。

先进行一次预演，确认原始文件未修改、`check` 的已知失败为预期。若实时推理出错，展示实际错误或明确切换到已保存的历史运行；不能将回放剪接成当次实时生成。缩短等待画面时标注“等待片段已加速”，保留原耗时及原记录。

## 时间轴与讲解

| 时间 | 操作/画面 | 建议讲解 |
|---|---|---|
| 00:00–00:30 | 标题与 MarkupSafe 历史版本迁移 | “API 升级后，文档示例可能失效。单个显示值正确，也不一定保留通用转换语义。例证把 AI 修复与预先设置的行为检查、可审核补丁连接起来。” |
| 00:30–01:05 | 展示原文出处、旧/目标版本及新版 convert 契约；运行 scan/check | “这是固定版本的真实源码迁移场景，新增绑定任务由评测者编写。普通字符串、Markup、None 等输入分别检查。它属于已见开发集，不能冒充新留出样本。” |
| 01:05–01:55 | 执行 semantic-v2 实时 benchmark；打开新报告 | “默认策略仍是 legacy；这里显式选择新版检索和分类反馈。模型收到任务、源码摘录和允许的反馈，不收到外部检查或预期输出。所有候选都重新在沙箱里检查；如未修好，也保留实际失败。” |
| 01:55–02:35 | 打开已归档的 escape 错误候选和外部检查失败 | “这一段是明确标记的工程负例回放，不是现场模型输出。显示的 Markup 相同，但 escape 不能替代一般字符串转换。9 个格式合法负例都被语义检查拒绝，8 个的显示输出仍正确。” |
| 02:35–03:10 | 展示本次 patch、输入快照和 patched 报告 | “只有通过检查的候选进入补丁；评测在一次性副本应用，再重新提取完整文档。工作区保持只读。这里的通过仅限预设检查，仍需人工审阅。” |
| 03:10–03:45 | 展示五组设计、两轮开发及留出 summary 与 token | “两轮开发五组预算内均4/6。锁定方法后，新项目留出五组均0/12，没有实现修复收益；输入token减少也不能称为修复效率提升。全部180次留出请求均保留，反馈未优于无反馈；12是4个失败的3次种子重复，不是12个独立缺陷，也不是赛事得分。” |
| 03:45–04:20 | 展示资源清单、方法锁、检查盲点和开放文件 | “核心实现、固定源码索引、案例和原始证据已开放。标准库索引的来源和许可单独披露。检查仍有缓存序列、对象边界和同进程局限；下一步需维护者复现与人工语义评价，不能先宣称普遍正确。” |

## 可复制命令

以下命令从仓库根目录运行，所有示例执行均由隔离执行器负责。

```sh
python3 -m exampleproof scan benchmarks/semantic_v2/development/markupsafe
python3 -m exampleproof check benchmarks/semantic_v2/development/markupsafe \
  --output artifacts/video-semantic-check
python3 -m exampleproof benchmark benchmarks/semantic_v2/development/markupsafe \
  --model qwen2.5-coder:7b --repair-policy semantic-v2 --max-attempts 3 \
  --model-timeout 180 --output artifacts/video-semantic-live
```

现场没有模型时，可用以下命令演示工具链，画面持续标注“记录候选回放，无实时推理”，随后打开已保存的真实推理证据：

```sh
python3 -m exampleproof benchmark benchmarks/semantic_v2/development/markupsafe \
  --proposals benchmarks/semantic_v2/development/markupsafe/proposals.json \
  --output artifacts/video-semantic-replay
```

负例画面使用 `benchmarks/semantic_v2/development/evidence/validation-02/markupsafe/negative-escape_instead_of_convert/repair/report.html`；旁边显示该记录属于人工构造的错误候选回放。不要把它的拒绝计为模型修复失败或模型输出。

真实模型历史证据入口为 [新版实验总览](../evidence/semantic-v2-20261013/README.md)，分别打开 development-01、development-02 与 holdout 记录；三者均 complete=true，已完成终态复核与独立审计。留出五组均0/12、健康各6/6、各36次请求；source_v2 输入95,778 token，legacy_source 输入160,488 token。零成功时每成功修复成本不可定义，不预录“反馈有提升”或“collate已修好”。旧 v1 已冻结，审计须使用 `--archived-only`。真实历史调用标注日期；现场结果可能不同，以新报告为准。`benchmark` 输出目录必须尚不存在，重录时另建目录；等待加速需明确标注。

## 导出与验收

录制为 1920×1080、MP4/H.264，文字保持可读；这些编码参数是建议，规则硬性条件为 MP4、3–5 分钟、≤300 MB。导出后用播放器和媒体探测工具核对实际时长、格式、文件字节数；完整观看一遍确认脱敏、音画和数据口径。此项目前尚未完成，不能在提交清单中勾选视频完成。
