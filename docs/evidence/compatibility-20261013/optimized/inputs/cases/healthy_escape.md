# 正常对照：HTML 转义与还原

当前支持的 `html.escape` / `html.unescape` 接口。默认转义引号、尖括号与和号，并保持可逆。所有外部检查通过时应直接标记 `checked`，不能请求修复候选。该对照没有历史移除事件。[官方 HTML 接口](https://docs.python.org/3.10/library/html.html#html.escape)。

```python
from html import escape, unescape
text = '<a title="A&B">雪</a>'
escaped = escape(text, quote=True)
restored = unescape(escaped)
print(escaped)
```
