from html import escape
import json
from pathlib import Path
import os
import tempfile

LABELS = {
    "checked": "原示例通过检查", "runnable_unverified": "可运行 · 未配置行为检查",
    "verified_repair": "修复通过检查", "candidate_unverified": "候选可运行 · 行为未验证",
    "failed": "运行或检查失败", "repair_failed": "候选未通过复验",
    "rejected": "补丁完整性检查未通过", "blocked": "执行环境不可用",
    "skipped": "未执行", "declined": "模型未提出修复", "provider_error": "修复服务调用失败",
    "repeated_candidate": "候选重复 · 已停止",
    "candidate_format_error": "模型回答格式错误",
}

STOP_LABELS = {
    **LABELS, "max_attempts": "已达到轮数上限", "no_candidate": "没有更多候选",
}

ATTENTION = {"blocked", "provider_error", "candidate_format_error", "failed", "repair_failed",
             "rejected", "declined", "candidate_unverified", "runnable_unverified"}
PRIORITY = {status: index for index, status in enumerate((
    "blocked", "provider_error", "candidate_format_error", "failed", "repair_failed", "rejected",
    "declined", "candidate_unverified", "runnable_unverified", "skipped", "verified_repair", "checked"))}
NEXT_STEPS = {
    "blocked": "先运行 python -m exampleproof doctor，按提示准备 Linux、Bubblewrap 和系统 Python。",
    "provider_error": "检查本机 Ollama 服务、模型名称和连接；服务恢复后重新运行。",
    "candidate_format_error": "模型回答未满足 code、rationale 字符串格式；查看逐轮记录后可重新运行。",
    "failed": "检查示例依赖的导入、初始化代码和数据；需要初始化时在 setup 中明确配置。",
    "repair_failed": "候选仍未通过原有检查；查看错误和修改差异，人工修正或补充相关源码后复验。",
    "rejected": "候选未通过结构检查；保留原断言，按拒绝原因修改候选后复验。",
    "declined": "补充与问题相关的文档和源码，或由维护者人工提出候选。",
    "candidate_unverified": "补充独立的 checks 或 expected_stdout 后重新复验；当前候选不进入已验证补丁。",
    "runnable_unverified": "补充独立的行为检查，确认示例结果符合预期。",
    "skipped": "查看跳过原因，补齐所需条件后再执行。",
    "verified_repair": "审核修改是否保留原任务，通过人工审核后再应用 verified.patch。",
    "checked": "原示例已通过现有检查；检查范围之外的行为仍需按实际任务审核。",
}


def next_step(result):
    status = result["status"]
    if status in {"failed", "repair_failed"}:
        execution = result.get("after") or result["before"]
        if execution.get("failure_kind") == "stdout_mismatch":
            return "核对多余打印、空格和换行；保持文档约定的输出后重新复验。"
        if execution.get("failure_kind") == "behavior_check":
            return "核对任务的返回值、类型、作用范围和副作用；修改候选后仍用原有检查复验。"
    return NEXT_STEPS.get(status, "查看运行证据后，由维护者确认下一步操作。")


def execution_html(execution):
    e = lambda value: escape(str(value))
    statuses = {"passed": "通过", "failed": "失败", "timeout": "超时", "blocked": "环境不可用", "skipped": "未执行"}
    oracles = {"configured_behavior_checks": "已配置行为检查", "original_top_level_assertions": "原始断言", "none": "未配置行为检查"}
    metadata = f'{statuses.get(execution["status"], execution["status"])} · {execution["duration_seconds"]} 秒 · 检查：{oracles.get(execution["oracle"], execution["oracle"])}'
    body = f'<p class="meta">{e(metadata)}</p>'
    for label, field in (("标准输出", "stdout"), ("错误信息", "stderr")):
        if execution[field]:
            body += f'<p>{label}</p><pre>{e(execution[field])}</pre>'
    return body


def proposal_html(proposal):
    provenance = "导入的候选补丁 · 非本次模型推理" if proposal["provider"] == "candidate_file" else f'模型或提供者：{proposal.get("model") or proposal["provider"]}'
    return f'<p class="provider">{escape(provenance)}</p><p>{escape(proposal["rationale"])}</p>'


def render_html(report):
    e = lambda value: escape(str(value))
    counts = report["summary"]["counts"]
    cards = []
    for result in sorted(report["results"], key=lambda item: PRIORITY.get(item["status"], 0)):
        example, before = result["example"], result["before"]
        proposal, after = result.get("proposal"), result.get("after")
        status = result["status"]
        body = f'<p class="context">{e(example["context"])}</p><h3>原始示例</h3><pre>{e(example["code"])}</pre>'
        body += '<h3>运行证据</h3>' + execution_html(before)
        if proposal:
            body += proposal_html(proposal)
        if result.get("diff"):
            body += f'<h3>修改差异</h3><pre class="diff">{e(result["diff"])}</pre>'
        if result.get("rejection"):
            body += f'<p class="warning">{e(result["rejection"])}</p>'
        if after:
            body += '<h3>复验结果</h3>' + execution_html(after)
        if result.get("attempts"):
            body += '<h3>逐轮修复记录</h3>'
            for attempt in result["attempts"]:
                label = LABELS.get(attempt["status"], attempt["status"])
                body += f'<details><summary>第 {e(attempt["number"])} 轮 · {e(label)}</summary>'
                if attempt.get("proposal"):
                    body += proposal_html(attempt["proposal"])
                    body += f'<pre>{e(attempt["proposal"]["code"])}</pre>'
                    tokens = attempt["proposal"]
                    body += f'<p class="meta">输入 token：{e(tokens.get("input_tokens") if tokens.get("input_tokens") is not None else "未提供")} · 输出 token：{e(tokens.get("output_tokens") if tokens.get("output_tokens") is not None else "未提供")} · 响应耗时：{e(tokens["duration_seconds"])} 秒</p>'
                if attempt.get("rejection"):
                    body += f'<p class="warning">{e(attempt["rejection"])}</p>'
                if attempt.get("after"):
                    body += execution_html(attempt["after"])
                body += '</details>'
            reason = result.get("stop_reason")
            body += f'<p class="meta">停止原因：{e(STOP_LABELS.get(reason, reason))}</p>'
        opened = " open" if status in ATTENTION else ""
        cards.append(f'<article data-status="{e(status)}"><div class="card-head"><h2>{e(example["id"])}</h2><span class="badge {e(status)}">{e(LABELS[status])}</span></div><p class="meta">{e(example["path"])} · 第 {example["start_line"]}–{example["end_line"]} 行 · {before["duration_seconds"]} 秒</p><p class="next-step"><strong>下一步：</strong>{e(next_step(result))}</p><details{opened}><summary>查看示例、证据与修复</summary>{body}</details></article>')
    stats = "".join(f'<div class="stat"><strong>{value}</strong><span>{e(LABELS[key])}</span></div>' for key, value in counts.items())
    if report.get("repair"):
        repair = report["repair"]
        stats += f'<div class="stat"><strong>{e(repair["attempts"])}</strong><span>修复轮次 · 每例上限 {e(repair["max_attempts"])}</span></div>'
        for field, label in (("input_tokens", "输入 token"), ("output_tokens", "输出 token")):
            value = repair.get(field)
            stats += f'<div class="stat"><strong>{e(value if value is not None else "未提供")}</strong><span>{label}</span></div>'
    attention = sum(counts.get(status, 0) for status in ATTENTION)
    overview = f'<p class="overview">共 {e(report["summary"].get("total", len(report["results"])))} 个示例 · {attention} 项需要处理 · {counts.get("verified_repair", 0)} 项修复通过检查</p>'
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'none'"><title>例证 · 文档验证报告</title><style>
    :root{color-scheme:light;--ink:#172a35;--muted:#526876;--line:#d8e2e7;--accent:#096c61}*{box-sizing:border-box}body{margin:0;background:#f3f6f7;color:var(--ink);font:15px/1.65 system-ui,sans-serif}.wrap{max-width:1050px;margin:auto;padding:48px 24px}header{border-bottom:1px solid var(--line);padding-bottom:28px}.eyebrow{color:var(--accent);font-size:12px;letter-spacing:.18em;font-weight:750}h1{font-size:36px;margin:8px 0}h2{font-size:17px;margin:0;overflow-wrap:anywhere}h3{font-size:14px;margin:24px 0 8px}.intro,.meta,.context{color:var(--muted)}.meta{font-size:12px}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}.stat{background:white;border:1px solid var(--line);padding:14px 20px;border-radius:10px;min-width:145px}.stat strong{display:block;font-size:28px}.stat span{font-size:12px;color:var(--muted)}article{background:white;border:1px solid var(--line);border-radius:12px;margin:14px 0;padding:22px}.card-head{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.badge{font-size:12px;border-radius:20px;padding:5px 12px;background:#fff0d5;color:#775119}.verified_repair,.checked{background:#dff2eb;color:#11644d}.failed,.repair_failed,.rejected,.blocked,.provider_error{background:#fde7e4;color:#9a3029}summary{cursor:pointer;color:var(--accent);font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#172a35;color:#e4eef2;border-radius:8px;padding:16px;font:12px/1.7 ui-monospace,monospace}.diff{background:#edf5f1;color:#214b3b}.provider{font-size:12px;color:var(--muted)}.warning{border-left:3px solid #c96a29;padding-left:12px}footer{font-size:12px;color:var(--muted);margin-top:28px}@media(max-width:600px){.wrap{padding:24px 16px}h1{font-size:28px}article{padding:16px}}
    .next-step{background:#edf5f1;border-left:3px solid var(--accent);padding:10px 14px}.overview{font-weight:600}.candidate_format_error{background:#fde7e4;color:#9a3029}
    </style></head><body><main class="wrap"><header><div class="eyebrow">EXAMPLEPROOF / 例证</div><h1>每一处修复，都有运行证据。</h1><p class="intro">''' + e(report["project_name"]) + ''' · 文档示例检查报告</p><p class="meta">''' + e(report["generated_at"]) + '''</p>''' + overview + '''</header><section class="stats">''' + stats + '''</section>''' + "".join(cards) + '''<footer>“修复通过检查”表示通过已有断言或配置的行为检查。检查覆盖之外的语义仍需人工核验。候选补丁不会自动修改原始项目。</footer></main></body></html>'''


def write_report(output: Path, report: dict, patch: str):
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {"report.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                 "report.html": render_html(report), "verified.patch": patch}
    staged = []
    try:
        # Replacing directory entries avoids truncating an input through a hard
        # link, and readers never observe a partially written artifact.
        for name, content in artifacts.items():
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", errors="backslashreplace", newline="", dir=output,
                                             prefix=".exampleproof-", delete=False) as temporary:
                path = Path(temporary.name)
                staged.append((path, output / name))
                temporary.write(content)
        for path, destination in staged:
            os.replace(path, destination)
    finally:
        for path, _ in staged:
            path.unlink(missing_ok=True)
