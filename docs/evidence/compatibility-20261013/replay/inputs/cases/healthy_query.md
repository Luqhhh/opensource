# 正常对照：保留查询参数的重复值和空值

当前支持的 `urllib.parse` 接口。所有外部检查通过时应直接标记 `checked`，不能请求修复候选。该对照没有历史移除事件，也不是一个待修复缺陷。[官方查询解析接口](https://docs.python.org/3.10/library/urllib.parse.html#urllib.parse.parse_qs)。

```python
from urllib.parse import parse_qs, urlencode
query = "tag=ai&tag=open+source&empty=&name=%E9%9B%AA"
parsed = parse_qs(query, keep_blank_values=True)
rebuilt = urlencode(parsed, doseq=True)
print(parsed["tag"], parsed["empty"], parsed["name"])
```
