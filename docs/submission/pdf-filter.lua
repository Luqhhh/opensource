-- Long paths and digests must wrap instead of extending beyond the page edge.
-- This affects PDF typesetting only; Markdown source and identifiers stay intact.
function Code(element)
  if not FORMAT:match('latex') then
    return nil
  end
  if #element.text < 36 and not element.text:find('/') then
    return nil
  end
  local escapes = {
    ['\\'] = '\\textbackslash{}', ['{'] = '\\{', ['}'] = '\\}',
    ['#'] = '\\#', ['$'] = '\\$', ['%'] = '\\%', ['&'] = '\\&',
    ['_'] = '\\_', ['^'] = '\\textasciicircum{}', ['~'] = '\\textasciitilde{}'
  }
  local characters = {}
  for _, codepoint in utf8.codes(element.text) do
    local character = utf8.char(codepoint)
    table.insert(characters, escapes[character] or character)
  end
  return pandoc.RawInline('latex', '{\\ttfamily '
    .. table.concat(characters, '\\allowbreak{}') .. '}')
end
