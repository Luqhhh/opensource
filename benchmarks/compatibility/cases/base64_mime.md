# 保留 MIME 换行的 Base64 往返

这是依据真实 API 移除事件自编的最小重现，非第三方仓库缺陷。这里需要 MIME 风格的 76 字符换行与末尾换行，不能用无换行编码替代。编码器和解码器还应支持其他二进制输入。

`base64.encodestring` / `decodestring` 自 Python 3.1 弃用，Python 3.9 移除。官方来源与版本记录见基准元数据。

```python
import base64
encode_payload = base64.encodestring
decode_payload = base64.decodestring
payload = b"abc" * 20
encoded = encode_payload(payload)
decoded = decode_payload(encoded)
print(len(decoded), len(encoded.splitlines()), decoded == payload)
```
