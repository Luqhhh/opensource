"""An original, deliberately small API-v2 fixture for integration testing.

This is synthetic evaluation material, not a third-party repository finding.
"""

from dataclasses import dataclass


def rounded(value: float, *, decimals: int = 2) -> float:
    return round(value, decimals)


@dataclass(frozen=True)
class Product:
    name: str
    price: int


def lookup(name: str) -> Product:
    return Product(name=name, price=7)


def double(value: int) -> int:
    return value * 2
