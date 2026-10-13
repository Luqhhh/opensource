"""Curate exact upstream bytes and declared adapters; never execute upstream on host."""
import ast
import doctest
import hashlib
import json
from pathlib import Path
import shutil
import textwrap

ROOT = Path(__file__).resolve().parent


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(name, repo, versions, license_name):
    root = ROOT / name
    root.mkdir(exist_ok=True)
    provenance = {'schema_version': 1, 'repository': repo, 'files': [], 'extractions': [],
                  'source_mappings': {}, 'version_commits': {}}
    for version, collection in versions.items():
        checkout = ROOT / 'collection' / name / collection
        commit = (checkout / 'commit.txt').read_text().strip()
        provenance['version_commits'][version] = commit
        selected = [p for p in checkout.rglob('*.py')
                    if p.relative_to(checkout).parts[0] in ('src', 'mistune.py')]
        selected.extend(p for p in checkout.glob('LICENSE*') if p.is_file())
        if name == 'mistune':
            selected.extend(p for p in [checkout / 'README.rst', checkout / 'docs/index.rst'] if p.exists())
        else:
            selected.extend([checkout / 'docs/urls.rst', checkout / 'docs/wsgi.rst'])
        mappings = {}
        for source in sorted(set(selected)):
            relative = source.relative_to(checkout).as_posix()
            dest = root / 'upstream' / version / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
            provenance['files'].append({'local_path': dest.relative_to(root).as_posix(),
                                       'upstream_path': relative, 'version': version,
                                       'commit': commit, 'sha256': sha(source.read_bytes()),
                                       'url': f'{repo}/blob/{commit}/{relative}'})
            if source.suffix == '.py' and (relative.startswith('src/') or relative == 'mistune.py'):
                runtime_name = relative.removeprefix('src/')
                mappings[runtime_name] = dest.relative_to(root).as_posix()
        provenance['source_mappings'][version] = mappings
    old, target = list(versions)
    if name == 'mistune':
        dependency = ROOT / 'collection/typing_extensions/4.12.2'
        commit = (dependency / 'commit.txt').read_text().strip()
        for relative in ['src/typing_extensions.py', 'LICENSE']:
            source = dependency / relative
            dest = root / 'upstream/dependencies/typing_extensions-4.12.2' / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
            provenance['files'].append({'local_path': dest.relative_to(root).as_posix(),
                                       'upstream_path': relative, 'version': 'typing_extensions 4.12.2',
                                       'commit': commit, 'sha256': sha(source.read_bytes()),
                                       'url': f'https://github.com/python/typing_extensions/blob/{commit}/{relative}'})
            if relative.endswith('.py'):
                for version in versions:
                    provenance['source_mappings'][version][relative.removeprefix('src/')] = dest.relative_to(root).as_posix()
    if name == 'werkzeug':
        # Upstream Werkzeug imports MarkupSafe. Pin the same Python fallback for
        # both versions; the selected cases do not test MarkupSafe migrations.
        dependency = ROOT.parents[1] / 'real_projects/markupsafe/upstream/2.1.5'
        for relative in ['src/markupsafe/__init__.py', 'src/markupsafe/_native.py', 'LICENSE.rst']:
            source = dependency / relative
            dest = root / 'upstream/dependencies/markupsafe-2.1.5' / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
            commit = 'fbba4acd0312826cec9cfe18371c7df07962cb65'
            provenance['files'].append({'local_path': dest.relative_to(root).as_posix(),
                                       'upstream_path': relative, 'version': 'MarkupSafe 2.1.5',
                                       'commit': commit, 'sha256': sha(source.read_bytes()),
                                       'url': f'https://github.com/pallets/markupsafe/blob/{commit}/{relative}'})
            if relative.endswith('.py'):
                for version in versions:
                    provenance['source_mappings'][version][relative.removeprefix('src/')] = dest.relative_to(root).as_posix()
    for runtime_name, source in provenance['source_mappings'][target].items():
        dest = root / runtime_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((root / source).read_bytes())
    config = {'documents': [], 'source_files': sorted(provenance['source_mappings'][target]),
              'timeout_seconds': 5, 'examples': {}}
    metadata = {'schema_version': 1, 'suite_id': f'{name}-semantic-v2-independent-holdout',
                'split': 'holdout_v2',
                'selection': {'held_out_from_method_optimization': True,
                              'model_calls_during_preparation': 0,
                              'sampling': 'purposive, independent collector; not random and not double-blind',
                              'boundary_disclosure': 'Collector accidentally saw generic SYSTEM_V2 additions while reading the existing FileProvider interface after selecting projects and cases; root did not see concrete cases or references before method lock. No model output or retrieval implementation was inspected.'},
                'classification': 'real_upstream_documentation_version_migration',
                'documentation_version': old, 'runtime_version': target,
                'version_commits': provenance['version_commits'],
                'license': license_name, 'cases': [],
                'scope': 'Purposive historical migration, not a current upstream documentation defect. No model calls during preparation.',
                'oracle_limit': 'Finite evaluator-owned tests establish the declared contract on selected inputs, not unrestricted semantic equivalence.'}
    return root, provenance, config, metadata


def add_case(pack, slug, relative, lines, code, context, checks, stdout, status,
             normalization, setup='', reference=None, negative=None, function=None):
    root, provenance, config, metadata = pack
    old = metadata['documentation_version']
    raw_source = root / 'upstream' / old / relative
    raw = b''.join(raw_source.read_bytes().splitlines(keepends=True)[lines[0]-1:lines[1]])
    raw_path = root / 'raw-snippets' / (slug + raw_source.suffix)
    raw_path.parent.mkdir(exist_ok=True)
    raw_path.write_bytes(raw)
    commit = provenance['version_commits'][old]
    link = f'{provenance["repository"]}/blob/{commit}/{relative}#L{lines[0]}-L{lines[1]}'
    document = f'# {slug.replace("_", " ")}\n\nHistorical upstream example: {link}\n\n{context}\n\n```python\n{code}```\n'
    path = 'cases/' + slug + '.md'
    dest = root / path
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(document)
    key = path + '#1'
    spec = {'expected_stdout': stdout, 'checks': checks}
    if setup:
        spec['setup'] = setup
    config['documents'].append(path)
    config['examples'][key] = spec
    extraction = {'case_id': key, 'source': raw_source.relative_to(root).as_posix(),
                  'line_range': lines, 'raw_snippet': raw_path.relative_to(root).as_posix(),
                  'raw_sha256': sha(raw), 'derived_document': path,
                  'document_sha256': sha(document.encode()), 'code_sha256': sha(code.encode()),
                  'normalization': normalization, 'function': function}
    provenance['extractions'].append(extraction)
    metadata['cases'].append({'id': key, 'expected_before': status,
                              'expected_repair': 'verified_repair' if status == 'failed' else 'checked',
                              'upstream_document': link, 'semantic_contract': context,
                              'category': 'historical_migration' if status == 'failed' else 'healthy_control'})
    return key, reference, negative


def docstring_case(source, function):
    text = source.read_text()
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == function)
    doc = node.body[0]
    code, outputs = [], []
    for ex in doctest.DocTestParser().get_examples(ast.get_docstring(node)):
        if ex.want:
            assert isinstance(ast.parse(ex.source).body[0], ast.Expr)
            code.append('print(repr(' + ex.source.strip() + '))\n')
            outputs.append(ex.want)
        else:
            code.append(ex.source)
    return [doc.lineno, doc.end_lineno], ''.join(code), ''.join(outputs)


def save(pack, candidates):
    root, provenance, config, metadata = pack
    dump(root / 'exampleproof.json', config)
    dump(root / 'metadata.json', metadata)
    dump(root / 'provenance.json', provenance)
    for field, index in [('proposals.json', 1), ('negative_proposals.json', 2)]:
        dump(root / field, {row[0]: {'code': row[index], 'rationale':
                                  'Evaluator-authored reference replay, not model output.' if index == 1 else
                                  'Deliberately incorrect constant/scope/output-only candidate for oracle validation.'}
                                  for row in candidates if row[index] is not None})


def main():
    mistune = prepare('mistune', 'https://github.com/lepture/mistune',
                      {'0.8.4': 'v0.8.4', '3.1.3': 'v3.1.3'}, 'BSD-3-Clause')
    root = mistune[0]
    readme = (root / 'upstream/0.8.4/README.rst').read_text().splitlines(keepends=True)
    checks = '''assert callable(markdown)
for _text, _expected in [('', ''), ('plain', '<p>plain</p>\\n'),
                         ('**bold**', '<p><strong>bold</strong></p>\\n'),
                         ('*em*', '<p><em>em</em></p>\\n'),
                         ('你好', '<p>你好</p>\\n'),
                         ('a\\nb', '<p>a\\nb</p>\\n'),
                         ('<b>x</b>', '<p><b>x</b></p>\\n')]:
    _actual = markdown(_text)
    assert type(_actual) is str
    assert _actual == _expected
assert markdown('plain') == markdown('plain')
'''
    code = textwrap.dedent(''.join(readme[69:73]))
    rows = [add_case(mistune, 'reusable_html', 'README.rst', [70, 73], code,
                    'Reuse the callable named markdown to render Markdown to an HTML string. '
                    'Preserve the old default behavior: raw HTML is retained and ordinary newlines remain soft. '
                    'The original expression is silent in a script. External checks cover empty text, emphasis, Unicode, raw HTML, and repeated calls.',
                    checks, '', 'failed', {'kind': 'dedent_code_block', 'imports_added': []},
                    reference=code.replace('mistune.Markdown()', 'mistune.create_markdown(escape=False)'),
                    negative="import mistune\nmarkdown = lambda text: '<p>I am using <strong>mistune markdown parser</strong></p>\\n'\nmarkdown('I am using **mistune markdown parser**')\n")]
    code = textwrap.dedent(''.join(readme[86:90]))
    hard_checks = '''assert callable(markdown)
for _text, _expected in [('', ''), ('a\\nb', '<p>a<br>\\nb</p>\\n'),
                         ('<b>x</b>', '<p>&lt;b&gt;x&lt;/b&gt;</p>\\n'),
                         ('**bold**', '<p><strong>bold</strong></p>\\n'),
                         ('你好\\n世界', '<p>你好<br>\\n世界</p>\\n'),
                         ('a & b', '<p>a &amp; b</p>\\n')]:
    _actual = markdown(_text)
    assert type(_actual) is str
    assert _actual == _expected
assert markdown(text) == '<p>&lt;b&gt;x&lt;/b&gt;<br>\\nnext</p>\\n'
'''
    rows.append(add_case(mistune, 'renderer_options', 'README.rst', [87, 90], code,
                        'Setup supplies import mistune and text = "<b>x</b>\\nnext" for the upstream placeholder. '
                        'Retain the reusable callable markdown. It must render HTML, escape raw HTML, and use hard line breaks. '
                        'Preserve the original HTML <br> style and silent expression; checks cover other text and boundary inputs.',
                        hard_checks, '', 'failed', {'kind': 'dedent_code_block', 'imports_added': []},
                        setup="import mistune\ntext = '<b>x</b>\\nnext'\n",
                        reference="renderer = mistune.HTMLRenderer(escape=True)\n_parser = mistune.Markdown(renderer=renderer, inline=mistune.InlineParser(hard_wrap=True))\nmarkdown = lambda value: _parser(value).replace('<br />', '<br>')\nmarkdown(text)\n",
                        negative="markdown = mistune.create_markdown(escape=True, hard_wrap=False)\nmarkdown(text)\n"))
    code = textwrap.dedent(''.join(readme[60:64]))
    rows.append(add_case(mistune, 'simple_html', 'README.rst', [61, 64], code,
                        'Render the supplied Markdown as HTML using the documented convenience function. '
                        'The expression is silent in a script. Checks cover empty input, plain text, emphasis, Unicode and escaping.',
                        "assert mistune.markdown('') == ''\nassert mistune.markdown('**x**') == '<p><strong>x</strong></p>\\n'\nassert mistune.markdown('plain') == '<p>plain</p>\\n'\nassert mistune.markdown('你好') == '<p>你好</p>\\n'\nassert mistune.markdown('<b>x</b>', escape=True) == '<p>&lt;b&gt;x&lt;/b&gt;</p>\\n'\n",
                        '', 'checked', {'kind': 'dedent_code_block', 'imports_added': []}))
    save(mistune, rows)

    werkzeug = prepare('werkzeug', 'https://github.com/pallets/werkzeug',
                       {'2.2.3': '2.2.3', '3.0.6': '3.0.6'}, 'BSD-3-Clause')
    root = werkzeug[0]
    rows = []
    pop_prefix = '''pop_path_info = lambda environ, charset='utf-8', errors='replace': (None if not environ.get('PATH_INFO') else (lambda path, script: (lambda leading, head, separator, tail: (environ.update({'PATH_INFO': '/' + tail if separator else '', 'SCRIPT_NAME': script + leading + head}), head.encode('latin1').decode(charset, errors) if charset is not None else head.encode('latin1'))[1])('/' * (len(path) - len(path.lstrip('/'))), *path.lstrip('/').partition('/')))(environ['PATH_INFO'], environ.get('SCRIPT_NAME', '')))
'''
    pop_checks = '''assert callable(pop_path_info)
assert env == {'SCRIPT_NAME': '/foo/a/b', 'PATH_INFO': ''}
for _initial, _result, _after in [
    ({'SCRIPT_NAME': '/app', 'PATH_INFO': '/x/y'}, 'x', {'SCRIPT_NAME': '/app/x', 'PATH_INFO': '/y'}),
    ({'SCRIPT_NAME': '/app', 'PATH_INFO': ''}, None, {'SCRIPT_NAME': '/app', 'PATH_INFO': ''}),
    ({'PATH_INFO': '/'}, '', {'SCRIPT_NAME': '/', 'PATH_INFO': ''}),
    ({'SCRIPT_NAME': '/app', 'PATH_INFO': '//x//y'}, 'x', {'SCRIPT_NAME': '/app//x', 'PATH_INFO': '//y'}),
    ({'PATH_INFO': '/cafÃ©/next'}, 'café', {'SCRIPT_NAME': '/cafÃ©', 'PATH_INFO': '/next'}),
    ({'PATH_INFO': '/x', 'keep': 7}, 'x', {'SCRIPT_NAME': '/x', 'PATH_INFO': '', 'keep': 7}),
    ({'keep': 7}, None, {'keep': 7})]:
    _environment = dict(_initial)
    assert pop_path_info(_environment) == _result
    assert _environment == _after
_environment = {'PATH_INFO': '/cafÃ©'}
assert pop_path_info(_environment, charset=None) == b'caf\\xc3\\xa9'
'''
    peek_prefix = "peek_path_info = lambda environ, charset='utf-8', errors='replace': (lambda value: value.decode(charset, errors) if charset is not None else value)(environ.get('PATH_INFO', '').lstrip('/').split('/', 1)[0].encode('latin1'))\n"
    peek_checks = '''assert callable(peek_path_info)
assert env == {'SCRIPT_NAME': '/foo', 'PATH_INFO': '/a/b'}
for _initial, _expected in [({}, ''), ({'PATH_INFO': ''}, ''), ({'PATH_INFO': '/'}, ''),
                             ({'PATH_INFO': '/x/y'}, 'x'), ({'PATH_INFO': '//x//y'}, 'x'),
                             ({'PATH_INFO': '/cafÃ©/y', 'keep': 7}, 'café')]:
    _environment = dict(_initial)
    assert peek_path_info(_environment) == _expected
    assert peek_path_info(_environment) == _expected
    assert _environment == _initial
assert peek_path_info({'PATH_INFO': '/cafÃ©'}, charset=None) == b'caf\\xc3\\xa9'
'''
    for name, prefix, checks, contract, negative in [
        ('pop_path_info', pop_prefix, pop_checks,
         'Keep the reusable callable pop_path_info. Remove and return the next path segment while moving its original WSGI bytes from PATH_INFO to SCRIPT_NAME. Preserve repeated slashes, unrelated keys, empty-path behavior, UTF-8 decoding, and charset=None bytes; retain the upstream printed results.',
         "from wsgiref.util import shift_path_info as pop_path_info\n"),
        ('peek_path_info', peek_prefix, peek_checks,
         'Keep the reusable callable peek_path_info. Return the next decoded segment without mutating the environment, including repeated calls and slashes. Preserve the pinned implementation boundary behavior: empty paths return an empty string; charset=None returns bytes. Retain the upstream printed results.',
         "peek_path_info = lambda environ, **kwargs: 'a'\n")]:
        relative = 'src/werkzeug/wsgi.py'
        lines, body, stdout = docstring_case(root / 'upstream/2.2.3' / relative, name)
        code = f'from werkzeug.wsgi import {name}\n' + body
        rows.append(add_case(werkzeug, name, relative, lines, code, contract, checks, stdout,
                             'failed', {'kind': 'docstring_doctest_repr', 'imports_added': [f'from werkzeug.wsgi import {name}']},
                             function=name, reference=prefix+body, negative=negative+body))
    relative = 'src/werkzeug/urls.py'
    lines, body, stdout = docstring_case(root / 'upstream/2.2.3' / relative, 'iri_to_uri')
    rows.append(add_case(werkzeug, 'iri_to_uri', relative, lines,
                        'from werkzeug.urls import iri_to_uri\n'+body,
                        'Retain the reusable iri_to_uri callable. Convert Unicode hostnames and paths to URI form while preserving existing percent escapes; retain doctest output.',
                        "assert iri_to_uri('https://example.com/a b') == 'https://example.com/a%20b'\nassert iri_to_uri('https://例子.test/你好') == 'https://xn--fsqu00a.test/%E4%BD%A0%E5%A5%BD'\nassert iri_to_uri('') == ''\nassert iri_to_uri('/already%20quoted') == '/already%20quoted'\n",
                        stdout, 'checked', {'kind': 'docstring_doctest_repr', 'imports_added': ['from werkzeug.urls import iri_to_uri']}, function='iri_to_uri'))
    save(werkzeug, rows)


if __name__ == '__main__':
    main()
