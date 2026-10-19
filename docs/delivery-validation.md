# 2026-10-19 交付优化与验证

以下记录对应基于 fcdd4f56fb042afe28776ffee380a942da398686 的补丁准备阶段：改动在仓库外副本完成，检查期间原用户仓库只读；当时尚未合并、推送或提交赛事。交付包含源码补丁、独立证据压缩包、wheel/sdist、PDF 草稿与日志；后续代码交付状态以仓库提交记录为准。本机完整结果见 [validation.json](evidence/delivery-20261019/validation.json)，它不代表远端 CI 已运行。

## 已完成

1. 发布校验移入 scripts/verify_package.py，从源码目录生成实际模块清单，逐字节核对 wheel、sdist 和安装目录，保留许可证、元数据和入口检查；在仓库外检查 analyze、compare、compare-audit、task-check、task-improve，并实际运行静态分析。
2. 新任务评测冻结协议、模型设置、同任务同范围两组输入、必要证据及完整性摘要，人工预审前拒绝运行；指标将未知值保留为 null，服务失败不折算成实测遗漏。两个新项目、四个任务已准备，独立人工结论仍缺。
3. task-improve 绑定已有建议与调用者冻结合同，完成候选生成/回放、结构保护、隔离任务验证与补丁复查；TinyDB 录制候选经新入口通过，原合同摘要未变，没有新实时模型调用。
4. iterative 增加累计 token 停止阈值、POSIX 主线程硬时限和逐轮必要证据增益。默认策略仍为 lexical；合成测试不证明真实收益。
5. 旧对照的有效/失败记录、完整任务证据及新评测准备包持久归档；技术报告、简介和演示脚本同步当前主线。

## 实际检查

| 检查 | 本次结果 |
| --- | --- |
| python3 -m unittest discover -s tests -v | 319 项发现，293 通过、26 个沙箱测试按默认配置跳过 |
| EXAMPLEPROOF_SANDBOX_TESTS=1 python3 -m unittest discover -s tests -v | 319 项全部通过，无跳过 |
| wheel/sdist、许可证、安装与命令检查 | 29 个模块逐字节一致，pip check 通过，无 Python 运行依赖 |
| 新入口 TinyDB 工程回放 | 原版失败，修改/补丁复查通过，模型请求 0；原始输入未变 |
| 未批准任务评测的运行保护 | 返回 2，没有创建运行目录或模型请求 |
| PDF 构建 | 13 页、441391 字节，简介 249 字符，仍为草稿 |
| 证据归档 | 所有压缩包按外部逐文件 SHA 清单复核通过 |

测试包括合成模型与传输响应、真实 Bubblewrap、断言和输出保护、预算停止、阻塞调用超时、私有检查不进入模型请求、协议篡改拒绝与未知质量指标；不计作新实时模型效果。任务准备时发现一处草稿跨度超出文件末行，在模型请求和成功冻结前修正为原文件末行，未改任何原始源码或历史 evaluator。

## 持久证据索引与复核

独立交付包 archives/ 中保存以下文件及同名 `.index.json`；完整摘要索引见 [archives.json](evidence/delivery-20261019/archives.json)。它们不依赖原来的 /tmp 目录，不含模型权重，也未自动发布到外部服务。

| 压缩包 | 类型与内容 |
| --- | --- |
| tutorial-factorial-20261019.tar.gz | 既有 36 次正式请求、输入、实现、许可、助手评阅和修订 |
| flash-comparison-valid-20261019.tar.gz | 旧单项目有效三次请求 |
| flash-comparison-failed-20261019.tar.gz | 旧单项目证据定位失败的三次请求，保持失败标记 |
| tinydb-first-run-20261019.tar.gz | 既有助手候选、任务、正负控制与验证 |
| tinydb-bridge-final.tar.gz | 新 task-improve 入口的录制候选回放、完整诊断输入及固定检查 |
| task-evaluation-v1.tar.gz | 两个新项目、四个任务、源码许可及冻结实现，尚无正式模型结果 |

```sh
python3 scripts/archive_tutorial_evidence.py verify /path/to/archives/tutorial-factorial-20261019.tar.gz \
  /path/to/archives/tutorial-factorial-20261019.tar.gz.index.json
```

此复核只读压缩包，不执行或自动解压输入代码；完整性通过不证明模型结论正确、服务真实性或独立评审。原始协议中的临时路径作为历史来源保留，不是当前唯一存储位置。新任务预审模板位于交付根目录的 task-evaluation-v1-preflight-review-template.json；应由独立人工在冻结包之外填写。

## 待完成

独立人工任务预审与质量评阅、读者完成率/耗时观察、新策略真实模型对照、维护者采纳、视频录制及验收、团队权属授权、参考模板核对和报名系统提交。当前没有用户效率或泛化改善的结论。
