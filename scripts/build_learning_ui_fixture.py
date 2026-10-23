"""Build a standalone synthetic browser check; no network/model/project execution.

Run from the checkout: python3 scripts/build_learning_ui_fixture.py --output /tmp/exampleproof-ui
Open index.html in a browser. Use ?preview=1 to inspect without running interactions.
"""
import argparse
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from exampleproof.learn_server import LearningApp


def build(output):
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError('Write browser fixtures outside the source checkout.')
    files = {'README.md': '# Example\n\n学习如何用函数处理输入，并检查返回结果。\n\n## Install\n\nPython 3.10 or later.\n\n## Usage\n\n```python\nfrom example import run\nresult = run(3)\nprint(result)\n```\n',
             'example.py': 'def run(value):\n    """Return twice the input."""\n    return value * 2\n'}
    files['reader-demo.js'] = ('// 阅读区合成样例，不执行\n'
                               'export function greet(name) {\n'
                               '    /* 注释第一行\n'
                               '       return 仍然是注释 */\n'
                               '    const message = `你好，${name}`;\n'
                               '    const count = 42;\n'
                               '    return message;\n'
                               '}\n\n'
                               'const escaped = "<img src=x onerror=alert(1)>";\n'
                               'const longLine = "' + 'code / ' * 70 + '";\n')
    files['README.md'] += '\n```js\n/* first\nreturn false\n*/\nconst value = 42;\n```\n'
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w') as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    with tempfile.TemporaryDirectory() as temp:
        app = LearningApp(temp, 'none')
        try:
            created = app.create(name='示例项目 · 合成交互检查', goal='理解输入与返回值，完成第一个调用', level='beginner', upload=raw.getvalue())
            for _ in range(300):
                record = app.read(created['id'])
                if record['status'] == 'ready':
                    break
                time.sleep(.01)
            else:
                raise RuntimeError('Fixture import failed')
            workspace = app.workspace.view(record['id'])
            step = workspace['tasks'][0]
            base = {'route_id': workspace['route_id'], 'step_key': step['key']}
            for index in range(14):
                app.workspace.prepare(record['id'], base | {'intent': 'ask', 'question': f'合成问题 {index+1}：如何检查输入与返回值？', 'use_ai': False})
            app.workspace.mutate(record['id'], base | {'action': 'position', 'reader': None, 'history': []})
            workspace = app.workspace.view(record['id'])
            fixture = {'record': app.public(record), 'workspace': workspace, 'files': files}
        finally:
            app.pool.shutdown()
    web = ROOT/'exampleproof/learner_web'
    html = (web/'index.html').read_text()
    html = re.sub(r'<link[^>]+>|<script[^>]+></script>', '', html)
    styles = '\n'.join((web/name).read_text() for name in ('app.css', 'study.css'))
    scripts = ['window.UI_FIXTURE='+json.dumps(fixture, ensure_ascii=False)+';',
               (ROOT/'tests/browser_learning_ui.js').read_text(),
               (web/'app.js').read_text(), (web/'code_highlight.js').read_text(), (web/'study.js').read_text()]
    html = html.replace('</head>', '<style>'+styles+'</style></head>')
    for script in scripts:
        html = html.replace('</body>', '<script>'+script.replace('</script', '<\\/script')+'</script></body>')
    output.mkdir(parents=True, exist_ok=True)
    (output/'index.html').write_text(html)
    for width in (320, 390, 768, 1024, 1440):
        # srcdoc gives a precise CSS viewport even when the host browser imposes
        # a minimum top-level window width. All data remains synthetic/local.
        embedded = json.dumps(html, ensure_ascii=False).replace('<', '\\u003c')
        wrapper = ('<!doctype html><meta charset="utf-8"><title>Synthetic UI viewport</title>'
                   '<style>body{margin:0}iframe{display:block;border:0;width:'+str(width)+'px;height:1100px}#ui-check-result{white-space:pre-wrap}</style>'
                   '<iframe title="合成界面检查"></iframe><pre id="ui-check-result">RUNNING</pre><script>'
                   'const frame=document.querySelector("iframe");frame.srcdoc='+embedded+';'
                   'const poll=setInterval(()=>{const result=frame.contentDocument?.querySelector("#ui-check-result");'
                   'if(result&&result.textContent!=="RUNNING"){document.querySelector("#ui-check-result").textContent=result.textContent;clearInterval(poll)}},50);'
                   '</script>')
        (output/('viewport-'+str(width)+'.html')).write_text(wrapper)
    print(output/'index.html')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
