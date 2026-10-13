# 使用最大公约数约分

这是依据真实 API 移除事件自编的最小重现。约分数据为非负整数，分母大于零。外部检查覆盖互质数和含零输入；不扩展到旧接口与当前接口符号行为可能不同的负数域。

`fractions.gcd` 自 Python 3.5 弃用，Python 3.9 移除。官方来源与版本记录见基准元数据。

```python
from fractions import gcd
numerator, denominator = 84, 30
divisor = gcd(numerator, denominator)
reduced = (numerator // divisor, denominator // divisor)
print(reduced)
```
