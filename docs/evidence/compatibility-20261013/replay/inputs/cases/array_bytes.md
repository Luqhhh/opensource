# 数组的二进制序列化与追加

这是依据真实 API 移除事件自编的最小重现。将无符号单字节数组序列化为 `bytes`，再追加到已有数组。使用 `B` 类型避免机器字节序影响。解码必须追加，不能覆盖已有元素。

`array.array.tostring` / `fromstring` 自 Python 3.2 弃用，Python 3.9 移除。官方来源与版本记录见基准元数据。

```python
from array import array
serialize = array.tostring
append_bytes = array.fromstring
values = array("B", [0, 127, 255])
encoded = serialize(values)
restored = array("B", [42])
append_bytes(restored, encoded)
print(restored.tolist())
```
