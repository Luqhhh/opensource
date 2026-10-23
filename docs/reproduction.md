# 安装复现与维护计划

供首次接触例证的人从安装开始完成一次可记录的复现。基础功能无需模型和第三方Python运行依赖；AI由本机使用者配置自己的服务。

## 安装与首次使用

从公开仓库下载固定提交的源码，或使用交付包中的wheel。建立新虚拟环境，在源码目录之外启动已安装程序，避免误用工作区模块。

```sh
python3 -m venv exampleproof-env
exampleproof-env/bin/python -m pip install /path/to/aic_exampleproof-0.1.0-py3-none-any.whl
exampleproof-env/bin/exampleproof learn --provider none --data /tmp/exampleproof-reproduction
```

Windows程序位于 `exampleproof-env\Scripts\`。打开 <http://127.0.0.1:8765/>，上传试用包的TinyDB或Schedule ZIP，输入具体目标。打开原文、写笔记、关闭后恢复记录并导出指南。AI问答单独验证，记录实际模式。

可选执行需要Linux/WSL和Bubblewrap。用 `exampleproof doctor --json` 检查；隔离不可用时使用阅读与问答，不能改为宿主执行。示例必须完整，每次独立，无网络与自动安装。

实际复现者填写 [外部复现表](user-study/external-reproduction.csv)。开发者安装验证、自动操作录像和外部人员复现分别记录。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 无AI功能 | 查看启动provider；在启动终端配置自己的密钥，或显式选择已准备的Ollama |
| 云端失败 | 保留错误，检查网络与服务；基础路线仍可阅读 |
| GitHub导入失败 | 使用固定项目ZIP，记录网络问题 |
| 运行blocked | 查看doctor，确认Linux、Bubblewrap与命名空间；禁止宿主回退 |
| 导入不全 | 查看范围说明，选择较小项目；输入有文件数与大小限制 |
| 找不到记录 | 确认同一个 `--data` 目录；参与者之间不共用 |

## 反馈与维护

在 <https://github.com/Luqhhh/opensource/issues> 提供版本、系统、最短操作、预期与实际现象。删除个人信息、密钥和私人源码；第三方内容注明来源与许可。

团队在试用期按场次整理阻碍任务的问题，优先处理保存、入口、引用定位和失败恢复。每个改动保留反馈编号，通过核心检查后给下一批参与者使用；版本变化单列。

后续计划每两周整理Issues、使用说明与资源清单；根据成员实际情况调整，不承诺全天服务。新增功能先说明具体用户问题。运行依赖保持精简，隔离执行和原项目只读原则不变。
