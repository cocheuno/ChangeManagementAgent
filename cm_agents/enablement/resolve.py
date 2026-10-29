"""CI name resolution. Exact match wins. A contains-match must be unique."""

from __future__ import annotations


def resolve_ci_name(requested: str, names: list[str]) -> list[str]:
    exact = [name for name in names if name == requested]
    if exact:
        return exact
    folded = requested.casefold()
    return [name for name in names if folded in name.casefold()]


def resolution_gap(requested: str, matches: list[str]) -> str | None:
    if len(matches) == 1:
        return None
    if not matches:
        return f"CI {requested} was not found"
    listed = ", ".join(sorted(matches))
    return f"CI {requested} is ambiguous: {listed}"
