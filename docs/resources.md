# 开源及第三方资源使用清单

## 2026-10-25 源途 · RepoPath 品牌更新

- **品牌与界面资源：** 新的路径与节点标识、导入页学习路线图形由项目内联 SVG、HTML 与 CSS 实现，随自主代码采用 MIT。使用已有系统字体，没有新增第三方图标、图片、字体、前端库或网络资源。
- **材料图示与截图：** `docs/submission/figures/repopath-architecture.svg` 与 `repopath-workflow.svg` 为本项目自主图形源文件，对应 PNG 为其渲染产物。`repopath-home.png` 来自关闭 AI 的本机应用导入页；`repopath-workspace.png` 来自合成浏览器夹具，使用合成项目。两者均无真实模型调用，不属于独立评测或用户研究。图示与截图随自主材料采用 MIT；旧图另行保留，没有复制新的第三方图像。
- **开发验证工具：** 复用本机已有 [Playwright](https://github.com/microsoft/playwright) 1.64.1（Apache-2.0）及其缓存 Chromium 156.0.8078.4（revision 1248）完成浏览器交互检查与截图，仅用于开发，不随应用分发。构建复用已有 PyPA build 1.6.1，并在独立临时虚拟环境使用 setuptools 84.0.0（MIT，官方 PyPI wheel）；未增加应用运行依赖。
- **学习空间动效：** 使用浏览器原生 Web Animations API、CSS 与系统动效偏好，实现任务切换、工具展开和定位反馈；没有新增运行依赖或外部素材。动效预览使用合成浏览器夹具，由上述 Playwright 及其已有缓存录屏工具（FFmpeg revision 1013）生成，仅展示交互，不属于真实模型结果或读者研究；录屏工具不随应用分发。
- **运行与安装：** 分发包更名为 `aic-repopath`，新增 `repopath` 启动入口；保留内部 `exampleproof` 模块及旧命令、数据目录、配置和环境变量。没有新增 Python 运行依赖、基础模型或数据集。
- **历史材料：** 以下日期条目中的 ExampleProof、旧包名、资源来源、归属及验证记录按当时版本保留。新品牌文档不改写冻结证据、用户记录、原截图与录像，也不产生新的真实模型结果或学习效果结论。升级与品牌约定见[品牌说明](branding.md)。

## 2026-10-23 共享 AI 代理候选

- **应用与本地验证：** 共享代理、HTTPS 客户端、SQLite 用量计数和合成检查由本项目实现，使用既有 Python 标准库，不新增 Python 运行依赖、模型或数据集。继续使用已有 DeepSeek HTTP 适配；本轮不调用真实模型。
- **Caddy（可选服务器部署组件）：** 提供项目自编的反向代理配置模板，参考官方[HTTPS 反向代理指南](https://caddyserver.com/docs/quick-starts/reverse-proxy)与[请求大小限制](https://caddyserver.com/docs/caddyfile/directives/request_body)。Caddy 仅用于部署端 TLS 入口，不随 Python 包分发；本轮未安装、未在公网验证，部署者需核对目标版本与配置。不复制 Caddy 实现代码。
- **systemd（可选 Linux 服务管理）：** 提供项目自编服务单元模板，用于非 root 进程、私有状态目录和服务重启；使用服务器已有 systemd，不分发其二进制。未在本轮安装服务或修改系统配置。
- **证据边界：** 新增检查为助手编写的合成工程验证，不是独立评测。公共域名、TLS、真实计费调用和公网负载验证尚未完成，配置中的 `ai.example.org` 仅为占位地址。

## 2026-10-23 学习交付与真实读者试用材料

- **范围：** 当前报告、简介和答辩材料以学习工作台与真实读者体验为主；历史原始记录不改写。提交附件为 `docs/submission/resource-list.md`，本文件继续保留完整资源来源。
- **试用项目：** TinyDB固定提交 `edff96aeb2616402e9489d46e90a592c05565621` 和Schedule固定提交 `82a43db1b938d8fdf60103bd41f329e06c8d3651`，来源分别为 [TinyDB](https://github.com/msiemens/tinydb/tree/edff96aeb2616402e9489d46e90a592c05565621)、[Schedule](https://github.com/dbader/schedule/tree/82a43db1b938d8fdf60103bd41f329e06c8d3651)。两者MIT；桌面试用包复制官方固定提交ZIP，保留原LICENSE文件，不修改上游内容。SHA与下载地址随项目包记录。主持人参考操作仅在既有Bubblewrap执行器中运行。
- **当前演示：** 新建独立本机数据目录，使用现有DeepSeek配置生成路线与回答，通过真实HTTP接口保存笔记和运行结果，再恢复页面。画面为自动操作的实际应用截图剪辑，不作为真实读者记录；路线与回答保留本次真实调用来源。视频中的旁白由系统语音合成，不冒充成员或受访者的声音。
- **websocket-client 1.9.2：** [PyPI](https://pypi.org/project/websocket-client/1.9.2/)，Apache-2.0。仅在仓库外工具环境连接独立Microsoft Edge的本机调试端口，未加入应用依赖或随应用分发。
- **Pillow 12.2.0：** [官方许可](https://github.com/python-pillow/Pillow/blob/12.2.0/LICENSE)，本机发行包元数据为MIT-CMU，附属资源按包内声明。调用已有环境生成自编架构图和材料预览，不复制外来图像；不作为应用依赖。图中字形使用已登记Fandol字体。
- **FFmpeg 4.4：** 复用已有conda缓存 `ffmpeg-4.4.0-hca11adc_2`，构建启用GPL与version3；[FFmpeg许可说明](https://ffmpeg.org/legal.html)。仅编码自己的应用画面和配音，不分发FFmpeg二进制。既有libx264、libvpx、OpenH264与LAME仅供该工具动态链接，各按原许可保留；不复制进产品或交付包。
- **Microsoft Edge与System.Speech：** 调用本机已安装浏览器与Windows系统语音服务，采用账户/系统适用条款。配音为Microsoft Huihui Desktop zh-CN。未上传声音训练数据、未仿制真人、未使用音乐素材；不分发浏览器、语音引擎或字体文件。
- **构建工具：** 仓库外环境使用build 1.6.1、setuptools 84.2.1、wheel 0.48.0（各MIT），不改变Python运行依赖。Pandoc、XeLaTeX、Poppler、Fandol与Latin Modern继续按下方原条目使用。
- **自主部分：** 学习工作台、试用文案、记录表、架构图、演示编排与校验逻辑由团队安排、AI辅助制作。新增素材和工具的用途、原许可与自研边界分别披露；空白表和自动操作不计作受访者反馈。

## 2026-10-22 B「纸感青绿」视觉精修候选

- **设计选择：** 用户从三张视觉概念图中选择 B；概念图由内置 imagegen 生成，仅用于确定视觉方向，不是已实现页面、评测结果或产品运行素材。原图保留在仓库外，未随产品分发。
- **实现：** 使用现有 HTML/CSS/JavaScript 和系统字体，复用仓库既有自编 SVG 图标；未安装或新增前端框架、字体、图片、插件、模型运行依赖。纸面层次、留白和青绿状态用 CSS 实现。
- **调研来源：** [Impeccable](https://github.com/pbakaus/impeccable)、[UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)、[Anthropic frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)、[Vercel Web Design Guidelines](https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines)。只阅读公开说明与设计原则，没有安装或复制其代码、规则库或其他资源；默认分支未固定为依赖版本。
- **验证边界：** 在仓库外候选副本运行原有核心测试和浏览器检查；预览使用标明的合成项目与模拟模型服务，不调用真实模型、不读取或修改用户学习记录。新增视觉检查属于助手编写的工程验证，不是独立评测。隔离 runner 与既有测试断言保持不变。

## 2026-10-22 学习工作台第二版设计候选

- **范围：** 在原版学习工作台上减少重复文案，保留卡片结构，并通过纸面背景、深色项目导航、当前步骤强调和渐进展开形成层次。候选在仓库外制作，独立于未采用的第一版补丁。
- **实现与素材：** HTML/CSS/JavaScript、线条 SVG 图标和文档叠层图形均由助手直接编写；没有复制上游代码、图标、字体、图片或规则库，没有安装技能、插件、前端库或新增运行依赖。
- **既有调研参考：** 已阅读 [Impeccable](https://github.com/pbakaus/impeccable)（[Apache-2.0](https://github.com/pbakaus/impeccable/blob/main/LICENSE)）、[UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)（[MIT](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/LICENSE)）、[Primer CSS](https://github.com/primer/css)（[MIT](https://github.com/primer/css/blob/main/LICENSE)）、[Tabler](https://github.com/tabler/tabler)（[MIT](https://github.com/tabler/tabler/blob/dev/LICENSE)）、[JupyterLab](https://github.com/jupyterlab/jupyterlab)（[BSD-3-Clause](https://github.com/jupyterlab/jupyterlab/blob/main/LICENSE)）的说明与许可。它们仅用于此前的设计调研；未安装、未运行其命令、未引入其资源。默认分支内容未固定为依赖版本。
- **证据：** 原有核心测试保持不变，在独立候选副本运行。Microsoft Edge 浏览器预览使用助手编写的合成项目与模拟 API，完成状态仍表示用户自行记录；新增交互检查不是独立评测、真实模型输出或学习效果证据。未修改隔离 runner。

## 2026-10-21 工程补强新增资源

- **离线工作台：** 自编 HTML/CSS/JavaScript，默认浅色深蓝＋青绿；无第三方前端框架、图标库、外部字体、图片或运行依赖。显示公开冻结项目原文时随导出文件保留各项目许可证。工作台和测试由 Codex 辅助编写，不等于独立人工评阅。
- **Docutils 0.21.2（可选隔离渲染工具）：** [PyPI 固定版本](https://pypi.org/project/docutils/0.21.2/)，wheel SHA256 `dafca5b9e384f0e419294eb4d2ff9fa826435bf15f15b7bd45723e8ad76811b2`。仅从用户明确提供的官方 wheel 提取文本到临时隔离工作区，不在宿主安装、不随 ExampleProof wheel 分发；核心 dependencies 仍为空。大部分文件为 public domain，部分文件有 BSD/GPL 等许可例外，以 wheel 自带 `COPYING.txt` 和逐文件声明为准；渲染输出保留该许可说明。禁用文件包含和 raw 指令，未声称 Sphinx 构建支持。
- **platformdirs 4.3.8 官方构建文件：** [PyPI 4.3.8](https://pypi.org/project/platformdirs/4.3.8/)，wheel SHA256 `ff7059bb7eb1179e2685604f4aaf157cfd9535242bd23742eadc3c13542139b4`。工程案例核对 7 个已有 Python 模块与固定源码快照字节一致，仅在新的临时案例副本补入 wheel 的 `src/platformdirs/version.py`；不改变旧冻结输入、不伪造构建文件、不执行安装脚本。源码及构建文件遵守上游 MIT，原许可证随案例保留。
- **2026-10-21 实时工程调用：** `deepseek-flash` 对 TinyDB 和 platformdirs 两个公开固定输入完成 6 次分析和 2 次候选生成，服务端实际 token 合计 42,790。两项候选均通过预先冻结的有限任务与补丁复查；不是独立质量评测、读者实验或赛事结果。直接模型与 lexical 最终用户输入逐字节一致，提示词不同；仅文档组实际输入不同。完整错误主张和失败前置探测均保留。两项任务合同由助手预先编写，不冒充独立评阅。此次数据仍属于开发工程样例。
- **四任务正式基线：** 在用户逐项预审后沿用旧冻结实现完成 8 次真实分析，实际 token 共 38,105；用户随后逐条核对并确认 38 条质评。首批网络沙箱失败尝试单独保留，未知用量不填零。没有真实读者实验。
- **隔离打包工具：** 本轮仅在外部 `/tmp` 虚拟环境使用 setuptools 80.9.0、wheel 0.45.1、build 1.2.2.post1、packaging 25.0、pyproject-hooks 1.2.0、tomli 2.2.1；均来自固定 PyPI wheel，用于构建/检查，不随产品分发，不加入运行依赖。既有构建工具资源说明继续适用。
- **浏览器验证：** 调用本机 Microsoft Edge 检查离线页面的桌面和手机宽度，不分发浏览器，不引入浏览器自动化运行依赖。

记录日期：2026-10-13。本清单作为技术报告附件；“已核对”仅表示查阅了所列来源或本机记录，不代替团队权属、服务条款及最终发布审核。版本按实测环境或配置分别标记，未知项不写成已确认。本仓库应用代码为MIT，第三方资源仍遵守各自许可。

## 2026-10-19 下一阶段新增服务与实现资源

- **DeepSeek API（可选云端模型服务）：** 使用官方 [Chat Completions](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/) 和 [JSON Output](https://api-docs.deepseek.com/zh-cn/guides/json_mode/) 文档设计 HTTP 协议适配。默认模型标识 `deepseek-flash`，可配置；模型权重不下载或分发。调用需用户自行配置密钥并遵守服务条款，费用按供应商实际用量计算，不声称永久免费或固定价格。首版只验证模拟响应契约；后续按用户指定使用 Flash 完成 6 次实时请求，其中 3 次属于证据定位错误的开发运行，3 次为修正后的探索性对照，分开保存。未报告独立准确率或学习效率收益。服务文档仅作为接口参考，未复制 SDK 或文档正文；不增加第三方 Python 依赖。详见 [Flash 对照记录](flash-comparison.md)。
- **GitHub REST API 与源码 ZIP（可选远端输入）：** 根据官方[提交查询接口](https://docs.github.com/en/rest/commits/commits#get-a-commit)解析 ref，再通过 `codeload.github.com` 获取固定 commit 的公开仓库快照。归档保存在临时目录，仅读取合格文本，不执行、不安装、不在 ExampleProof 包中再分发下载的项目。使用者仍须遵守被分析项目许可及 API 使用限制；报告包含的原文摘录也受上游许可约束。Python 标准库负责 HTTPS、ZIP、JSON 和路径校验，无新增 SDK。
- **真实输入链路 smoke：** 公开 TinyDB 仓库 `msiemens/tinydb`，实际固定到 `edff96aeb2616402e9489d46e90a592c05565621`；28 个文件、259 个片段完成静态索引，模型请求为 0。它只验证项目输入与报告链路，零发现不代表教程无问题，不是质量评测、模型实测或参赛评测结果。该项目的历史兼容性夹具与此当前快照分别统计；上游 TinyDB 的许可义务继续适用。快照处理结束即清理，smoke 报告保存在本次临时审阅产物中。
- **实现与合成测试：** 本轮新增代码、中文文档和接口夹具由 Codex 辅助编写。模型接口及失败场景测试全部使用明确标注的合成响应，不将它们视为 DeepSeek/Ollama 实时推理或独立教程质量证据。原有 Ollama、CPython 与 Bubblewrap 资源条目继续适用，安装包运行依赖仍为零。
- **后续冻结输入与实现归档：** Flash 对照继续使用上述 TinyDB 同一 commit，新增无扩展名许可等发现规则后索引 30 个文件、261 个片段，输入快照保存在临时审阅产物中并保留许可。该提交的 TinyDB 资源仍按上游 MIT 许可使用，不改标为 ExampleProof 自主代码。对照协议归档 ExampleProof 实现及其已有许可材料，不增加新的外部模型、数据集、SDK 或运行依赖。中文标题的字对分词、文字补丁完整性检查和快照审计均用标准库实现。

## 核心运行资源

### 1. Python / CPython标准库（软件、运行时）

- **版本/来源：** 实测Python 3.10.12；[CPython v3.10.12](https://github.com/python/cpython/tree/v3.10.12)，[该版本许可](https://github.com/python/cpython/blob/v3.10.12/LICENSE)。声明支持Python 3.10+，不等于所有环境均已实测。
- **许可/关键义务：** PSF License Agreement与所包含的历史许可；再分发保留适用版权、许可和免责说明，修改版按条款记录变更，不借原作者名义背书。
- **使用方式/自主边界：** 解释器及标准库支持解析、沙箱调度、HTTP客户端、报告及测试。没有修改或复制解释器实现；工具模块在本仓库开发，包含AI辅助内容。
- **合规状态/开放方式：** 已查上游版本许可；调用本机解释器，不随仓库分发Python。历史兼容性知识见官方说明，案例来源另列。

### 2. Bubblewrap（隔离执行工具）

- **版本/来源：** 实测0.6.1；[版本源码](https://github.com/containers/bubblewrap/tree/v0.6.1)，[入口许可声明](https://github.com/containers/bubblewrap/blob/v0.6.1/bubblewrap.c)，[COPYING](https://github.com/containers/bubblewrap/blob/v0.6.1/COPYING)。
- **许可/关键义务：** LGPL-2.0-or-later；再分发其二进制或修改版时，按许可提供对应源码及版权/许可说明，不以本仓库MIT覆盖上游许可。
- **使用方式/自主边界：** 作为独立进程调用，负责命名空间与只读挂载。命令组织、资源限制及状态判断由本仓库实现，没有修改Bubblewrap。
- **合规状态/开放方式：** 已核对版本与许可；调用系统安装版本，不打包其二进制。不能创建隔离环境时停止执行。

### 3. Ollama（本地模型服务）

- **版本/来源：** 实测0.40.3；[官方发行版](https://github.com/ollama/ollama/releases/tag/v0.40.3)，[该版本MIT许可](https://github.com/ollama/ollama/blob/v0.40.3/LICENSE)，[generate接口](https://docs.ollama.com/api/generate)。安装包摘要见 `docs/evidence/ollama-20261013/environment.json`。
- **许可/关键义务：** Ollama本体MIT；复制或再分发上游内容须保留版权和许可。模型及捆绑组件分别遵守对应许可，软件许可不能替代模型许可。
- **使用方式/自主边界：** 本机模型推理服务；本仓库实现回环HTTP适配、解析、反馈和取证，没有修改Ollama。
- **合规状态/开放方式：** 已核验发行包摘要并保存实际版本；安装包保存在仓库外，本工具不自动下载或再分发。

### 4. Qwen2.5-Coder-7B-Instruct（模型权重）

- **版本/来源：** Ollama `qwen2.5-coder:7b`，7.6B、Q4_K_M；[模型标签](https://ollama.com/library/qwen2.5-coder:7b)，[原模型](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct)，[Apache-2.0许可](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct/blob/main/LICENSE)。实测manifest SHA-256：`dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364`。同名tag可能变化，摘要固定本次对象。
- **许可/关键义务：** Apache-2.0；再分发附许可，保留适用版权、归属与NOTICE（如有），标记修改，不授予商标使用权。输出仍须核查来源和权利。
- **使用方式/自主边界：** 生成真实修复候选；没有训练、微调、改写权重或自主量化。提示词和验证流程在仓库开发，不把基础模型归为团队成果。
- **合规状态/开放方式：** 已核对原模型许可并校验manifest及文件摘要；约4.7GB权重不随仓库分发。请求、响应与补丁可包含自编案例及下列许可允许复制的上游源码/文档；上游内容继续保留原许可与归属。生成候选的团队权利审核待完成。

## 数据、案例与调研材料

### 5. 历史兼容性事实、自制SDK和候选（案例素材）

- **版本/来源：** `examples/tutorial/`、`benchmarks/compatibility/`，精确来源见各自案例说明及兼容性集 `metadata.json`。Python 3.8/3.9/3.10官方版本说明提供历史变更事实，如 [Python 3.10移除项](https://docs.python.org/3.10/whatsnew/3.10.html#removed)；当前重现环境Python 3.10.12。
- **许可/关键义务：** 自编最小重现、自制SDK及检查按仓库MIT开放；[Python官方文档许可](https://docs.python.org/3/license.html)为PSF License Version 2，文档代码示例另有0BSD双重许可。这里仅摘要事实并链接来源，未复制上游实现或教程代码，不将官方文档改标MIT；来源链接不等于任意复制授权。
- **使用方式/自主边界：** 原教程为一个历史重现、两个自制SDK失败及三个对照；兼容性集为六个历史CPython API变更的自编重现和两个正常对照，另有四个错误改法用于检查误修复。候选JSON为AI辅助编写并保存的回放数据，不是实时推理，不是六个真实项目缺陷。
- **合规状态/开放方式：** 已记录来源类型；示例、配置、回放候选及真实推理报告随仓库开放。加入第三方代码前须逐案核对版本及许可；生成内容的团队权利复核待完成。

### 6. Sybil、Drift（相关工作调研）

- **版本/来源：** 2026-10-13查阅 [Sybil 10.1.0文档](https://sybil.readthedocs.io/en/latest/)及[许可](https://sybil.readthedocs.io/en/latest/license.html)；[Drift仓库](https://github.com/pallaprolus/drift)及[许可](https://github.com/pallaprolus/drift/blob/main/LICENSE)，Drift未安装、未固定版本。
- **许可/关键义务：** 所查两者均MIT；如后续复制实现，须保留版权与许可。当前仅摘要介绍能力并引用来源，无性能比较结论。
- **使用方式/自主边界：** 用于定位相关工作；未作为依赖，未复制其实现、图片或文档段落。
- **合规状态/开放方式：** 已核对所查页面许可；仅保留来源链接与自行撰写的说明，不打包上游内容。

## 开发、构建与协作工具

### 7. setuptools（可选包构建）

- **版本/来源：** 声明 `setuptools>=61`，既有隔离打包实测84.0.0；[该版本MIT许可](https://github.com/pypa/setuptools/blob/v84.0.0/LICENSE)。
- **许可/关键义务：** MIT；复制分发须保留版权和许可；工具捆绑依赖按其各自许可。
- **使用方式/自主边界：** 隔离构建wheel，没有修改setuptools；CLI可直接运行，无第三方Python运行依赖。
- **合规状态/开放方式：** 既有安装验证见 `docs/validation.md`；仓库仅提供构建配置，不分发构建工具。

### 8. GitHub Actions官方组件（CI组件）

- **版本/来源：** 工作流声明 `actions/checkout@v7`、`actions/setup-python@v7`；核对 [checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1)及[MIT许可](https://github.com/actions/checkout/blob/v7.0.1/LICENSE)、[setup-python v7.0.0](https://github.com/actions/setup-python/releases/tag/v7.0.0)及[MIT许可](https://github.com/actions/setup-python/blob/v7.0.0/LICENSE)。主版本tag可移动，实际解析commit以每次CI日志为准。
- **许可/关键义务：** 两组件MIT；复制分发须保留版权和许可；托管CI另遵守GitHub服务条款。
- **使用方式/自主边界：** 仅检出和Python环境准备；测试及工作流由本仓库组织，未修改官方组件。
- **合规状态/开放方式：** 已核对声明版本和许可；公开工作流，不复制组件代码。后续CI结果以对应commit的运行记录为准。

### 9. GitHub（第三方托管与CI服务）

- **版本/来源：** 在线服务，无固定本地版本，2026-10-13使用；[GitHub服务条款](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service)。
- **授权/关键限制：** 按适用账户条款使用，上传者须具有上传和授权展示内容所需权利；公开可访问不自动等于可任意复制。
- **使用方式/自主边界：** 托管代码、工作流和证据；平台能力不计入自主实现。
- **合规状态/开放方式：** 已记录公开仓库地址；账户适用条款与共同权利确认待团队审核，不公开访问凭据。

### 10. 对话式生成式AI辅助工具（第三方开发服务）

- **版本/来源：** 对话式AI辅助本项目开发，本轮工具界面为Codex。具体后端模型标识、账号适用服务与使用档案未由团队完整提供，**待补**；由账户主体从 [OpenAI政策索引](https://openai.com/policies/)核对对应协议。
- **授权/关键限制：** 属服务授权，不是开源资源；确认输入权利，审核输出来源、准确性与适用条款。AI生成内容不当然构成团队独占知识产权。
- **使用方式/自主边界：** 辅助选题、规则、架构、代码、测试、提示词和文档；与作品运行阶段的本地Qwen推理分开披露。AI参与不替代真实团队投入与审核说明。
- **合规状态/开放方式：** 已披露用途；人工审核、修改记录及授权档案尚未确认。仅公开有权公开并经审核的成果，不公开账号或完整私人对话。

### 11. Pandoc、XeLaTeX / TeX Live（报告构建工具）

- **版本/来源：** 本机Pandoc 2.9.2.1、XeTeX 0.999993（TeX Live 2022/dev/Debian）；[Pandoc许可](https://github.com/jgm/pandoc/blob/2.9.2.1/COPYING.md)，[XeTeX许可](https://github.com/TeX-Live/xetex/blob/master/source/texk/web2c/xetexdir/COPYING)，[CTeX](https://ctan.org/pkg/ctex)。准确工具输出见构建清单。
- **许可/关键义务：** Pandoc GPL-2.0-or-later；XeTeX增补部分MIT，TeX Live组件按各自许可（含LPPL等）。再分发时保留适用许可并履行源码义务，不能将整个工具链统称MIT。
- **使用方式/自主边界：** 将Markdown排版为PDF；正文和构建脚本在本仓库维护，没有修改上游排版软件，作品运行不依赖这些工具。
- **合规状态/开放方式：** 调用已有系统工具，未额外安装；不分发其程序。系统包许可汇总见本机 `texlive-xetex` 文档。

### 12. Fandol、Latin Modern（PDF字体）

- **版本/来源：** 本机Fandol 0.3；[CTAN Fandol](https://ctan.org/pkg/fandol)及发行包README/COPYING。Latin Modern系统包 `fonts-lmodern 2.004.5-6.1`；[CTAN Latin Modern](https://ctan.org/pkg/lm)。实际嵌入字体可用 `pdffonts`核查。
- **许可/关键义务：** Fandol发行包为GPL-3.0加字体嵌入例外，嵌入未改字形不单独使文档适用GPL；Latin Modern为GUST Font License。修改或另行分发字体文件须遵守原许可及命名要求。
- **使用方式/自主边界：** 中文及拉丁文字排版，由排版器嵌入所用字形子集；未设计或修改字形。
- **合规状态/开放方式：** 已核对本机发行包许可；仓库保存文档与构建脚本，PDF包含字形子集，不另发完整字体文件。未用外部图片、音频、模板素材或数据集。

### 13. Git、curl、Poppler（版本、下载与PDF核查工具）

- **版本/来源：** 本机Git 2.34.1、curl 7.81.0、Poppler `pdfinfo/pdftotext` 22.02.0；[Git许可](https://github.com/git/git/blob/v2.34.1/COPYING)、[curl许可](https://github.com/curl/curl/blob/curl-7_81_0/COPYING)、[Poppler许可](https://gitlab.freedesktop.org/poppler/poppler/-/blob/poppler-22.02.0/COPYING)。
- **许可/关键义务：** Git GPL-2.0、curl专用宽松许可；本机Poppler发行包标注GPL-2或GPL-3，另含按各自许可发布的组件，已核对本机 `poppler-utils` 版权清单。分发程序时须履行对应版权、许可和源码义务。
- **使用方式/自主边界：** 仓库管理、下载官方资源、补丁检查、PDF页数/文本/体积核查；未修改工具，其实现不计入自主成果。
- **合规状态/开放方式：** 仅调用系统工具，不分发二进制。主机内核、驱动及硬件另作为环境信息记录，不主张为项目成果。

## 新增真实项目文档与源码快照

本组位于 `benchmarks/real_projects/`，共三个项目、五个版本迁移失败和三个健康对照。原始文档取自上游历史版本，运行实现固定到声明的新版本；失败不等于当前上游文档有缺陷。只做提示符去除、文档片段拼接、表达式显示包装和源码路径映射，原始输入值及 API 调用不改坏，库实现不改写。逐文件版本、提交、URL、SHA-256、逐例文档行号和转换步骤保存在各项目 `provenance.json`。

### 14. TinyDB（官方文档、实现与版本迁移案例）

- **版本/来源：** 文档及旧版正控制为 [v3.15.2 / `5e781305`](https://github.com/msiemens/tinydb/tree/5e7813053f721ab37acd4ed1e50b41009886f5b2)，运行目标为 [v4.8.2 / `10644a0e`](https://github.com/msiemens/tinydb/tree/10644a0e07ad180c5b756aba272ee6b0dbd12df8)。案例来自 `docs/getting-started.rst`、`docs/usage.rst`；[来源清单](../benchmarks/real_projects/tinydb/provenance.json)含精确行号。
- **许可/关键义务：** 两版均为 MIT，版权归 Markus Siemens 等上游权利人；复制及再分发须保留原版权、许可和免责文本。已保存 [3.15.2 许可](../benchmarks/real_projects/tinydb/upstream/v3.15.2/LICENSE)与 [4.8.2 许可](../benchmarks/real_projects/tinydb/upstream/v4.8.2/LICENSE)，可对照[目标提交的上游许可](https://github.com/msiemens/tinydb/blob/10644a0e07ad180c5b756aba272ee6b0dbd12df8/LICENSE)。相同的 MIT 名称不代表复制代码属于本作品自主实现。
- **使用方式/自主边界：** 两个清空/删除表 API 迁移及一个查询对照。运行源码逐字节保存，没有修改库实现；不复制依赖 mypy 的可选静态分析插件。原始文档命令只去提示符并拼接初始化片段。独立 archive 表、外部检查及参考候选由本仓库构造，并与上游原文分开披露。两版运行都通过 Bubblewrap，不在宿主解释器导入下载代码。
- **开放及再分发范围：** 仓库包含选定源码、相关原始文档、两版许可证、机械提取案例、配置、参考补丁及复验报告。对应模型证据中的上游文本也须连同来源和许可保留；不把整个上游仓库、其生态依赖或维护者反馈计为本作品成果。

### 15. more-itertools（官方 docstring、实现与版本迁移案例）

- **版本/来源：** 文档为 [5.0.0 / `53c2c692`](https://github.com/more-itertools/more-itertools/tree/53c2c692d3175e4487235213465afb14a211ec3c)，运行目标为 [9.0.0 / `ffcfe0b4`](https://github.com/more-itertools/more-itertools/tree/ffcfe0b4e63c75fe1470b8b25a29b0e698a9a587)。`docs/api.rst` 通过 Sphinx 展示 `more.py`、`recipes.py` 中的函数文档；[来源清单](../benchmarks/real_projects/more_itertools/provenance.json)保留原始位置与输出。
- **许可/关键义务：** 上游整体声明 MIT，版权说明为 Erik Rose；保留 [5.0.0 许可](../benchmarks/real_projects/more_itertools/upstream/5.0.0/LICENSE)、[9.0.0 许可](../benchmarks/real_projects/more_itertools/upstream/9.0.0/LICENSE)及[固定提交的许可](https://github.com/more-itertools/more-itertools/blob/ffcfe0b4e63c75fe1470b8b25a29b0e698a9a587/LICENSE)。`recipes.py` 明确注明来源于 Python `itertools` 文档，本仓库原样保留该归属，不能将其中 Python 派生内容只归给 more-itertools 或本作品。[Python 文档许可](https://docs.python.org/3/license.html)包含 PSF License Version 2，并说明文档代码自 Python 3.8.6 起另有 0BSD 双重许可；上游未固定每条历史 recipe 的 CPython 来源版本，因此不据此推断 5.0.0 的全部历史片段自动适用后来的双重许可。已另归档 [CPython 3.7.0 完整许可与历史版权说明](../benchmarks/real_projects/more_itertools/upstream/cpython-3.7.0/LICENSE)和 [recipes 来源说明](../benchmarks/real_projects/more_itertools/upstream/PYTHON-RECIPES-NOTICE.md)，用于保留原始许可与归属，不将 3.7.0 声称为每条 recipe 的精确来源。再分发时这些说明也须保留。
- **使用方式/自主边界：** `collate` 移除、`grouper` 参数顺序迁移和 `chunked` 健康对照。三个目标 `.py` 文件完整复制、字节不变，合计 156,459 字节；不安装上游发行包。原始 doctest 去提示符，补模块导入并给列表表达式添加 `print(...)`，原始值与期望结果保存不变。额外行为检查和参考候选由本仓库编写。旧版正控制另给沙箱提供下列固定版本的 `six.py`，不增加作品的运行依赖。
- **开放及再分发范围：** 选定两版源码/文档、原始片段、许可证、案例配置及复验报告随仓库保存；Python recipes 原归属也随源码保留。目标 9.0.0 及旧版 5.0.0 + six 1.16.0 均只在隔离环境运行；同样的三个原始示例和检查在旧版全部通过，见[正控制记录](../benchmarks/real_projects/more_itertools/evidence/old-version-control/validation.json)。复制实现与转换后的上游示例继续按适用上游许可处理，不统标为本仓库 MIT。

### 16. MarkupSafe（官方 API 文档、实现与版本迁移案例）

- **版本/来源：** 文档及旧版正控制为 [1.1.1 / `22c946de`](https://github.com/pallets/markupsafe/tree/22c946de28c2f5916f8c88a983a3e48e1cdbd2fd)，运行目标为 [2.1.5 / `fbba4acd`](https://github.com/pallets/markupsafe/tree/fbba4acd0312826cec9cfe18371c7df07962cb65)。`docs/escaping.rst` 通过 autodoc 引入 `_native.py` 的函数文档；[来源清单](../benchmarks/real_projects/markupsafe/provenance.json)记录对应 docstring 行号及原始片段。
- **许可/关键义务：** 两版均为 **BSD-3-Clause**，版权为 Pallets。保存 [1.1.1 许可](../benchmarks/real_projects/markupsafe/upstream/1.1.1/LICENSE.rst)、[2.1.5 许可](../benchmarks/real_projects/markupsafe/upstream/2.1.5/LICENSE.rst)及[固定提交的上游许可](https://github.com/pallets/markupsafe/blob/fbba4acd0312826cec9cfe18371c7df07962cb65/LICENSE.rst)。源码再分发保留版权、条款和免责；二进制再分发在随附文档保留这些内容；未经许可不得借版权人或贡献者名称作背书。本仓库 MIT 不覆盖这些文件。
- **使用方式/自主边界：** `soft_unicode` 移除的字符串转换示例及 `escape_silent` 健康对照。仅去除 docstring 提示符并给输出表达式添加 `print(repr(...))`，setup 提供文档模块作用域。运行实现只映射 `src/` 路径前缀，内容逐字节不变；使用官方纯 Python fallback，不编译或分发 C 扩展。旧版两个原始示例通过；新版原始示例一失败、一通过，参考修复后两个均通过，均有隔离执行记录。
- **开放及再分发范围：** 保存选定源码、原始 docstring、API 文档入口、变更记录、两版许可证、转换案例及参考复验报告。生成报告、请求与补丁中包含的相同上游内容仍保留 BSD-3-Clause 归属；外部检查、提取校验脚本及执行组织属于本仓库开发范围。

### 17. six（仅用于旧版本正控制的兼容模块）

- **版本/来源：** six **1.16.0**，固定提交 [`65486e4383f9f411da95937451205d3c7b61b9e1`](https://github.com/benjaminp/six/tree/65486e4383f9f411da95937451205d3c7b61b9e1)。[源码副本](../benchmarks/real_projects/more_itertools/upstream/six-1.16.0/six.py)和摘要保存在 more-itertools 的来源清单；`six.py` SHA-256 为 `4ce39f422ee71467ccac8bed76beb05f8c321c7f0ceda9279ae2dfa3670106b3`。
- **许可/关键义务：** MIT，版权为 Benjamin Peterson；复制或再分发保留上游版权、许可与免责。已保存[原始许可证](../benchmarks/real_projects/more_itertools/upstream/six-1.16.0/LICENSE)，对应[固定提交的上游许可](https://github.com/benjaminp/six/blob/65486e4383f9f411da95937451205d3c7b61b9e1/LICENSE)。
- **使用方式/自主边界：** 仅满足 more-itertools 5.0.0 旧版正控制的兼容依赖，字节不变地映射为沙箱中的 `six.py`。不在宿主安装或导入，不提供给 9.0.0 目标案例或实时修复模型，不属于本作品实现。
- **开放及再分发范围：** 归档原始单文件源码、许可证及旧版控制的输入快照，以便复现 3/3 `checked` 记录；其存在不表示作品运行依赖 six，也不表示重建了 more-itertools 5.0.0 发布时的完整系统环境。

### 18. CPython 3.10.12 标准库 API 检索语料

- **版本/来源：** [CPython v3.10.12 官方源码](https://github.com/python/cpython/tree/v3.10.12/Lib)，固定发行归档 SHA-256 为 `5bcecf44fb27cda3efb0426a1b464d1925d0e7bfb1e423aaa301e5294db1fcef`。按统一规则选择全部 153 个公开平面 `Lib/*.py` 模块，AST 提取 999 个顶层公开函数的签名和 docstring；不含私有模块、类、子包或 C 内置实现。[原始语料及逐文件摘要](../benchmarks/semantic_v2/resources/cpython-3.10.12/provenance.json) 与 [生成器](../scripts/build_stdlib_index.py) 随仓库保存。
- **许可/关键义务：** [完整 CPython LICENSE](../benchmarks/semantic_v2/resources/cpython-3.10.12/LICENSE)，包括 PSF License Agreement 和历史许可；另保留源码局部版权及附加许可通知。再分发须保留适用版权、许可、免责及变更说明，不把 Python 示例文档的 0BSD 双许可推及所有源码。完整许可和收集到的模块通知也嵌入安装包的 `stdlib_index.py`。逐个检查全部 153 个模块后，另随 wheel/sdist 分发 [Apache-2.0 完整正文](../exampleproof/licenses/Apache-2.0.txt)，对应 `profile.py`、`pstats.py` 的 Disney Enterprises 声明；[独立归属补充](../exampleproof/licenses/stdlib-attribution.txt)保留各模块原始通知并补齐 doctest、inspect、tabnanny 和 socket 辅助函数的 public-domain/no-warranty 声明，附完整 153 文件摘要清单。包内还提供可单独阅读的 [CPython 完整许可副本](../exampleproof/licenses/CPython-3.10.12.txt)。这是分发许可补充，未修改冻结的方法、索引或实验。
- **使用方式/自主边界：** 官方源码按统一规则机械抽取，未修改原文行片段；静态语料用于缺失导入时的候选 API 检索，不执行索引中的代码，不携带案例参考修复或外部检查。生成、触发、排名与预算控制在本仓库实现。只使用原有解释器执行修复候选，没有新增 Python 运行依赖。
- **开放及再分发范围：** 原始公开平面模块以压缩 JSON 归档；完整候选索引、出处摘要和许可随源码、wheel/sdist 及实验实现快照保存。新方法包含新增标准库信息，应作为完整方法升级解释，不能归因为执行反馈单项收益。固定官方版本与本机发行版解释器版本号对应，不声称两者全部实现字节一致。

以上复制资源、其机械派生案例，以及含相同文本的 `inputs/` 和报告不能仅依赖仓库根目录 MIT 进行统一授权；公开或导出证据时应保留对应项目的 `provenance.json`、原始许可证及本清单。参考 `proposals.json` 属工程回放资料，不是模型输出成绩；真实模型请求须排除这些参考答案和外部 oracle。

## AI参与和审核记录

2026-10-13：AI辅助选题、规则解读、代码与测试、文档及回放候选；后续辅助多轮修复、证据保存、执行完整性与提示词优化。本轮另辅助自动benchmark流程、兼容性案例、误修复对照和参赛材料/PDF构建，随后采集三个真实上游项目的历史文档、核对许可、机械提取版本迁移案例并完成冻结对照。27 个实验单元、92 次真实请求及失败记录见 [实测证据](evidence/real-projects-20261013/README.md)。提交和证据说明实际变化，自动测试不能替代团队人工审核。

`proposals.json`与`proposals.multiround.json`是已保存候选；后者有刻意失败的第一轮，只验证下一轮流程，不产生模型调用。真实Ollama调用保存在 `docs/evidence/ollama-20261013/` 和 `docs/evidence/compatibility-20261013/`，包含放弃与检查失败，候选未人工改写。

两组既有真实提示词优化均在观察对应开发样例基线后进行：原教程三例第一轮通过；新增兼容性集优化后六个失败中四例通过补丁复查，其中计时例实际经历三轮。后者提示词及实际调用预算同时变化，不能独立证明多轮增益，也不代表未见项目成功率。新增三个上游项目案例未参与此前提示词优化，其参考复验不是实时模型评测；冻结后的固定预算对照应以另行保存的协议、请求和完整结果为准。“未见”只指本项目开发过程中的留出，不能断言公开文档从未进入基础模型训练集。尚无维护者或真实用户反馈可供引用。

**提交前待补：** 团队确认实际AI服务和模型档案，审核生成内容来源/权利，记录人工修改及验证，确认共同权利人的参赛和公开授权，检查最终版本的新增资源已全部列入。不得将“待审核”改写为“团队已审核”。

## semantic_v2 新增独立留出资源

以下资源位于 `benchmarks/semantic_v2/holdout/`。两个新项目提供四个历史迁移失败和两个健康对照，原文、库实现与各自许可证按原字节保留；[独立封存清单](../benchmarks/semantic_v2/holdout/input-inventory.json)记录 266 个输入文件，SHA-256 为 `48557123a7453b5e8a899f7531e3b4cc4773ce1e158136ba0aa974cbe6d485ac`。这组素材不是当前上游缺陷报告，也不是随机抽样；参考候选和负例仅用于验证检查器，不作为模型效果。

### 19. Mistune（官方 README、实现与版本迁移留出）

- **版本/来源：** 文档及旧版正控制为 [0.8.4 / `6470c42b`](https://github.com/lepture/mistune/tree/6470c42b2087a4649ad0437227cf7b5c570c3a91)，运行目标为 [3.1.3 / `45e4de61`](https://github.com/lepture/mistune/tree/45e4de61b8897fe5b0458d5ebe3d3cc7bde408d2)。官方 `docs/index.rst` 包含 README；三个片段精确位置为 README.rst 70–73、87–90、61–64 行。[来源清单](../benchmarks/semantic_v2/holdout/mistune/provenance.json)保留完整 commit、URL、原始文件及片段 SHA。
- **许可/关键义务：** 两版 BSD-3-Clause，原版权及条款分别保存在 [0.8.4 LICENSE](../benchmarks/semantic_v2/holdout/mistune/upstream/0.8.4/LICENSE)、[3.1.3 LICENSE](../benchmarks/semantic_v2/holdout/mistune/upstream/3.1.3/LICENSE)。再分发保留版权、许可和免责；不借作者名称作背书，不将上游实现归为本仓库 MIT 自主代码。
- **使用方式/自主边界：** 复用 HTML 渲染器的返回类型变化、Renderer 接口与选项迁移，以及 convenience function 健康对照。只剥离 RST 缩进，保留语句、注释和静默表达式；原文 `text` 占位参数的 setup 明确披露。多输入、空输入、类型、HTML 转义、软／硬换行及重复调用检查为本仓库编写。运行时的 typing_extensions 另列下项，未改上游源码或在宿主安装上游包。
- **开放及再分发范围：** 旧／新源码、README、Sphinx 入口、许可证、机械提取记录、配置、参考候选及失败证据随仓库保存。相同外部检查在旧版 3/3 通过，目标两失败一健康；人工参考补丁应用后 3/3 通过，两个错误候选均拒绝。[控制证据](../benchmarks/semantic_v2/holdout/validation-final/mistune/validation.json)全部经 Bubblewrap 执行，不产生模型请求。该验证不证明任意 Markdown 的语义等价。

### 20. Werkzeug（官方 docstring、实现与版本迁移留出）

- **版本/来源：** 文档及旧版正控制为 [2.2.3 / `22a254fc`](https://github.com/pallets/werkzeug/tree/22a254fca2ad0130adbbcbd11d3de51bcb04a08b)，运行目标为 [3.0.6 / `5eaefc39`](https://github.com/pallets/werkzeug/tree/5eaefc3996aa5cc8c5237d8b82f1b89eed6ea624)。官方 `docs/wsgi.rst`、`docs/urls.rst` 发布选定的函数 docstring；[来源清单](../benchmarks/semantic_v2/holdout/werkzeug/provenance.json)给出精确行号、URL、commit 与原始字节 SHA。
- **许可/关键义务：** 两版 BSD-3-Clause，原 [2.2.3 许可](../benchmarks/semantic_v2/holdout/werkzeug/upstream/2.2.3/LICENSE.rst)、[3.0.6 许可](../benchmarks/semantic_v2/holdout/werkzeug/upstream/3.0.6/LICENSE.txt)及源码局部声明随归档保留。复制分发保留版权、条款和免责，不借 Pallets 或贡献者名称背书。Markupsafe 依赖沿用第 16 项固定 2.1.5 commit，原生 Python 回退实现及完整许可另随本项目归档，不计作新的 MarkupSafe 迁移案例。
- **使用方式/自主边界：** `pop_path_info`、`peek_path_info` 移除及 `iri_to_uri` 健康对照。仅去 doctest 提示符、补文档模块显式导入，并以 `print(repr(...))` 保留 REPL 输出。外部检查覆盖可调用名称复用、环境字典副作用、空／缺失路径、重复斜线、无关字段、Unicode／WSGI 字节和 `charset=None`。固定旧版实现的空路径行为与 docstring 概述存在差别，已在上下文和案例 README 显式说明，没有静默改变契约。
- **开放及再分发范围：** 两版纯 Python 源码、原始 docstring、Sphinx 入口、原许可证、案例和参考证据随仓库保留；所有上游执行仅在沙箱内完成。相同检查旧版 3/3 通过；目标两失败一健康，参考补丁复查 3/3，两个错误候选均拒绝。[运行证据](../benchmarks/semantic_v2/holdout/validation-final/werkzeug/validation.json)为人工候选回放，不是模型实测。导出的补丁用于规范化 Markdown 副本，不等同于上游 PR。

### 21. typing_extensions（仅用于固定隔离运行依赖）

- **版本/来源：** [4.12.2 / `e1250ff8`](https://github.com/python/typing_extensions/tree/e1250ff869e7ee5ad05170d8a4b65469f13801c3)，[原始单文件](../benchmarks/semantic_v2/holdout/mistune/upstream/dependencies/typing_extensions-4.12.2/src/typing_extensions.py) SHA 在 Mistune 来源清单中。
- **许可/关键义务：** PSF-2.0 及 [完整 LICENSE 中的历史许可说明](../benchmarks/semantic_v2/holdout/mistune/upstream/dependencies/typing_extensions-4.12.2/LICENSE)，再分发保留适用版权、许可和免责；不改标为本仓库 MIT。
- **使用方式/自主边界：** 满足 Mistune 3.1.3 在 Python 3.10 上的 `Self` 类型依赖，旧、新版本使用同一固定源文件，运行字节不变。仅放入沙箱选定源码，不安装到宿主，不增加 ExampleProof 安装包运行依赖；来源和许可随原始输入及验证快照保留。

### 22. Click（仅用于采样与排除记录）

- **版本/来源：** [7.1.2 / `1784558e`](https://github.com/pallets/click/tree/1784558ed7c75c65764d2a434bd9cbb206ca939d) 与 [8.1.8 / `934813e4`](https://github.com/pallets/click/tree/934813e4d421071a1b3db3973c02fe2721359a6e)。`collection/click/` 保留所查 API、补全和回调文档、utils/termui 源码与两个 commit 文件。
- **许可/关键义务：** BSD-3-Clause，所查版本原始许可证分别保存在 [7.1.2 LICENSE.rst](../benchmarks/semantic_v2/holdout/collection/click/7.1.2/LICENSE.rst) 与 [8.1.8 LICENSE.txt](../benchmarks/semantic_v2/holdout/collection/click/8.1.8/LICENSE.txt)。复制的调研材料仍须保留上游版权、许可和免责。
- **使用方式/自主边界：** 适合的完整官方示例需要 decorator 或函数定义，超出现有直线修复范围，故在模型调用前排除；没有人为改坏或重写成自编片段。未用于模型输入，不计入案例分母，不导入或执行这些归档文件；[采样记录](../benchmarks/semantic_v2/holdout/sampling-record.json)同时说明只做公开搜索而未复制源码的其他候选项目。

### 本轮 AI 参与与留出边界补充

AI 独立采集者完成上述两个新项目的来源采集、机械提取、外部契约、旧版正控制、参考候选及错误候选。准备阶段的依赖缺失和换行格式预期错误均保留，并在首次模型调用前根据固定旧版本验证结果纠正；没有根据留出模型输出更换题目、改检查或补答案。

采集者先选定项目与四个题目，随后为查看既有 FileProvider 接口意外看到正在开发的通用 SYSTEM_V2 增补和反馈分类开头，立即披露；未读取模型输出或检索实现。因此本轮不称双盲。采集输入先封存，方法作者随后完成第二次方法实现与工程测试并锁定方法，再获知具体项目与案例；锁定时第二次开发推理尚在运行，之后没有按开发或留出输出改方法。顺序和局限见[封存外说明](../benchmarks/semantic_v2/holdout/COLLECTION-BOUNDARY-NOTE.md)；[方法锁](evidence/semantic-v2-20261013/method-lock.json) SHA-256 为 `76087371cf7e09eee4d03c03ce9308597a394d5a1f1dcabdc43098bbd3586fe2`。准确范围是“未用于方法优化、首次模型调用前冻结的留出”，不代表随机样本或排除了基础模型预训练污染。

参考回放、安装包验证和来源核对没有调用本地模型；它们验证的是工程流程。留出真实模型效果与 token 成本须引用后续冻结协议和原始调用证据，不以这些 6/6 参考结果替代实测。上述说明不代替团队人工审核、作者贡献与权利确认。

## 2026-10-19 两组对照实验新增使用记录

- **实验配置：** DeepSeek `deepseek-flash` 与 Ollama 0.40.3 上的 `qwen2.5-coder:7b`（7.6B、Q4_K_M），分别比较规则检索与 AI 选择。Ollama 发行包和模型主层 SHA-256 与上文历史记录及官方资源核对一致；复用仓库外缓存，在临时目录复制模型数据后运行，未改写原缓存或安装新依赖。模型 Apache-2.0 许可层随缓存保留。8 GB RTX 4070 Laptop GPU，8192 上下文、单并行，温度 0、每次最多生成 2048 token；本地两次重复种子为 17、29。API 不支持对应种子控制，不声称严格确定性。
- **Schedule 冻结项目：** [dbader/schedule / `82a43db1`](https://github.com/dbader/schedule/tree/82a43db1b938d8fdf60103bd41f329e06c8d3651)，25 个合格文本文件；原 `LICENSE.txt` 为 MIT，随临时冻结输入保留。仅读取公开教程和源码，不导入、不执行、不安装，不将上游代码归为 ExampleProof 自主成果。
- **Humanize 冻结项目：** [python-humanize/humanize / `785e5dcc`](https://github.com/python-humanize/humanize/tree/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b)，21 个合格文本文件；MIT 原文采用 `LICENCE` 文件名，本次按相同 commit 单独保存许可副本于实验 `licenses/`，没有在模型调用后改动冻结输入。仅读取教程、元数据和源码，不执行，不安装。发布摘录或快照须保留适用版权、许可及免责。
- **TinyDB：** 继续使用此前明确接触过的 `edff96ae` 开发项目快照，30 个文件；不称为新的留出样本。另两个项目只是新冻结快照，不声称已排除训练污染或属于独立盲测。
- **证据范围：** 三个项目、四个组合、各两次，最多 36 次正式模型请求；预热是明确标注的合成输入上的实时调用，单独记录。原文质量核对由助手在隐藏模型标签后完成，独立人工质量指标和召回率保持未知，不把模型生成的断言、建议数量或改进文字视作独立证据。完整许可、冻结协议、实现归档、模型请求/响应和用量保存在仓库外审阅产物中，不随源码补丁复制第三方项目。未宣称参赛提交或独立评测结果。

## 2026-10-19 后续默认配置

按用户选择，将项目级 `analyze` 默认设为已登记的 DeepSeek `deepseek-flash`＋AST/关键词规则检索（`lexical`）；`compare` 默认 Flash，纯静态检查需显式 `--static`。保留 Ollama 与 AI 选择选项。此次只调整入口配置和文档，没有新增模型、数据集、依赖或第三方资源，没有重新调用实时模型，也未改写已冻结实验协议及结果。新增回归检查使用合成夹具与接口模拟，不作为模型效果证据。

后续教程风险控制补丁仅使用 Python 标准库和本仓库编写的合成夹具；没有新增第三方运行依赖、模型、数据集或复制资源。必要证据标注格式本身不构成独立人工标注，新增 HTTP 接口模拟也不是实时模型结果；已冻结实验保持不变。

后续遗漏诊断补充仅新增任务标注、阶段记录和合成工程夹具，没有新增第三方资源或模型调用。当前没有真实项目的独立必要证据全集和遗漏原因分布；任务查询、允许测试目录的收益及迭代检索均未完成效果评测，不将合成分支覆盖表述为这些方法的实证结论。

后续 iterative 实现使用同一静态索引和 Python 标准库，实现受限的缺口查询、任务词项排序及多轮分析；没有新增第三方依赖、模型、数据集或复制资源。新增验证为本仓库编写的合成夹具和 HTTP 接口模拟，没有新增实时模型调用或质量成绩；已有回放、历史兼容重现和实时模型记录保持各自原有来源及协议。

## TinyDB 首次运行任务案例补充

本例继续使用已接触的 TinyDB **4.9.0 / edff96aeb2616402e9489d46e90a592c05565621**，[原仓库](https://github.com/msiemens/tinydb/tree/edff96aeb2616402e9489d46e90a592c05565621)。复用此前真实 Flash 诊断，新增助手编写候选、冻结任务合同及同版本 Bubblewrap 执行；不是旧版迁移回放，不增加模型请求或 ExampleProof 的第三方运行依赖。

MIT 原版权与许可见[LICENSE.tinydb](evidence/tutorial-task-tinydb-20261019/LICENSE.tinydb)。案例审阅包复制 README.rst、pyproject.toml、原 LICENSE 和九个运行模块，保持原字节与记录摘要；可选 mypy_plugin.py 未供给运行。包内上游源码、补丁上下文、候选及录制诊断中的同源文字仍按 TinyDB MIT 许可保留归属，不视为 ExampleProof 自主实现。源码补丁只保存必要案例记录及许可证，完整运行输入在单独审阅包中。[来源清单](evidence/tutorial-task-tinydb-20261019/provenance.json)记录全部文件与摘要。

任务检查和候选均由助手编写，检查先冻结；负控制是明确合成的内存存储候选。这些有限检查不代表独立人工审核、真实读者实验或维护者接受。开发中的负控制提示符构造失败保留，修正时没有改合同、正例候选或上游原件，详见[案例说明](real-tutorial-task.md)。

## 本轮交付优化新增资源（2026-10-19）

| 资源 | 固定来源与许可 | 使用方式及边界 |
| --- | --- | --- |
| python-dotenv v1.1.0 | [6a02ef5a](https://github.com/theskumar/python-dotenv/tree/6a02ef5a1034d66338811757df07a113a1169af6)，BSD-3-Clause | 固定文档、源码、测试、LICENSE 进入仓库外任务评阅包；只静态读取，不安装或在宿主导入。保留版权、许可、免责及不背书条款。 |
| platformdirs 4.3.8 | [22089f1e](https://github.com/tox-dev/platformdirs/tree/22089f1e1ff477037cd7b3e03ad38ae2bf251031)，MIT | 同上，用于 Linux 示例和目录创建任务；保留完整 LICENSE。项目没有因其在评测中出现而获得维护者认可。 |
| PyPA build 及构建环境依赖 | build 1.6.1（MIT）、packaging 26.3（Apache-2.0 OR BSD-2-Clause）、pyproject_hooks 1.3.3（MIT）、tomli 2.5.0（MIT）；本机元数据及版本记录见交付包 build-tool-versions.txt | 仅用于 wheel/sdist 构建检查，不是 ExampleProof 运行依赖；未复制工具源码进项目。既有 setuptools/pip/venv 分发工具仍用于安装检查。 |

四个任务与必要证据由助手起草，人工评阅尚未完成；未发送新的真实模型请求。两个项目没有出现在此前教程对照，但本轮选题阅读后不能称为未来未见项目。任务包中的第三方文件不改标为 ExampleProof 的 MIT 自主代码。既有 Flash/Qwen 请求、TinyDB 候选和许可证仅作原字节归档及回放，不计作新的模型、数据集效果或采纳结果。新增实现使用 Python 标准库，运行依赖仍为空。
# 2026-10-21 学习入口补充

本机学习入口使用 Python 标准库 HTTP/线程/ZIP、原有模型客户端和原生 HTML/CSS/JavaScript；无新增运行时第三方依赖、外部字体、图像或前端库。提示与结构校验为本项目新增代码。

端到端开发验证使用 python-dotenv 公开提交 `6a02ef5a1034d66338811757df07a113a1169af6`（原资源说明中的 BSD-3-Clause 项目）与配置的 DeepSeek `deepseek-flash`，属于真实模型工程试用，不是未见数据效果评测。ZIP/浏览器测试使用明确标注的合成小项目。Microsoft Edge 仅用于开发界面检查，不随软件分发；已有构建工具只用于安装包验证。


## 2026-10-22 学习布局候选

新增路线目录、并排原文阅读、专注模式与浏览器本地笔记，仅使用原生 HTML/CSS/JavaScript；无新增第三方运行依赖、模型、字体、图像或网络资源。仓库外审阅预览复用本项目 learning-ui-v2 审阅包中的助手编写合成夹具，并增加模拟延迟、失败与笔记存储检查；原夹具位置为 `learning-ui-v2/review/fixture.js`，本轮副本为 `study-layout/review/fixture.js`。继续使用本机已有 Microsoft Edge 做界面检查，不复制浏览器资源或随软件分发。所有浏览器检查均为合成工程检查，不属于独立评测、真实模型结果或学习效果证据。

本轮落地验证另外使用助手编写的三文件合成 ZIP，经浏览器真实上传到独立测试数据目录，调用现有 HTTP 后端进行静态分析、原文读取、进度持久化与导出；不模拟这些接口，不执行上传源码，不调用云模型。另有两项明确标注的合成路线模式切换检查，不作为真实模型结果。未引入新的第三方资源或运行依赖。

## 2026-10-22 学习流程实现

细化任务、上下文问答与排错、正文/代码阅读、练习反馈、本机学习记录和可撤销调整使用 Python 标准库及原生 JavaScript/CSS，无新增第三方运行依赖或复制资源。可选运行检查复用已登记的 Bubblewrap 执行器，保持只读项目副本、无网络和禁止宿主回退；执行器本身未改动。

新增测试使用助手编写的保存/查询合成项目和合成模型响应。浏览器上传、HTTP、磁盘持久化及隔离执行是真实工程路径；合成模型反馈不能算真实模型效果，助手编写的断言不能算独立评测。继续使用本机已有 Microsoft Edge 检查桌面与移动视口，不复制或分发浏览器。既有 DeepSeek/Ollama 模型配置和历史评测记录不变，没有新增模型、数据集或外部网页资源。

后续文字层级调整只使用原生 HTML/CSS/JavaScript。复用上述合成 HTTP 流程夹具，并在隔离测试目录复制现有项目做长文字排版检查；未修改原项目、未发送新模型请求，也未新增第三方资源。浏览器检查用于确认展示与交互，不作为学习效率或独立用户研究证据。
