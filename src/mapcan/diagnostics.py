"""Сообщения валидатора."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Literal

Level = Literal["error", "warning", "info"]
LEVEL_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Diagnostic:
    level: Level
    code: str
    message: str
    file: str | None = None
    line: int | None = None      # 1-based
    column: int | None = None    # 1-based
    path: str = ""
    node: list = field(default_factory=list)   # путь узла в YAML (для веб-редактора)

    def format(self) -> str:
        loc = self.file or "<input>"
        if self.line is not None:
            loc += f":{self.line}"
            if self.column is not None:
                loc += f":{self.column}"
        where = f" [{self.path}]" if self.path else ""
        return f"{loc}: {self.level}[{self.code}]: {self.message}{where}"


@dataclass
class Report:
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def add(self, d: Diagnostic) -> None:
        self.diagnostics.append(d)

    def extend(self, ds) -> None:
        self.diagnostics.extend(ds)

    def count(self, level: Level) -> int:
        return sum(1 for d in self.diagnostics if d.level == level)

    @property
    def errors(self) -> int:
        return self.count("error")

    @property
    def warnings(self) -> int:
        return self.count("warning")

    def sorted(self) -> list[Diagnostic]:
        return sorted(
            self.diagnostics,
            key=lambda d: (d.file or "", d.line or 0, LEVEL_ORDER[d.level], d.code),
        )

    def codes(self) -> set[str]:
        return {d.code for d in self.diagnostics}

    def to_json(self) -> str:
        return json.dumps([asdict(d) for d in self.sorted()], ensure_ascii=False, indent=2)
