"""Create evaluator-authored development cases without touching v1 evidence.

This one-time authoring script refuses existing project directories. Execution
of copied upstream snippets is handled separately by validate.py in Bubblewrap.
"""

import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[2]
ORIGIN = REPOSITORY / "benchmarks/real_projects"
PROJECTS = ("tinydb", "more_itertools", "markupsafe")


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def document(path, title, contract, code):
    path.write_text(f"# {title}\n\nEvaluator-authored development_v2 adaptation; not a newly held-out upstream example.\n{contract}\n\n```python\n{code}```\n")


def main():
    if any((ROOT / name).exists() for name in PROJECTS):
        raise ValueError("Project directories already exist; authoring never overwrites evidence")
    for name in PROJECTS:
        original, root = ORIGIN / name, ROOT / name
        root.mkdir()
        for directory in (name, "upstream", "cases", "original", "original_snippets"):
            if (original / directory).is_dir():
                shutil.copytree(original / directory, root / directory)
        shutil.copytree(original / "cases", root / "origin_cases")
        shutil.copyfile(original / "provenance.json", root / "upstream-provenance.json")
        for filename in ("exampleproof.json", "proposals.json"):
            shutil.copyfile(original / filename, root / filename)

    root = ROOT / "tinydb"
    config = json.loads((root / "exampleproof.json").read_text())
    proposals = json.loads((root / "proposals.json").read_text())
    defaults = "cases/purge_default.md#1"
    named = "cases/purge_named_table.md#1"
    archive = {"1": {"value": "keep"}, "4": {"value": "归档<&>", "nested": [0, False, None]}, "9": {"value": ""}}
    default_fixture = {"archive": archive, "empty_archive": {}, "_default": {"3": {"type": "seed", "count": 0}, "10": {"type": "种子", "count": None}}}
    named_fixture = {"archive": archive, "empty_archive": {}, "table_name": {"2": {"value": False}, "7": {"value": None}, "11": {"value": "标签<&>"}}}
    for key, fixture in ((defaults, default_fixture), (named, named_fixture)):
        config["examples"][key]["setup"] = "import json\nwith open('db.json', 'w') as _fixture:\n    json.dump(" + repr(fixture) + ", _fixture)\n"
    default_code = (root / "origin_cases/purge_default.md").read_text().split("```python\n")[1].split("```")[0].replace("db.purge()", "clear_default = db.purge\nclear_default()")
    named_code = (root / "origin_cases/purge_named_table.md").read_text().split("```python\n")[1].split("```")[0].replace("db.purge_table('table_name')", "drop_named = db.purge_table\ndrop_named('table_name')")
    document(root / "cases/purge_default.md", "Clear default records and retain unrelated tables", "Keep db and a reusable zero-argument clear_default callable bound to this database. Clear only default-table records, retaining the default table and named archive/empty_archive tables and data. The fixture contains pre-existing records including Unicode, empty strings, false and null. Repeated calls on empty and refilled tables must work, reset IDs to 1, invalidate cached searches, and persist after reopen. Emit no stdout.", default_code)
    document(root / "cases/purge_named_table.md", "Drop one named table and preserve other records", "Keep db and a reusable drop_named(name) callable bound to this database. Remove only the requested named table and its records; preserve default, archive and empty_archive tables and data. Handle missing/empty tables and repeated calls, invalidate table caches so recreation starts at ID 1, and persist after reopen. The fixture includes multiple Unicode/false/null records. Emit no stdout.", named_code)
    archive_assert = "assert db.storage.read()['archive'] == " + repr(archive) + "\nassert db.storage.read()['empty_archive'] == {}\n"
    config["examples"][defaults]["checks"] = """assert callable(clear_default)
assert db.all() == []
assert len(db) == 0
assert db.tables() == {'_default', 'archive', 'empty_archive'}
assert db.storage.read()['_default'] == {}
""" + archive_assert + """clear_default()
assert db.insert({'type': 'edge', 'count': 0, 'data': [False, None, '', '汉字<&>']}) == 1
assert db.search(Query().type == 'edge') == [{'type': 'edge', 'count': 0, 'data': [False, None, '', '汉字<&>']}]
assert db.insert({'type': 'edge', 'count': -1}) == 2
clear_default()
assert db.search(Query().type == 'edge') == []
assert db.all() == []
clear_default()
assert db.insert({'type': 'new', 'count': 2}) == 1
""" + archive_assert + """db.close()
_reopened = TinyDB('db.json')
assert _reopened.all() == [{'type': 'new', 'count': 2}]
assert _reopened.tables() == {'_default', 'archive', 'empty_archive'}
assert _reopened.storage.read()['archive'] == """ + repr(archive) + "\n_reopened.close()\n"
    config["examples"][named]["checks"] = """assert callable(drop_named)
assert db.tables() == {'_default', 'archive', 'empty_archive'}
assert db.all() == [{'type': 'apple', 'count': 7}, {'type': 'peach', 'count': 3}]
assert 'table_name' not in db.storage.read()
""" + archive_assert + """drop_named('table_name')
drop_named('never_created')
_table = db.table('table_name')
assert _table.all() == []
assert _table.insert({'value': None}) == 1
assert _table.insert({'value': '第二条<&>'}) == 2
assert _table.search(Query().value == None) == [{'value': None}]
drop_named('table_name')
assert 'table_name' not in db.storage.read()
assert db.table('table_name').insert({'value': False}) == 1
assert db.table('table_name').all() == [{'value': False}]
drop_named('table_name')
db.table('empty_to_drop').insert({'temporary': True})
db.table('empty_to_drop').remove(Query().temporary == True)
drop_named('empty_to_drop')
assert 'empty_to_drop' not in db.storage.read()
assert db.tables() == {'_default', 'archive', 'empty_archive'}
assert db.all() == [{'type': 'apple', 'count': 7}, {'type': 'peach', 'count': 3}]
""" + archive_assert + """db.close()
_reopened = TinyDB('db.json')
assert _reopened.tables() == {'_default', 'archive', 'empty_archive'}
assert _reopened.all() == [{'type': 'apple', 'count': 7}, {'type': 'peach', 'count': 3}]
_reopened.close()
"""
    for key, code, old, new in ((defaults, default_code, "db.purge", "db.truncate"), (named, named_code, "db.purge_table", "db.drop_table")):
        proposals[key] = {"code": code.replace(old, new), "rationale": "Evaluator-authored reference replay; no model inference."}
    negatives = {
        "wrong_scope": {defaults: {"code": default_code.replace("db.purge", "db.drop_tables"), "rationale": "Wrong scope: removes archive tables."}, named: {"code": named_code.replace("db.purge_table", "lambda name: db.truncate()"), "rationale": "Wrong scope: clears default records instead of dropping requested table."}},
        "single_use": {defaults: {"code": default_code.replace("clear_default = db.purge\nclear_default()", "clear_default = lambda: None\ndb.truncate()"), "rationale": "Matches first operation but reusable callable does nothing."}, named: {"code": named_code.replace("drop_named = db.purge_table\ndrop_named('table_name')", "drop_named = lambda name: None\ndb.drop_table('table_name')"), "rationale": "Matches first operation but cannot remove later records."}},
    }
    dump(root / "exampleproof.json", config)
    dump(root / "proposals.json", proposals)
    dump(root / "negative_proposals.json", negatives)

    root = ROOT / "more_itertools"
    config = json.loads((root / "exampleproof.json").read_text())
    key = "cases/collate.md#1"
    collate_code = (root / "origin_cases/collate.md").read_text().split("```python\n")[1].split("```")[0]
    document(root / "cases/collate.md", "Reusable lazy sorted merge", "Preserve a reusable callable named collate and all three displayed outputs. Merge any number of already-sorted iterables, retaining duplicates and stable order for equal keys, accepting key and reverse together. Support empty inputs, Unicode and one-shot iterators. Preserve lazy iteration: do not consume inputs at construction or read the entire input to return a prefix. These evaluator-authored requirements expand the original documented lazy merge contract.", collate_code)
    config["examples"][key]["checks"] += """assert callable(collate)
assert list(collate()) == []
assert list(collate(iter([0, 0, 2]), iter([-1, 0, 3]), iter([]))) == [-1, 0, 0, 0, 2, 3]
assert list(collate(iter(['é', '界']), iter(['ñ', '汉']))) == ['é', 'ñ', '汉', '界']
assert list(collate(['20', '3', '-1'], ['12', '2'], key=int, reverse=True)) == ['20', '12', '3', '2', '-1']
_left = [(1, 'left-a'), (1, 'left-b'), (3, 'left-c')]
_right = [(1, 'right-a'), (2, 'right-b')]
assert list(collate(iter(_left), iter(_right), key=lambda item: item[0])) == [(1, 'left-a'), (1, 'left-b'), (1, 'right-a'), (2, 'right-b'), (3, 'left-c')]
_seen = []
def _stream(start):
    for value in range(start, 100, 2):
        _seen.append(value)
        yield value
_merged = collate(_stream(0), _stream(1))
assert _seen == [], 'merge must not consume the inputs before iteration'
assert next(_merged) == 0
assert next(_merged) == 1
assert len(_seen) <= 4, 'merge must consume only a bounded prefix'
from itertools import islice, count
assert list(islice(collate(count(0, 2), count(1, 2)), 8)) == list(range(8))
"""
    eager = collate_code.replace("from more_itertools import collate", "from itertools import chain\ncollate = lambda *inputs, key=None, reverse=False: iter(sorted(chain.from_iterable(inputs), key=key, reverse=reverse))")
    dropdups = collate_code.replace("from more_itertools import collate", "from heapq import merge\nfrom itertools import groupby\ncollate = lambda *inputs, **options: (key for key, group in groupby(merge(*inputs, **options)))")
    negatives = {"eager_merge": {key: {"code": eager, "rationale": "Displayed values match but eager sorting violates lazy merge."}}, "drops_duplicates": {key: {"code": dropdups, "rationale": "Wrongly removes repeated values."}}}
    dump(root / "exampleproof.json", config)
    dump(root / "negative_proposals.json", negatives)

    root = ROOT / "markupsafe"
    config = json.loads((root / "exampleproof.json").read_text())
    proposals = json.loads((root / "proposals.json").read_text())
    new_id = "cases/convert_contract.md#1"
    code = "from markupsafe import escape, soft_unicode\nconvert = soft_unicode\nvalue = escape('<User 1>')\nprint(repr(escape(convert(value))))\n"
    document(root / "cases/convert_contract.md", "Reusable soft conversion without HTML escaping", "Keep a reusable callable named convert that converts non-strings with str(), preserves existing str/str-subclass/Markup objects by identity, and performs no HTML escaping. Cover ordinary/empty/Unicode/HTML-sensitive strings, numbers, booleans, None and objects defining __str__ or __html__. The displayed escaped Markup must remain Markup('&lt;User 1&gt;'). This authored binding task expands the upstream soft-conversion contract; it is not a mechanical excerpt.", code)
    config["documents"].insert(1, "cases/convert_contract.md")
    config["examples"][new_id] = {"expected_stdout": "Markup('&lt;User 1&gt;')\n", "checks": """from markupsafe import Markup as _Markup
assert callable(convert)
for _text in ['ordinary text', '', '<tag>&' + chr(34) + chr(39), '中文🙂é', 'already &lt;escaped&gt;']:
    _converted = convert(_text)
    assert type(_converted) is str
    assert _converted is _text, 'existing strings must preserve identity'
for _safe in [_Markup(''), _Markup('<b>&safe</b>'), _Markup('&lt;escaped&gt;')]:
    assert convert(_safe) is _safe, 'Markup must retain type and identity'
class _Text(str):
    pass
_subclass = _Text('<still text>')
assert convert(_subclass) is _subclass
for _input, _expected in [(0, '0'), (-42, '-42'), (1.25, '1.25'), (True, 'True'), (False, 'False'), (None, 'None')]:
    _converted = convert(_input)
    assert type(_converted) is str
    assert _converted == _expected
class _Object:
    def __str__(self):
        return '<object>&'
    def __html__(self):
        return '<em>different HTML</em>'
_converted = convert(_Object())
assert type(_converted) is str
assert _converted == '<object>&', 'soft conversion uses str, not __html__ or HTML escaping'
assert convert(value) is value
"""}
    proposals[new_id] = {"code": code.replace("soft_unicode", "soft_str"), "rationale": "Evaluator-authored reference replay of the documented soft conversion replacement; no model inference."}
    negatives = {
        "escape_instead_of_convert": {new_id: {"code": code.replace("escape, soft_unicode", "escape").replace("convert = soft_unicode", "convert = escape"), "rationale": "Earlier experiment's escape-style repair preserves the displayed safe value but wrongly escapes ordinary strings."}},
        "none_as_empty": {new_id: {"code": code.replace("soft_unicode", "soft_str").replace("convert = soft_str", "convert = lambda item: '' if item is None else soft_str(item)"), "rationale": "Incorrectly treats None as optional empty text."}},
        "markup_identity_lost": {new_id: {"code": code.replace("escape, soft_unicode", "escape, Markup, soft_str").replace("convert = soft_unicode", "convert = lambda item: Markup(item) if isinstance(item, Markup) else soft_str(item)"), "rationale": "Values and type match but Markup identity is unnecessarily lost."}},
    }
    # Keep the original display case to measure its finite-check limitation; do
    # not present a no-op expansion of that oracle as stronger general proof.
    document(root / "cases/safe_string.md", "Original soft conversion display regression", "The harness imports markupsafe's public namespace. Preserve value as Markup and all three original displayed lines. This remains a finite display regression: the reusable convert contract is a separate new case.", (root / "origin_cases/safe_string.md").read_text().split("```python\n")[1].split("```")[0])
    dump(root / "exampleproof.json", config)
    dump(root / "proposals.json", proposals)
    dump(root / "negative_proposals.json", negatives)

    retained_contracts = {
        ('tinydb', 'healthy_query'): ('Healthy fruit query', 'Keep db and the Query instance Fruit available. Insert the original two records and preserve equality, count-greater-than, and empty-result queries without mutating stored data. Retain only the default table. Emit no stdout.'),
        ('more_itertools', 'grouper'): ('Grouped values with padding', 'Keep a reusable callable named grouper accepting iterable, n and fillvalue keyword arguments. Preserve the original displayed groups of three with x padding; support empty input, exact multiples, and a final partial group padded with the supplied fill value.'),
        ('more_itertools', 'healthy_chunked'): ('Healthy chunked iterator', 'Keep a reusable callable named chunked. Preserve the original displayed list of chunks; support empty input, exact multiples, and a final shorter chunk without padding.'),
        ('markupsafe', 'optional_values'): ('Healthy optional escaped values', "The harness imports the public markupsafe namespace. Keep escape and escape_silent callable. Preserve displayed Markup('None') and Markup(''); escape_silent(None) returns empty Markup, HTML-sensitive text is escaped, and numeric zero is converted to Markup('0')."),
    }
    for (name, stem), (title, contract) in retained_contracts.items():
        root = ROOT / name
        code = (root / 'origin_cases' / (stem + '.md')).read_text().split('```python\n')[1].split('```')[0]
        document(root / 'cases' / (stem + '.md'), title, contract, code)

    for name in PROJECTS:
        original, root = ORIGIN / name, ROOT / name
        original_metadata = json.loads((original / "metadata.json").read_text())
        config = json.loads((root / "exampleproof.json").read_text())
        old_cases = {item['id']: item for item in original_metadata['cases']}
        cases = []
        for document_path in config['documents']:
            key = document_path + '#1'
            old = old_cases.get(key)
            cases.append({"id": key, "expected_before": old['expected_before'] if old else 'failed', "classification": "expanded_development_contract" if key not in old_cases or name == 'tinydb' and 'healthy' not in key or name == 'more_itertools' and 'collate' in key else "retained_development_regression", "origin_case": key if old else "cases/safe_string.md#1", "authorship": "Evaluator-authored context and external checks; unchanged source and retained upstream commands where documented.", "oracle": "configured_behavior_checks_and_expected_stdout"})
        metadata = {"schema_version": 1, "suite_id": name + "-semantic-development-v2", "split": "development_v2", "description": "Expanded development checks based on previously observed v1 migrations; never report these cases as held out.", "classification": "evaluator_authored_migration_contracts_and_retained_regressions", "provenance": {"origin": "benchmarks/real_projects/" + name, "previous_cases_and_live_results_seen": True, "held_out": False, "upstream_runtime_bytes_unchanged": True, "candidate_mode": "recorded_candidate_replay", "live_model_evaluation": False}, "limitations": ["Cases were deliberately selected from known failures and are development data.", "New callable tasks and boundary checks are authored adaptations, not new official upstream documentation excerpts.", "Finite checks share a process with candidate code and do not prove adversarial semantic equivalence.", "Reference candidates validate the evaluation pipeline, not model quality."], "cases": cases}
        dump(root / "metadata.json", metadata)
        copied = []
        for path in sorted(root.rglob('*')):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            origin_relative = relative.replace('origin_cases/', 'cases/', 1) if relative.startswith('origin_cases/') else 'provenance.json' if relative == 'upstream-provenance.json' else relative
            origin_path = original / origin_relative
            if origin_path.exists() and path.read_bytes() == origin_path.read_bytes():
                copied.append({"path": relative, "origin": str(origin_path.relative_to(REPOSITORY)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        mappings = {
            'tinydb': {f'tinydb/{p.name}': f'upstream/v3.15.2/tinydb/{p.name}' for p in (root / 'upstream/v3.15.2/tinydb').glob('*.py')} if name == 'tinydb' else {},
            'more_itertools': {**{f'more_itertools/{part}': f'upstream/5.0.0/more_itertools/{part}' for part in ('__init__.py', 'more.py', 'recipes.py')}, 'six.py': 'upstream/six-1.16.0/six.py'},
            'markupsafe': {f'markupsafe/{part}': f'upstream/1.1.1/src/markupsafe/{part}' for part in ('__init__.py', '_native.py', '_compat.py', '_constants.py')},
        }
        dump(root / 'provenance.json', {"schema_version": 1, "split": "development_v2", "upstream_provenance": "upstream-provenance.json", "copied_files": copied, "historical_source_mapping": mappings[name], "historical_versions": {'tinydb': '3.15.2', 'more_itertools': '5.0.0 + six 1.16.0', 'markupsafe': '1.1.1'}[name], "target_versions": {'tinydb': '4.8.2', 'more_itertools': '9.0.0', 'markupsafe': '2.1.5'}[name], "authored_files": ["metadata.json", "exampleproof.json", "negative_proposals.json", "cases/*.md"], "execution": "Copied code executes only via SandboxRunner; never host imports."})
    print("Created 3 development projects; validate.py performs isolated controls and replay.")


if __name__ == '__main__':
    main()
