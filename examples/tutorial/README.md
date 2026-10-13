# ExampleProof evaluation tutorial

These examples are authored fixtures, not discoveries in an upstream repository.
The collections example reproduces a real Python 3.10 compatibility change.

## 1. Historical standard-library compatibility

Check whether a dictionary implements the mapping interface.

```python
from collections import Mapping
result = isinstance({"a": 1}, Mapping)
assert result is True
print(result)
```

## 2. Renamed keyword in a synthetic SDK

Round a number to two decimal places using the bundled SDK.

```python
from sdk import rounded
result = rounded(1.234, digits=2)
assert result == 1.23
print(result)
```

## 3. Changed return type in a synthetic SDK

Retrieve a product name from the SDK's lookup result.

```python
from sdk import lookup
product = lookup("apple")
result = product["name"]
assert result == "apple"
print(result)
```

## 4. Healthy example: must stay unchanged

```python
from sdk import double
result = double(3)
assert result == 6
print(result)
```

## 5. Incomplete contextual fragment

This fragment needs a dataset that is intentionally not included.

```python
print(training_dataset[0])
```

## 6. Runs, but has no behavioral oracle

```python
from sdk import double
print(double(5))
```
