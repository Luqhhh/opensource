/* Synthetic lexical cases; no imported project code is executed. */
'use strict';
const assert=require('node:assert/strict');
const syntax=require('../exampleproof/learner_web/code_highlight.js');
let checks=0;
function test(name,run){run();checks++;console.log('PASS '+name);}
const kind=(text,language,value)=>syntax.tokens(text,language).find(token=>token.text===value)?.kind;
function plain(html){return html.replace(/<span class="syntax-[a-z]+">|<\/span>/g,'').replace(/&(amp|lt|gt|quot|#39|#13);/g,(_,key)=>({amp:'&',lt:'<',gt:'>',quot:'"','#39':"'",'#13':'\r'}[key]));}
test('detect extensions and aliases; unknown formats stay plain',()=>{
  for(const [path,language] of [['src/Main.PY','python'],['index.tsx','typescript'],['config.yml','yaml'],['Cargo.toml','toml'],['Dockerfile','shell'],['unknown.xyz','text']])assert.equal(syntax.detect(path),language);
  assert.equal(syntax.language('js extra'), 'javascript');
  for(const name of ['__proto__','constructor','toString'])assert.equal(syntax.language(name),'text');
});
test('Python floor division is an operator, hashes inside strings stay strings',()=>{
  const code='value = 10 // 2 # halve\nurl = "https://host/#tag"';
  assert.equal(kind(code,'python','//'),'operator');
  assert.equal(kind(code,'python','# halve'),'comment');
  assert.equal(kind(code,'python','"https://host/#tag"'),'string');
});
test('Python multiline docstrings retain their context on every line',()=>{
  const lines=syntax.lines('def run():\n    """line one\n    return # still a string\n    end"""\n    return 2','python');
  assert.match(lines[2],/syntax-string/);assert.doesNotMatch(lines[2],/syntax-comment|syntax-keyword/);
  assert.match(lines[4],/syntax-keyword/);
});
test('JavaScript block comments and template strings cross line boundaries',()=>{
  const lines=syntax.lines('/* first\nreturn false\n*/\nconst s = `a\nb`;\nrun(s);','javascript');
  assert.match(lines[1],/syntax-comment/);assert.doesNotMatch(lines[1],/syntax-keyword/);
  assert.match(lines[4],/syntax-string/);assert.match(lines[5],/syntax-function/);
});
test('JSON keys and values, HTML attributes, and shell variables are distinct',()=>{
  assert.equal(kind('{"key": true}','json','"key"'),'property');
  assert.equal(kind('{"key": true}','json','true'),'literal');
  assert.equal(kind('<div title="demo">','html','title'),'property');
  assert.equal(kind('echo ${VALUE} # comment','shell','${VALUE}'),'variable');
});
test('Markdown fences use the declared language and allow longer delimiters',()=>{
  const text='~~~~js\n/* note\nreturn false\n*/\n~~~\nconst x=2;\n~~~~\n# Title';
  const lines=syntax.lines(text,'markdown');
  assert.match(lines[2],/syntax-comment/);assert.match(lines[5],/syntax-keyword/);assert.match(lines[7],/syntax-heading/);
});
test('Unknown fence content and unknown files are escaped without guessing',()=>{
  assert.equal(syntax.highlight('<img src=x onerror=bad()>','text'),'&lt;img src=x onerror=bad()&gt;');
  assert.doesNotMatch(syntax.lines('```unknown\nreturn 2\n```','markdown')[1],/syntax-/);
});
test('Unclosed strings and comments preserve remaining source',()=>{
  for(const [text,language] of [['"unterminated\nnext','javascript'],['/* unfinished\nend','c'],['"""unfinished\nend','python']])assert.equal(plain(syntax.highlight(text,language)),text);
});
test('All modes preserve whitespace, CRLF, Unicode and dangerous HTML exactly',()=>{
  const input='\t  <script>alert("x")</script> & \'世界\'\r\n// # comment\n\n"a\\\\b"\n';
  for(const language of ['python','javascript','typescript','json','yaml','toml','shell','html','css','markdown','c','cpp','java','go','rust','text']){
    const lines=syntax.lines(input,language);
    assert.equal(lines.length,input.split('\n').length,language);
    assert.equal(plain(lines.join('\n')),input,language);
    assert.equal(syntax.tokens(input,language).map(token=>token.text).join(''),input,language);
    assert.doesNotMatch(lines.join(''),/<script|<img|onerror=/);
  }
});
test('Large supported files and long lines retain exact text',()=>{
  const source=('const value = "'+ 'x'.repeat(2000)+'"; // comment\n').repeat(120);
  assert.equal(plain(syntax.highlight(source,'javascript')),source);
});
console.log(`${checks} synthetic highlighter checks passed`);
