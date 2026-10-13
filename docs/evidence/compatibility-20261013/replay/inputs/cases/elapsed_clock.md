# 包含等待时间的短时计时

这是依据真实 API 移除事件自编的最小重现。计时目标是包含睡眠的经过时间，单位为秒；不能换成排除睡眠的 CPU 时间。旧 `clock` 的行为依赖平台，本例不声称它在所有旧平台上满足这项需求。

`time.clock` 自 Python 3.3 弃用，Python 3.8 移除。官方来源与版本记录见基准元数据。

```python
import time
timer = time.clock
started = timer()
time.sleep(0.02)
elapsed = timer() - started
print(elapsed >= 0.01)
```
