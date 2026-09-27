"""Provenance, not a truth oracle: facts are trusted only as supplied test data.

Every dynamic factual fragment is read through Book.get(). Derived claims carry
explicit input paths. This verifies source ownership/value, not real-world truth.
"""
from dataclasses import dataclass, field, asdict
from copy import deepcopy
import hashlib
import re
from typing import Any
from .store import canonical


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def resolve(obj: Any, path: str) -> Any:
    if not path:
        return obj
    try:
        for key in path.split("."):
            obj = obj[int(key)] if isinstance(obj, list) else obj[key]
        return obj
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def text(value: Any, max_length: int = 400) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    value = re.sub(r"[\x00-\x1f\x7f]", " ", str(value))
    return " ".join(value.split())[:max_length]


def suspicious(value: str) -> bool:
    return bool(re.search(r"ignore (?:all |previous |prior )?instructions|system\s*prompt|api[_ -]?key|<script|javascript:|developer message", value, re.I))


@dataclass
class Evidence:
    scope: str
    path: str
    value: Any
    version: int | None = None


@dataclass
class Book:
    roots: dict[str, dict]
    versions: dict[str, int] = field(default_factory=dict)
    facts: dict[str, Evidence] = field(default_factory=dict)
    calculations: list[dict] = field(default_factory=list)

    def get(self, scope: str, path: str, default: Any = None) -> Any:
        value = resolve(self.roots.get(scope, {}), path)
        if value is None:
            return default
        self.facts[f"{scope}.{path}"] = Evidence(scope, path, deepcopy(value), self.versions.get(scope))
        return value

    def string(self, scope: str, path: str, default: str = "", limit: int = 400) -> str:
        value = text(self.get(scope, path), limit)
        return value if value and not suspicious(value) else default

    def number(self, scope: str, path: str) -> float | int | None:
        v = self.get(scope, path)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            import math
            return v if math.isfinite(v) else None
        return None

    def derived(self, operation: str, inputs: list[str], result: Any) -> None:
        self.calculations.append({"operation": operation, "inputs": inputs, "result": result})

    def verify(self) -> bool:
        return all(resolve(self.roots.get(f.scope, {}), f.path) == f.value for f in self.facts.values())

    def report(self) -> dict:
        return {"facts": [asdict(f) for _, f in sorted(self.facts.items())], "calculations": self.calculations, "source_values_match": self.verify()}


def percent(value: float) -> str:
    return f"{value * 100:.1f}".rstrip("0").rstrip(".") + "%"
