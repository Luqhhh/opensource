# 维护者统一提供 AI 额度

源途 · RepoPath 使用 `repopath` 启动入口；下述 `EXAMPLEPROOF_*` 变量、内部模块与部署路径为保留的兼容标识，更名无需调整既有服务数据。安装包升级见[品牌与升级说明](branding.md)。

克隆者的浏览器连接自己的本机工作台，本机 Python 后端再经 HTTPS 请求维护者的共享代理，由代理使用维护者的 DeepSeek API Key 调用模型。克隆者无需 DeepSeek 密钥。代理仅转发模型请求，不接收整个仓库，也不执行项目代码。

本实现尚未部署到公共地址。下面的 `ai.example.org` 是占位域名，不是可用服务。

## 密钥与访问方式

| 配置 | 保存位置 | 是否可以提交到仓库 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 代理服务器的环境变量；systemd 可从 `/etc/exampleproof-gateway.env` 读取 | 不可以 |
| 共享服务 HTTPS 地址和模型名称 | `exampleproof/shared_service.py` 或客户端环境变量 | 可以 |
| `EXAMPLEPROOF_GATEWAY_TOKEN` 邀请码 | 代理和受邀者各自的环境变量 | 不可以 |
| 调用用量 | 代理数据目录中的 `gateway-usage.sqlite3`，权限 0600 | 不可以 |

默认要求至少 24 字符的邀请码。邀请码只允许使用你的共享代理，不是你的 DeepSeek 密钥；它仍可以消耗共享额度，应仅分发给受邀者。变更服务端邀请码并重启即可撤销旧码。本版是一个共享邀请码和全局额度，不包含独立用户账号或个人配额。

显式添加 `--public` 可开放无邀请码访问。此模式下任何知道地址的人都能消耗全局额度，包括仓库之外的客户端；调用次数上限不等同于按人公平分配。

## 本机验证与启动

代理端先通过终端安全输入密钥和邀请码（以下为 Bash，输入不显示，也不写入命令历史）：

```sh
read -rsp 'DeepSeek API Key: ' DEEPSEEK_API_KEY
export DEEPSEEK_API_KEY
read -rsp '共享邀请码（至少 24 字符）: ' EXAMPLEPROOF_GATEWAY_TOKEN
export EXAMPLEPROOF_GATEWAY_TOKEN
python3 -m repopath gateway --daily-limit 50 --hourly-limit 10 --total-limit 500
```

服务固定监听 `127.0.0.1:8787`。`GET /health` 仅检查代理进程和配置，不调用模型；它不证明密钥余额充足或供应商可用。真实请求只有调用 `/v1/complete` 时发生。

克隆者在另一个终端设置代理地址和受邀邀请码，然后启动工作台：

```sh
export EXAMPLEPROOF_GATEWAY_URL='http://127.0.0.1:8787'
read -rsp '共享邀请码: ' EXAMPLEPROOF_GATEWAY_TOKEN
export EXAMPLEPROOF_GATEWAY_TOKEN
python3 -m repopath learn
```

以上回环地址只用于同机联调。远程用户应填写你部署好的 `https://` 地址。公共模式不需要设置邀请码。Windows PowerShell 使用 `$env:EXAMPLEPROOF_GATEWAY_URL='https://你的域名'` 等环境配置；请避免在共享终端历史中留下真实凭据。

## 部署到服务器

使用专门的非 root 系统用户，将代码安装到 `/opt/exampleproof` 下的虚拟环境；创建私有的 `/etc/exampleproof-gateway.env`，按 `deploy/gateway.env.example` 填入真实值并设置文件权限 0600。服务用户需要读取安装目录；systemd 负责读取环境文件并以该用户运行。

`deploy/exampleproof-gateway.service` 提供守护进程模板，数据保存在 `/var/lib/exampleproof-gateway`。安装到 `/etc/systemd/system/` 后执行 `systemctl daemon-reload`，再启用服务。按实际路径、账户、模型和预算修改模板。若使用公共模式，在 `ExecStart` 中显式添加 `--public`，不要发布邀请码。

将 `deploy/gateway.Caddyfile` 中的域名替换成已指向服务器的域名，供 Caddy 在 80/443 端口提供 HTTPS，再转发到回环代理。使用 Caddy 的 `validate` 检查配置后启动或重载。配置只开放健康检查和模型接口，没有配置请求正文或访问日志记录。Caddy 的自动 HTTPS 需要正确 DNS 和端口可达，见[官方反向代理指南](https://caddyserver.com/docs/quick-starts/reverse-proxy)。请求大小限制对应[官方 request_body 指令](https://caddyserver.com/docs/caddyfile/directives/request_body)。

Python 标准库 HTTP 服务仅作为回环后端，连接数与推理并发均有限制。它适合小规模共享试用；未进行公网负载或安全评测，不应直接作为无边界的公网服务。Python 官方说明 `http.server` 仅提供基础防护，见[官方文档](https://docs.python.org/3/library/http.server.html)。较大规模服务应另行采用成熟的应用服务器与统一认证、监控体系。

## 让 clone 后自动接入

完成部署并核对 HTTPS 地址后，在 `exampleproof/shared_service.py` 中仅填写公开地址 `SERVICE_URL` 和服务端一致的 `MODEL`，再把这两个非秘密配置随代码发布。这样克隆者运行 `python3 -m repopath learn` 就会自动选择共享服务；邀请码模式仍需各自设置邀请码。

选择优先级为：显式指定 provider；自动模式下，命令行/环境变量共享地址优先，其次个人 `DEEPSEEK_API_KEY`，然后仓库的公开共享地址，最后基础路线。可以用 `--provider none` 禁用 AI，用 `--provider deepseek` 使用自己的密钥。`--gateway-url` 覆盖默认共享地址，`--model` 覆盖默认模型。

共享服务返回额度耗尽、认证失败或网络错误时，工作台显示错误并保留基础路线、问题和笔记，不自动改用个人密钥，也不自动重试产生新调用。

## 用量边界与数据

- 默认全局每 UTC 小时最多 10 次、每 UTC 日最多 50 次、累计最多 500 次调用，同时最多 2 次推理；都可以通过命令行调低或调高，不能设置为 0 来取消限制。
- SQLite 在上游调用前原子预留额度，重启保留计数。网络失败、超时或无效模型回答仍消耗一次额度，以避免不确定是否计费时重复释放。并发已满、鉴权失败和格式错误不占调用额度。
- 这是请求次数上限，不是人民币金额上限。实际费用取决于模型和供应商计费；服务端固定模型、官方 DeepSeek 地址、60 秒超时和既有 2,048 输出 token 上限，客户端不能指定其他上游或更大的输出预算。
- 单次请求最多 96,000 字节，响应最多 256,000 字节。远程客户端只允许 HTTPS，不跟随重定向；本机联调可用回环 HTTP。
- 数据库只保存当前时段与累计调用计数。代理不持久化密钥、提示词、回答或原文；内容仍会经由代理发送给模型供应商。本机工作台保留既有请求与回答记录，发送预览会显示共享服务地址。
- 保留数据目录即可保留累计预算；不要在重启或升级时删除用量数据库。累计用完后应明确提高 `--total-limit`，而非依赖自动重置。

自动化验证使用合成响应，涵盖鉴权、额度持久化与并发预留、错误脱敏、HTTP 大小限制、客户端接入及发送预览绑定；不属于真实模型质量或公网部署结果。
