"""Grounded study tasks and reading metadata; parsing never executes project code."""
import ast
import hashlib
import json
from pathlib import PurePosixPath
import re


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def route_id(record):
    return digest([record.get('snapshot_id'), record.get('guide_revision', 1), record['guide']])


def outline(path, text):
    rows, lines = [], text.splitlines()
    suffix = PurePosixPath(path).suffix.lower()
    if suffix in {'.md', '.markdown', '.rst', '.txt'}:
        fence = False
        for i, line in enumerate(lines):
            if re.match(r'^\s*(```|~~~)', line):
                fence = not fence
            if fence:
                continue
            match = re.match(r'^(#{1,6})\s+(.+?)\s*#*$', line)
            under = i+1 < len(lines) and re.fullmatch(r'[=~\-^"`:+*#]{3,}', lines[i+1].strip())
            if match or (line.strip() and under):
                rows.append({'title': (match[2] if match else line.strip())[:160],
                             'line': i+1, 'end_line': i+1,
                             'level': len(match[1]) if match else 2, 'kind': 'heading'})
    elif suffix == '.py':
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    rows.append({'title': node.name, 'line': node.lineno,
                                 'end_line': node.end_lineno, 'kind': 'class' if isinstance(node, ast.ClassDef) else 'function',
                                 'level': 1, 'summary': (ast.get_docstring(node) or '')[:800]})
        except (SyntaxError, ValueError, RecursionError):
            pass
    else:
        for i, line in enumerate(lines):
            match = re.search(r'\b(?:function|class|def|fn|func)\s+(\w+)|\b(?:const|let)\s+(\w+)\s*=.*=>', line)
            if match:
                rows.append({'title': next(s for s in match.groups() if s), 'line': i+1,
                             'end_line': i+1, 'kind': 'symbol', 'level': 1})
    return sorted(rows, key=lambda item: item['line'])[:400]


def excerpt(files, ref, limit=6000):
    item = files.get(ref.get('path'))
    if not item:
        return ''
    return '\n'.join(item['text'].splitlines()[max(0, ref['start_line']-1):ref['end_line']])[:limit]


def code_sample(files, refs):
    """Locate an original fenced Python example and its exact line span."""
    for ref in refs:
        lines = excerpt(files, ref).splitlines()
        for i, line in enumerate(lines):
            if re.match(r'^\s*```(?:python|py)\s*$', line):
                end = next((j for j in range(i+1, len(lines)) if lines[j].strip().startswith('```')), None)
                if end is not None and 0 < end-i <= 65:
                    return {'text': '\n'.join(lines[i+1:end]), 'evidence': [{
                        'path': ref['path'], 'start_line': ref['start_line']+i+1,
                        'end_line': ref['start_line']+end-1}]}
    return None


def concrete_local_steps(guide, snapshot):
    """Break the existing usage step into real source statements when parseable."""
    result = []
    for step in guide['steps']:
        if step['title'] != '从原文的最小用法开始':
            result.append(step)
            continue
        sample = code_sample(snapshot.files, step['evidence'])
        try:
            tree = ast.parse(sample['text']) if sample else None
        except (SyntaxError, ValueError, RecursionError):
            tree = None
        statements = tree.body if tree else []
        if not 2 <= len(statements) <= 8:
            result.append(step)
            continue
        groups = [statements[:1], statements[1:]] if len(statements) == 2 else [statements[:1], statements[1:-1], statements[-1:]]
        for number, group in enumerate(groups):
            calls = [n for node in group for n in ast.walk(node) if isinstance(n, ast.Call)]
            call = ast.unparse(calls[0].func)[:70] if calls else None
            label = ('准备示例中的导入与输入' if number == 0 else
                     ('观察示例最后一步' if number == len(groups)-1 else '继续示例中的操作'))
            if call:
                label += '：' + call
            first, last = group[0].lineno, group[-1].end_lineno
            ref = dict(sample['evidence'][0])
            ref.update(start_line=ref['start_line']+first-1, end_line=ref['start_line']+last-1)
            result.append({'title': label,
                           'action': '对照引用中的原始代码，在自己的开发环境中按顺序操作。' +
                                     ('沿用前一步的导入、变量和会话，不要把这一段当成独立程序。' if number else '先确认安装前提和原文要求的运行位置。'),
                           'checkpoint': '记录实际输出或对象状态，并与原文核对。原文未给出确定输出时，保留疑问，不把未报错等同于结果正确。',
                           'evidence': [ref], 'original_code': '\n'.join(sample['text'].splitlines()[first-1:last])})
    for i, step in enumerate(result):
        step['id'] = f'step-{i+1}'
    guide['steps'] = result
    return guide


CONCEPTS = {
    'import': ('导入与模块', '导入让当前代码能够使用另一个模块中的名字。对照这里的模块路径和被使用的名字。'),
    'return': ('返回值', '返回值是一次函数调用交给调用方的结果；它与终端打印的内容可能不同。'),
    'class ': ('类与实例', '类定义一类对象的行为；实例保存具体对象的状态。沿构造和方法调用核对。'),
    'with ': ('上下文管理', 'with 将一段操作放在进入、退出的边界内；具体资源行为需要查看对象实现。'),
    'async ': ('异步调用', '异步函数的执行与普通同步调用不同；查看调用处是否等待结果。'),
}


def tasks(record, files=None):
    guide = record['guide']
    result = []
    symbols = [(path, symbol) for path, item in (files or {}).items() if PurePosixPath(path).suffix not in {'.md', '.rst', '.txt', '.markdown'}
               for symbol in outline(path, item['text'])]
    for step in guide['steps']:
        refs = step.get('evidence', [])
        key = digest([record.get('snapshot_id'), record.get('guide_revision', 1), guide['mode'], step['id'], step['title'], step['action'], step['checkpoint'], refs])
        text = '\n'.join(excerpt(files or {}, ref) for ref in refs)
        concepts = [{'title': title, 'detail': detail, 'evidence': refs} for token, (title, detail) in CONCEPTS.items() if token in text][:4]
        result.append(dict(step, key=key,
                           where=step.get('location') or '；'.join(f"{r['path']} · 第 {r['start_line']}–{r['end_line']} 行" for r in refs) or '从项目文件定位相关文档。',
                           prerequisites=step.get('prerequisites', guide.get('prerequisites', []))[:3],
                           implementations=[{'title': symbol['title'], 'evidence': [{'path': path, 'start_line': symbol['line'], 'end_line': symbol['end_line']}]}
                                            for path, symbol in symbols if re.search(r'\b'+re.escape(symbol['title'])+r'\s*\(', text)][:6],
                           expected=step['checkpoint'],
                           actions=[{'title': '定位与准备', 'detail': '打开引用，核对运行环境和原文前提；原文没有说明的工作目录或输出需要进一步确认。'},
                                    {'title': '完成当前操作', 'detail': step['action']},
                                    {'title': '观察与记录', 'detail': step['checkpoint']}],
                           concepts=concepts,
                           exercises=[
                               {'id': 'predict', 'title': '先预测，再对照', 'prompt': '根据当前原文，预测这一操作会返回、输出或改变什么。若原文不足以确定，请写出缺少的信息。'},
                               {'id': 'change', 'title': '只改变一个条件', 'prompt': '选择原文中的一个输入或配置，写出你准备怎样改变它、预期差异以及核对方法。不要修改原项目。'},
                               {'id': 'explain', 'title': '用自己的话解释', 'prompt': '选出原文中两行或两个操作，解释它们如何衔接、各自使用了什么输入。'}]))
    return result


def journal_text(record, workspace):
    lines = [record['name']+' · 学习记录', '目标：'+record['goal'], '', '完成状态由用户记录；练习反馈不是独立掌握证明。']
    for route in workspace['routes'].values():
        lines += ['', f"路线版本 {route['id']} · {route['mode']}"]
        lines += [f"- {s['title']}" for s in route['steps']]
    for note in workspace['notes'].values():
        lines += ['', '笔记：'+note['title'], note['text']]
        lines += [f"引用：{r['path']}:{r['start_line']}–{r['end_line']}" for r in note.get('evidence', [])]
    for item in workspace['discussions']:
        lines += ['', ('练习' if item['intent'] == 'feedback' else '问题')+'：'+item['question'],
                  '状态：'+('已解决' if item.get('resolved') else '待回顾'),
                  '反馈来源：'+item['response']['origin'], item['response']['answer']]
        lines += ['下一步：'+s['text'] for s in item['response'].get('next_actions', [])]
        lines += [f"引用：{r['path']}:{r['start_line']}–{r['end_line']}" for r in item['response'].get('evidence', [])]
        lines += ['仍需确认：'+s for s in item['response'].get('uncertainties', [])]
        if item.get('error'):
            lines += ['运行环境：'+item['environment'], '命令：'+item['command'], '报错：'+item['error']]
    for item in workspace.get('run_checks', []):
        run = item['execution']
        lines += ['', '实际隔离执行：'+item['title'], '状态：'+run['status'], item['note'],
                  '提交代码：', item['code'], '标准输出：', run['stdout'], '错误输出：', run['stderr']]
    lines += ['', '路线调整记录（含撤销）：']
    lines += [f"{event['at']} · {event['title']} · {event['action']}" for event in workspace['events']]
    return '\n'.join(lines)
