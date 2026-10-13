# 将 HTML 字符引用还原为文本

这是依据真实 API 移除事件自编的最小重现。需要同时处理命名、十进制、十六进制字符引用，并保留未知引用；这不是删除 HTML 标签的接口。

`HTMLParser.unescape` 自 Python 3.4 弃用，Python 3.9 移除。官方来源与版本记录见基准元数据。

```python
from html.parser import HTMLParser
decode_entities = HTMLParser().unescape
text = "Tom &amp; Jerry &#60;3 &#x2603;"
decoded = decode_entities(text)
print(decoded)
```
