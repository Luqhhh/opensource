# 开源及第三方资源使用清单

记录日期：2026-10-13。本清单作为技术报告附件；“已核对”仅表示查阅了所列来源或本机记录，不代替团队权属、服务条款及最终发布审核。版本按实测环境或配置分别标记，未知项不写成已确认。本仓库应用代码为MIT，第三方资源仍遵守各自许可。

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

以上复制资源、其机械派生案例，以及含相同文本的 `inputs/` 和报告不能仅依赖仓库根目录 MIT 进行统一授权；公开或导出证据时应保留对应项目的 `provenance.json`、原始许可证及本清单。参考 `proposals.json` 属工程回放资料，不是模型输出成绩；真实模型请求须排除这些参考答案和外部 oracle。

## AI参与和审核记录

2026-10-13：AI辅助选题、规则解读、代码与测试、文档及回放候选；后续辅助多轮修复、证据保存、执行完整性与提示词优化。本轮另辅助自动benchmark流程、兼容性案例、误修复对照和参赛材料/PDF构建，随后采集三个真实上游项目的历史文档、核对许可、机械提取版本迁移案例并完成冻结对照。27 个实验单元、92 次真实请求及失败记录见 [实测证据](evidence/real-projects-20261013/README.md)。提交和证据说明实际变化，自动测试不能替代团队人工审核。

`proposals.json`与`proposals.multiround.json`是已保存候选；后者有刻意失败的第一轮，只验证下一轮流程，不产生模型调用。真实Ollama调用保存在 `docs/evidence/ollama-20261013/` 和 `docs/evidence/compatibility-20261013/`，包含放弃与检查失败，候选未人工改写。

两组既有真实提示词优化均在观察对应开发样例基线后进行：原教程三例第一轮通过；新增兼容性集优化后六个失败中四例通过补丁复查，其中计时例实际经历三轮。后者提示词及实际调用预算同时变化，不能独立证明多轮增益，也不代表未见项目成功率。新增三个上游项目案例未参与此前提示词优化，其参考复验不是实时模型评测；冻结后的固定预算对照应以另行保存的协议、请求和完整结果为准。“未见”只指本项目开发过程中的留出，不能断言公开文档从未进入基础模型训练集。尚无维护者或真实用户反馈可供引用。

**提交前待补：** 团队确认实际AI服务和模型档案，审核生成内容来源/权利，记录人工修改及验证，确认共同权利人的参赛和公开授权，检查最终版本的新增资源已全部列入。不得将“待审核”改写为“团队已审核”。
