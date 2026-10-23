/* Local, display-only lexical highlighting. No evaluation or external resources. */
(() => {
  'use strict';
  const escape=text=>String(text).replace(/[&<>"'\r]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','\r':'&#13;'}[c]));
  const words=text=>new Set(text.split(' '));
  const names={python:'Python',javascript:'JavaScript',typescript:'TypeScript',json:'JSON',yaml:'YAML',toml:'TOML',shell:'Shell',html:'HTML',css:'CSS',markdown:'Markdown',c:'C',cpp:'C++',java:'Java',go:'Go',rust:'Rust',text:'纯文本'};
  const aliases={py:'python',pyi:'python',pycon:'python',python3:'python',js:'javascript',jsx:'javascript',mjs:'javascript',cjs:'javascript',ts:'typescript',tsx:'typescript',yml:'yaml',sh:'shell',bash:'shell',zsh:'shell',console:'shell',shell:'shell',htm:'html',xml:'html',svg:'html',scss:'css',less:'css',md:'markdown',mdx:'markdown',h:'c',cc:'cpp',cxx:'cpp',hpp:'cpp',rs:'rust',txt:'text',rst:'text',ini:'toml'};
  function language(value='text'){
    const key=String(value).trim().toLowerCase().split(/\s+/)[0];
    return Object.hasOwn(aliases,key)?aliases[key]:(Object.hasOwn(names,key)?key:'text');
  }
  function detect(path=''){
    const name=String(path).split('/').at(-1).toLowerCase();
    if(['dockerfile','containerfile','makefile','gnumakefile'].includes(name))return 'shell';
    return language(name.includes('.')?name.split('.').at(-1):name);
  }
  const common='if else for while do return break continue switch case default try catch finally throw new class extends public private protected static import export from as async await yield in of this super function const let var void null true false typeof instanceof delete get set';
  const keywords={
    python:words('and as assert async await break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield match case'),
    javascript:words(common),typescript:words(common+' interface type enum implements namespace declare abstract readonly keyof infer unknown never any string number boolean constructor override satisfies'),
    json:words(''),yaml:words(''),toml:words(''),
    shell:words('if then else elif fi for do done while until in case esac function select time export local readonly source alias unset set echo printf cd pwd test exec return exit FROM RUN COPY ADD WORKDIR ENV ARG ENTRYPOINT CMD EXPOSE USER VOLUME LABEL'),
    html:words(''),css:words('important inherit initial unset auto none block flex grid relative absolute fixed sticky'),
    c:words('auto break case char const continue default do double else enum extern float for goto if inline int long register restrict return short signed sizeof static struct switch typedef union unsigned void volatile while'),
    cpp:words(common+' auto bool char const constexpr decltype double enum explicit extern float friend inline int long namespace nullptr operator override short signed sizeof struct template typename typedef union unsigned using virtual void volatile'),
    java:words(common+' abstract boolean byte char double enum final float implements int long native package short synchronized throws transient volatile record'),
    go:words('break case chan const continue default defer else fallthrough for func go goto if import interface map package range return select struct switch type var'),
    rust:words('as async await break const continue crate dyn else enum extern fn for if impl in let loop match mod move mut pub ref return self Self static struct super trait type unsafe use where while'),
  };
  const literals=words('True False None true false null undefined NaN Infinity nil NULL nullptr yes no on off');
  const builtins=words('print len range enumerate zip list dict set tuple str int float bool bytes object type isinstance issubclass Exception ValueError RuntimeError TypeError open input sum min max sorted reversed any all abs round map filter next iter getattr setattr hasattr property classmethod staticmethod __init__ self cls console window document Math JSON Array Object String Number Boolean Promise Map Set Date Error RegExp require module exports process');
  const number='\\b(?:0[xX][\\da-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|\\d[\\d_]*(?:\\.[\\d_]+)?(?:[eE][+-]?[\\d_]+)?)[a-zA-Z]*\\b';
  const quoted='"(?:\\\\[\\s\\S]|[^"\\\\\\r\\n])*(?:"|(?=\\r?\\n|$))|\'(?:\\\\[\\s\\S]|[^\'\\\\\\r\\n])*(?:\'|(?=\\r?\\n|$))';
  const identifiers='[A-Za-z_$][\\w$]*';
  function pattern(lang){
    const parts=[];
    if(lang==='python')parts.push('#[^\\r\\n]*', '(?:\\b[rRuUbBfF]{1,2})?(?:"""[\\s\\S]*?(?:"""|$)|\'\'\'[\\s\\S]*?(?:\'\'\'|$))');
    else if(['shell','yaml','toml'].includes(lang))parts.push('(?<!\\S)#[^\\r\\n]*');
    else if(lang==='html')parts.push('<!--[\\s\\S]*?(?:-->|$)', '<\\/?[A-Za-z][\\w:-]*', '<!DOCTYPE[^>]*>');
    else if(lang!=='json')parts.push('\\/\\*[\\s\\S]*?(?:\\*\\/|$)');
    if(['javascript','typescript','c','cpp','java','go','rust'].includes(lang))parts.push('\\/\\/[^\\r\\n]*');
    if(['javascript','typescript','go','shell'].includes(lang))parts.push('`(?:\\\\[\\s\\S]|[^`\\\\])*(?:`|$)');
    if(lang==='toml')parts.push('"""[\\s\\S]*?(?:"""|$)|\'\'\'[\\s\\S]*?(?:\'\'\'|$)');
    parts.push(quoted);
    if(lang==='css')parts.push('#[\\da-fA-F]{3,8}\\b');
    if(lang==='shell')parts.push('\\$\\{[^}\\r\\n]*\\}|\\$[\\w?@#]+');
    parts.push(number,identifiers,'[{}\\[\\]();,.]','[+*/%=!<>:&|?~^@-]+');
    return new RegExp(parts.join('|'),'g');
  }
  function tokens(source,lang){
    lang=language(lang);const text=String(source);
    if(lang==='text')return [{text,kind:''}];
    if(lang==='markdown')return markdownTokens(text);
    const result=[];let at=0,previous='';
    for(const match of text.matchAll(pattern(lang))){
      if(match.index>at)result.push({text:text.slice(at,match.index),kind:''});
      const value=match[0],after=text.slice(match.index+value.length),set=keywords[lang];let kind='';
      if(value.startsWith('/*')&&!['python','shell','yaml','toml','json'].includes(lang)||value.startsWith('//')&&['javascript','typescript','c','cpp','java','go','rust'].includes(lang)||value.startsWith('<!--')&&lang==='html'||value.startsWith('#')&&['python','shell','yaml','toml'].includes(lang))kind='comment';
      else if(/^([rRuUbBfF]{0,2}["']|`)/.test(value))kind=/^\s*:/.test(after)&&['json','yaml'].includes(lang)?'property':'string';
      else if(lang==='html'&&value.startsWith('<'))kind='tag';
      else if(/^\d/.test(value)||lang==='css'&&value.startsWith('#'))kind='number';
      else if(lang==='shell'&&value.startsWith('$'))kind='variable';
      else if(literals.has(value))kind='literal';
      else if(set?.has(value))kind='keyword';
      else if(/^[A-Za-z_$]/.test(value)&&['class','interface','struct','enum','trait'].includes(previous))kind='type';
      else if(/^[A-Za-z_$]/.test(value)&&(['def','function','fn','func'].includes(previous)||/^\s*\(/.test(after)))kind='function';
      else if(/^[A-Za-z_$]/.test(value)&&(['json','yaml','css'].includes(lang)&&/^\s*:/.test(after)||['toml','html'].includes(lang)&&/^\s*=/.test(after)))kind='property';
      else if(builtins.has(value))kind='builtin';
      else if(/^[{}\[\]();,.]$/.test(value))kind='punctuation';
      else if(/^[+*/%=!<>:&|?~^@-]+$/.test(value))kind='operator';
      else if(/^[A-Z][A-Za-z0-9_]+$/.test(value))kind='type';
      result.push({text:value,kind});at=match.index+value.length;
      if(kind!=='comment')previous=value;
    }
    if(at<text.length)result.push({text:text.slice(at),kind:''});
    return result;
  }
  function markdownTokens(text){
    const result=[];let fence=null,code='',codeLanguage='text';
    const flush=()=>{if(code){result.push(...tokens(code,codeLanguage));code='';}};
    for(const line of text.match(/[^\n]*\n|[^\n]+$/g)||[]){
      const opening=line.match(/^\s{0,3}(`{3,}|~{3,})([^\r\n]*)/);
      if(fence){
        if(opening&&opening[1][0]===fence[0]&&opening[1].length>=fence.length&&!opening[2].trim()){flush();fence=null;result.push({text:line,kind:'comment'});}
        else code+=line;
      }else if(opening){fence=opening[1];codeLanguage=language(opening[2]);result.push({text:line,kind:'comment'});}
      else if(/^\s{0,3}#{1,6}\s/.test(line))result.push({text:line,kind:'heading'});
      else result.push({text:line,kind:''});
    }
    flush();return result;
  }
  // Close/reopen spans at line boundaries so each line keeps its original ID.
  function lines(source,lang='text'){
    const output=[''];
    for(const token of tokens(source,lang)){
      const parts=token.text.split('\n');
      parts.forEach((part,index)=>{
        if(index)output.push('');
        if(part)output[output.length-1]+=token.kind?`<span class="syntax-${token.kind}">${escape(part)}</span>`:escape(part);
      });
    }
    return output;
  }
  const api={detect,language,label:value=>names[language(value)],tokens,lines,highlight:(text,lang)=>lines(text,lang).join('\n')};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else globalThis.ExampleProofSyntax=api;
})();
