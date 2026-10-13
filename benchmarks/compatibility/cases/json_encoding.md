# 保留 Decimal 精度的 JSON 读取

这是依据真实 API 移除事件自编的最小重现。输入为 Unicode JSON 文本，保留中文名称，并通过 `parse_float=Decimal` 保留小数精度。移除废弃参数时不能连带删除有效的解析选项。

`json.loads` 的 `encoding` 参数自 Python 3.1 弃用并被忽略，Python 3.8 起产生弃用警告，Python 3.9 移除。官方来源与版本记录见基准元数据。

```python
import json
from decimal import Decimal
from functools import partial
load_document = partial(json.loads, encoding="utf-8", parse_float=Decimal)
document = '{"name": "雪", "price": 1.20, "available": true}'
record = load_document(document)
print(record["name"], record["price"])
```
