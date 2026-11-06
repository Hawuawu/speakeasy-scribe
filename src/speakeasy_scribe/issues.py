"""Validation problems and the helpers that report them while parsing YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    """One problem found in a profile; ``level`` is ``"error"`` or ``"warning"``."""

    level: str
    where: str
    message: str

    def __str__(self) -> str:
        """Format as ``level: where: message``."""
        return f"{self.level}: {self.where}: {self.message}"


@dataclass
class Report:
    """Every issue found while loading one profile, in the order found."""

    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        """Issues that stop the profile from being applied."""
        return [issue for issue in self.issues if issue.level == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        """Issues worth a look that do not block applying."""
        return [issue for issue in self.issues if issue.level == WARNING]

    def at(self, where: str) -> Scope:
        """Return a scope that reports issues found at ``where``."""
        return Scope(self, where)


@dataclass(frozen=True)
class Scope:
    """A place in the YAML (file, scene, line...) that issues are reported against."""

    report: Report
    where: str

    def error(self, message: str) -> None:
        """Record an error at this place."""
        self.report.issues.append(Issue(ERROR, self.where, message))

    def warn(self, message: str) -> None:
        """Record a warning at this place."""
        self.report.issues.append(Issue(WARNING, self.where, message))

    def child(self, suffix: str) -> Scope:
        """Return a narrower scope, such as one line of a scene."""
        return Scope(self.report, f"{self.where}{suffix}")

    def unknown_keys(self, raw: dict[Any, Any], allowed: set[str], what: str) -> None:
        """Report every key of ``raw`` that is not in ``allowed``."""
        for key in raw:
            if key not in allowed:
                self.error(f"unknown {what} '{key}'")

    def number(self, value: Any, name: str, bounds: tuple[float, float], default: float) -> float:
        """Check a number against SpeakEasy's range; missing or non-numbers give ``default``."""
        if value is None:
            return default
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.error(f"{name} must be a number")
            return default
        low, high = bounds
        if not low <= value <= high:
            self.error(f"{name} must be between {low} and {high}")
        return value

    def flag(self, value: Any, name: str = "enabled") -> bool:
        """Check a true/false switch; anything but ``false`` counts as on, like SpeakEasy."""
        if not isinstance(value, bool):
            self.error(f"{name} must be true or false")
        return value is not False
