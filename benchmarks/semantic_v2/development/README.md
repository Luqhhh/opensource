# 语义评测开发集 v2

这是根据已看过的 v1 案例和模型结果扩展的 **development_v2 开发集**，不是留出集。3 个固定版本项目共 9 例：6 个迁移失败、3 个健康对照。新版没有修改 `benchmarks/real_projects/` 或 `docs/evidence/real-projects-20261013/`；v1 的 5 个失败案例及其分数保持原样。

| 项目 | 旧版正控制 → 目标版本 | 迁移失败 / 健康 | 新增语义覆盖 |
| --- | --- | ---: | --- |
| [TinyDB](tinydb/) | 3.15.2 → 4.8.2 | 2 / 1 | 默认表与命名表范围、多记录、Unicode/空串/false/null、无记录表、缺失表、重复调用、重新插入的 ID、缓存失效、关闭后持久化 |
| [more-itertools](more_itertools/) | 5.0.0 → 9.0.0 | 2 / 1 | `collate` 的重复项、`key` 与 `reverse` 同时使用、相同 key 的稳定顺序、Unicode、一次性迭代器、零输入、构造时惰性、有限前缀与无限流 |
| [MarkupSafe](markupsafe/) | 1.1.1 → 2.1.5 | 2 / 1 | 保留原显示回归，另增 `convert` 可复用契约；普通/空/Unicode/HTML 特殊字符串、str 子类、Markup 类型及 identity、数字、布尔、None、自定义 `__str__`/`__html__` |

TinyDB 的两个操作被评测者改写为可复用的 `clear_default` 和 `drop_named` 绑定；MarkupSafe 的 `convert` 是新写的绑定任务。这些都是**根据上游语义编写的评测适配**，不声称是新发现或机械摘录的官方文档。保留的官方命令位于各项目 `origin_cases/`，完整来源和许可位于 `upstream-provenance.json` 及 `upstream/`。所有绑定、输出及扩展行为契约均放在代码块紧邻的上下文中，能够进入模型请求。

MarkupSafe 原显示例只检查一个已经转义的 `Markup` 值，因此 `escape` 替代转换操作也可能得到相同的显示输出。新增案例先明确要求保留 `convert`，再用多种输入独立检查它：普通字符串不得被 HTML 转义，`None` 应成为 `'None'`，已有 Markup 对象必须保持 identity。v2 未追溯改变 v1 的得分，也不把原来的有限显示回归描述成通用转换正确性证明。

## 已完成的验证

最终证据：[validation-02/validation.json](evidence/validation-02/validation.json)。`validation-01` 是补齐其余健康/分组案例的模型可见契约前的工程记录，保留但不作为当前输入的最终校验。

| 检查 | 结果 |
| --- | ---: |
| 原始代码配旧运行时，同一套 v2 setup/checks/stdout | 9 / 9 通过 |
| 原始代码配目标运行时 | 6 失败、3 健康，符合预期 |
| 人工参考候选，经导出补丁、`git apply`、重新检查 | 6 / 6 修复，3 / 3 健康保留 |
| 有意错误候选，被外部语义检查拒绝 | 9 / 9 |
| 其中显示 stdout 仍完全匹配的错误候选 | 8 / 9 |
| 真实模型请求 | 0 |

9 个负例均通过候选结构检查、完成示例执行，随后由外部检查以 `AssertionError` / returncode 22 拒绝；没有将候选语法、格式或不支持的语法误算为语义检查成功。

| 负例 | 数量 | 说明 |
| --- | ---: | --- |
| TinyDB 错误范围 | 2 | 清默认表时删全部表，或删命名表时清默认表 |
| TinyDB 只执行一次 | 2 | 第一次操作正确，但留下不可复用的空操作 callable |
| `collate` 急切排序 | 1 | 三个显示输出全对，但构造时消耗输入，破坏惰性 |
| `collate` 删除重复 | 1 | 错误去重，外部检查拒绝，显示输出也改变 |
| MarkupSafe 使用 `escape` | 1 | 显示安全值不变，但普通字符串错误转义/改变类型 |
| MarkupSafe 将 None 当空串 | 1 | 显示值不变，边界输入语义错误 |
| MarkupSafe 重建 Markup | 1 | 显示值、类型不变，却丢失已有对象 identity |

参考补丁均作用于此评测适配目录的 Markdown，不是已提交上游的 PR：

- [TinyDB 参考补丁](evidence/validation-02/tinydb/reference/repair/verified.patch)
- [more-itertools 参考补丁](evidence/validation-02/more_itertools/reference/repair/verified.patch)
- [MarkupSafe 参考补丁](evidence/validation-02/markupsafe/reference/repair/verified.patch)

## 复现与边界

在仓库根目录执行，输出目录必须不存在：

```sh
python3 benchmarks/semantic_v2/development/validate.py --output /tmp/exampleproof-semantic-v2-new
```

验证脚本检查已复制源码与原 v1 文件逐字节一致；只在隔离的 `SandboxRunner` 中执行上游代码；使用旧版本源文件映射正控制，而不是在宿主机安装或导入旧库。more-itertools 5.0.0 的 six 1.16.0 也只复制进旧版隔离工作区。运行前后还比较 v1 项目和冻结实验的文件哈希，确认未改变。脚本拒绝覆盖已有证据。

`prepare.py` 是一次性的案例编写记录，已有项目目录时拒绝运行。它不会修改原项目。正常复查应运行 `validate.py`。

这批参考与负例回放只证明检查能区分所选已知错误，不是模型成功率。任务和检查是共同设计的开发数据；后续模型收益必须用另行冻结的新留出案例衡量。有限检查不能证明一般语义等价，示例与检查共用解释器，也不是对抗恶意候选的安全证明。MarkupSafe 使用上游 Python fallback，未测试 C 扩展。

复制的资源和版本沿用原评测：TinyDB 为 MIT；more-itertools 与 six 为 MIT，并保留 recipes 的 Python 文档来源说明及 PSF 许可；MarkupSafe 为 BSD-3-Clause。每份完整许可均保留在相应 `upstream/` 目录；没有新增运行时依赖、下载模型或调用外部服务。
