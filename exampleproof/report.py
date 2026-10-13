from html import escape
import json
from pathlib import Path

LABELS = {
    "checked": "原示例通过检查", "runnable_unverified": "可运行 · 未配置行为检查",
    "verified_repair": "修复通过检查", "candidate_unverified": "候选可运行 · 行为未验证",
    "failed": "运行或检查失败", "repair_failed": "候选未通过复验",
    "rejected": "补丁完整性检查未通过", "blocked": "执行环境不可用",
    "skipped": "未执行", "declined": "模型未提出修复", "provider_error": "修复服务调用失败",
}


def render_html(report):
    e = lambda value: escape(str(value))
    counts = report["summary"]["counts"]
    cards = []
    for result in report["results"]:
        example, before = result["example"], result["before"]
        proposal, after = result.get("proposal"), result.get("after")
        status = result["status"]
        body = f'<p class="context">{e(example["context"])}</p><h3>原始示例</h3><pre>{e(example["code"])}</pre>'
        body += f'<h3>运行证据</h3><pre>{e(before["stderr"] or before["stdout"] or "无输出")}</pre>'
        if proposal:
            provenance = "导入的候选补丁 · 非本次模型推理" if proposal["provider"] == "candidate_file" else f'本地模型：{proposal["model"]}'
            body += f'<p class="provider">{e(provenance)}</p><p>{e(proposal["rationale"])}</p>'
        if result.get("diff"):
            body += f'<h3>修改差异</h3><pre class="diff">{e(result["diff"])}</pre>'
        if result.get("rejection"):
            body += f'<p class="warning">{e(result["rejection"])}</p>'
        if after:
            body += f'<h3>复验结果</h3><pre>{e(after["stderr"] or after["stdout"] or "无输出")}</pre>'
        cards.append(f'<article data-status="{e(status)}"><div class="card-head"><h2>{e(example["id"])}</h2><span class="badge {e(status)}">{e(LABELS[status])}</span></div><p class="meta">{e(example["path"])} · 第 {example["start_line"]}–{example["end_line"]} 行 · {before["duration_seconds"]} 秒</p><details><summary>查看示例、证据与修复</summary>{body}</details></article>')
    stats = "".join(f'<div class="stat"><strong>{value}</strong><span>{e(LABELS[key])}</span></div>' for key, value in counts.items())
    return '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'none'"><title>例证 · 文档验证报告</title><style>
    :root{color-scheme:light;--ink:#172a35;--muted:#526876;--line:#d8e2e7;--accent:#096c61}*{box-sizing:border-box}body{margin:0;background:#f3f6f7;color:var(--ink);font:15px/1.65 system-ui,sans-serif}.wrap{max-width:1050px;margin:auto;padding:48px 24px}header{border-bottom:1px solid var(--line);padding-bottom:28px}.eyebrow{color:var(--accent);font-size:12px;letter-spacing:.18em;font-weight:750}h1{font-size:36px;margin:8px 0}h2{font-size:17px;margin:0;overflow-wrap:anywhere}h3{font-size:14px;margin:24px 0 8px}.intro,.meta,.context{color:var(--muted)}.meta{font-size:12px}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:24px 0}.stat{background:white;border:1px solid var(--line);padding:14px 20px;border-radius:10px;min-width:145px}.stat strong{display:block;font-size:28px}.stat span{font-size:12px;color:var(--muted)}article{background:white;border:1px solid var(--line);border-radius:12px;margin:14px 0;padding:22px}.card-head{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}.badge{font-size:12px;border-radius:20px;padding:5px 12px;background:#fff0d5;color:#775119}.verified_repair,.checked{background:#dff2eb;color:#11644d}.failed,.repair_failed,.rejected,.blocked,.provider_error{background:#fde7e4;color:#9a3029}summary{cursor:pointer;color:var(--accent);font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#172a35;color:#e4eef2;border-radius:8px;padding:16px;font:12px/1.7 ui-monospace,monospace}.diff{background:#edf5f1;color:#214b3b}.provider{font-size:12px;color:var(--muted)}.warning{border-left:3px solid #c96a29;padding-left:12px}footer{font-size:12px;color:var(--muted);margin-top:28px}@media(max-width:600px){.wrap{padding:24px 16px}h1{font-size:28px}article{padding:16px}}
    </style></head><body><main class="wrap"><header><div class="eyebrow">EXAMPLEPROOF / 例证</div><h1>每一处修复，都有运行证据。</h1><p class="intro">''' + e(report["project_name"]) + ''' · 文档示例检查报告</p><p class="meta">''' + e(report["generated_at"]) + '''</p></header><section class="stats">''' + stats + '''</section>''' + "".join(cards) + '''<footer>“修复通过检查”表示通过已有断言或配置的行为检查。检查覆盖之外的语义仍需人工核验。候选补丁不会自动修改原始项目。</footer></main></body></html>'''


def write_report(output: Path, report: dict, patch: str):
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "report.html").write_text(render_html(report), encoding="utf-8")
    (output / "verified.patch").write_text(patch, encoding="utf-8")
