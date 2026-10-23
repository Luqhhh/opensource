-- Keep Chinese table cells within the printable page and resolve packet links.
function Table(element)
  if not FORMAT:match('latex') then return nil end
  local count = element.colspecs and #element.colspecs or #element.widths
  local widths = count == 3 and {0.20, 0.40, 0.40} or nil
  if widths then
    if element.colspecs then
      for index, spec in ipairs(element.colspecs) do
        spec[2] = widths[index]
      end
    else
      element.widths = widths
    end
  end
  return element
end

function Link(element)
  local targets = {
    ['participant-guide.md'] = '02_受访者说明与任务卡.pdf',
    ['facilitator-guide.md'] = '03_主持人手册.pdf',
    ['metrics.md'] = '04_指标与汇总说明.pdf',
    ['results.md'] = '可编辑源文档/用户体验回填.md',
    ['observations.csv'] = '记录模板/observations.csv',
    ['questionnaire.csv'] = '记录模板/questionnaire.csv',
    ['interviews.csv'] = '记录模板/interviews.csv',
    ['external-reproduction.csv'] = '记录模板/external-reproduction.csv'
  }
  element.target = targets[element.target] or element.target
  return element
end
