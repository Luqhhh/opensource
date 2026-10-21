# 教程任务工作台与验证范围

正式界面采用 A：浅色背景 `#f4f7fa`、深蓝导航 `#142d3a`、青绿操作色 `#087e80`。按用户要求，前端仅面向用户展示，不包含人工审批或评分表单。页面为离线 HTML/CSS/JavaScript，无前端框架、外部字体或网络请求。

## 从读者卡点开始

需要分别记录：读者具体操作、教程已承诺的范围、实际错误、已有解释的位置和仍待验证的困扰。例如，环境变量未被配置文件覆盖可能是文档已说明的正常行为；拿到配置目录路径也不必然承诺目录已创建。重复提醒可能有用，但不能计为发现了缺失说明。

工作台包括完整冻结原文搜索、任务场景、对照结果、真实工程案例和方案边界。人工预审、逐条质评、读者观察记录通过对话或独立 JSON 保存；前端只展示经核对的记录。修改任务或问题清单须建立新的冻结版本。

```sh
python3 scripts/build_workbench.py /path/to/frozen /tmp/workbench
# 正式运行后载入全部策略报告：
python3 scripts/build_workbench.py /path/to/frozen /tmp/workbench-results --run /path/to/run \
  --preflight /path/to/preflight.json --quality-review /path/to/quality-review.json
```

Windows + WSL 使用资源管理器路径 `\\wsl.localhost\Ubuntu-22.04\tmp\workbench`，双击 `index.html`；发行版名称按本机实际情况替换。Linux `/tmp/...` 不能直接作为 Windows 磁盘路径。

## 比较直接模型与证据流程

评测协议可指定 `direct`、`lexical`、`iterative`、`documentation_only`。直接模型组与 lexical 组使用同一个最终证据 JSON 和任务，系统提示不同；lexical 另有静态观察与本地补查，必须分别报告模型发现和静态发现。iterative 可主动请求冻结索引内的证据，调用数与实际 token 另计。documentation_only 去掉源码证据，但其文档选择和实际 token 也可能变化，不能把结果差异完全归因于单一源码变量。

新增协议设 `review_schema: 2`，要求逐任务确认范围、原文、必要证据与完整问题清单。旧冻结协议继续使用原实现，不把升级代码偷偷放进旧基线。修改任务或 gold 也必须重新冻结。此前看过的任务重新冻结后仍是开发集，不能称为未见留出集。

缺失文档主张会补查整个合格索引，附带命中原文并标为 `needs_confirmation`；命中不是自动反驳，零命中不证明缺失。报告区分源码声明冲突、示例风险、证据不足和体验建议。当前确定性检查仅覆盖本地链接、明确的 Python 最低版本声明、占位路径、可唯一定位函数的布尔/None 默认值；不是完整配置分析器。

质量汇总保留 supported、partial、unsupported、unassessable 四类。原文已说明却被声称缺失时，不允许标为 supported。支持率与无支持占比以全部建议为分母；召回率依赖完整冻结问题清单，不能用必要证据覆盖率代替。没有真实评阅时均为 null。实际请求数、token 与耗时仍可单独汇总。

```sh
python3 scripts/run_tutorial_evaluation.py summarize /path/to/frozen /path/to/run \
  --review /path/to/quality-review.json --observations /path/to/reader-observations.json
```

独立的读者观察记录按原版、工具辅助、候选版本分别记录完成情况、实测时间、求助次数和过程说明。重复参与、顺序与熟悉效应尚未被实验设计消除；工程检查通过不能代替学习效果。

## 从任务模板到补丁

```sh
python3 -m exampleproof task-init PROJECT --document README.rst --block 3 \
  --task '在新 Linux 会话中查询用户与站点目录' --import-root src --output /tmp/task-draft
```

模板列出源码、选中代码块和运行边界，但检查留空。由使用者或评测者填写并冻结 setup/checks/expected_stdout，然后：

```sh
python3 -m exampleproof task-diagnose PROJECT --contract /tmp/task-draft/task.json
python3 -m exampleproof task-improve PROJECT --analysis /path/to/analysis.json \
  --contract /tmp/task-draft/task.json --finding-id f-REPLACE \
  --provider deepseek --output /tmp/task-attempt --cloud-review /tmp/proposal-review.json
# 核对生成的确切发送清单后，按命令输出提供 --approve-cloud SHA256。
```

建议 ID 绑定原始快照、标题、来源、分类与引用跨度，适用于同一条保存后的建议；它不是跨模型重写的语义身份。模型只收到任务、诊断、文档及引用，不收到验收断言。导入探测与执行都经过 Bubblewrap；依赖或生成文件缺失归为环境未准备，不自动创建替代文件，也不回退宿主执行。

任务检查保留断言、原有 REPL 输出、其他代码块、RST 指令及选项。仅允许保留原有完全相同的环境赋值，不能借补丁新增任意对象修改。支持 Markdown Python 块、RST code-block/code/sourcecode 的 Python/pycon、有限选项和包含 REPL 提示符的字面块。不是任意 RST/Sphinx 语法的完整解析器。

通过的候选也只导出补丁，记录原版、候选、临时副本应用后复查三份执行结果；检查失败、候选拒绝和模型拒绝均保存。不把模型新增断言作为独立证据。

## 可选的真实 RST 渲染

默认任务页面的结构预览只是转义原文与代码块。需要真实渲染时，显式提供固定版本的 Docutils wheel；无需安装到宿主或增加运行依赖：

```sh
python3 -m pip download --no-deps --only-binary=:all: docutils==0.21.2 --dest /tmp/render-deps
python3 scripts/render_rst.py /path/to/README.rst \
  --docutils-wheel /tmp/render-deps/docutils-0.21.2-py3-none-any.whl --output /tmp/rst-render
```

实现核对 wheel SHA256，在现有隔离 runner 中渲染；禁用 include/raw，不读取项目 conf.py，不加载 Sphinx 扩展。警告和截断均保留，非完整成功返回非零状态。通过仅说明这一受限 Docutils 渲染，不代表完整文档站构建通过。资源来源见 [resources.md](resources.md)。

## 后续值得验证的方向

1. 反证复核：让评阅者一键查看缺失主张与已有说明的对应位置，测量纠正误报时是否引入漏报。
2. 前提关系图：连接安装、导入、初始化、配置、目录、持久化等任务前提；以真实读者停滞记录验证价值。
3. 源码影响审计：保存仅文档与加入源码后的逐条判断变化、引用和人工结论；变化本身不等于变好。
4. 补丁影响范围：用相邻任务和健康任务检查一次修改的回归，而非仅重复候选自己的断言。
5. 版本定向复查：源码接口、默认值或依赖声明变化时，定位需要重新核对的教程与旧判断。

其中补查原文、对照入口、模板、环境诊断和离线工作台已实现；自动前提图、跨任务回归调度、版本定向复查仍是后续方向。
