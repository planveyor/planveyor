#!/usr/bin/env python3
"""
Path-prefix context registry for docs retrieval tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ContextRule:
    prefix: str
    label: str
    text: str


DEFAULT_CONTEXT_RULES: tuple[ContextRule, ...] = (
    ContextRule("docs/schema.md", "Schema", "Schema (канон): модели/инварианты данных"),
    ContextRule("docs/api.md", "API", "API (канон): public/internal endpoints"),
    ContextRule("docs/guides/", "Guides", "Guides (канон): эксплуатация/инструкции"),
    ContextRule("docs/roles/", "Roles", "Roles (process): bootstrap роли"),
    ContextRule("docs/playbooks/", "Playbooks", "Playbooks (process): как работаем/как проверяем"),
    ContextRule("docs/plans/", "Plans", "Plans (эпhemeral): контракт на работу; **Status:** = кто следующий"),
    ContextRule("docs/followups/", "Follow-ups", "Follow-ups (backlog): мастер-индекс = docs/followups/index.md"),
    ContextRule("docs/reviews/", "Reviews", "Reviews (артефакты): отчеты/harvest/audit; не source of truth"),
    ContextRule("docs/code_reviews/", "Code reviews", "Code reviews (артефакты): замечания по изменениям; не source of truth"),
    ContextRule("docs/snapshots/", "Snapshots", "Snapshots (контекст): brain backup; может быть устаревшим"),
)


def _normalize_value(value: str) -> str:
    out = str(value or "").strip().replace("\\", "/")
    while "//" in out:
        out = out.replace("//", "/")
    while out.startswith("./"):
        out = out[2:]
    return out


def _matches(path: str, prefix: str) -> bool:
    if prefix.endswith("/"):
        return path.startswith(prefix)
    return path == prefix


def _iter_rules(rules: Iterable[ContextRule] | None = None) -> tuple[ContextRule, ...]:
    if rules is None:
        return DEFAULT_CONTEXT_RULES
    return tuple(rules)


def registered_prefixes(*, rules: Iterable[ContextRule] | None = None) -> list[str]:
    out: list[str] = []
    for rule in _iter_rules(rules):
        prefix = _normalize_value(rule.prefix)
        if prefix:
            out.append(prefix)
    return out


def contexts_for_path(path: str, *, rules: Iterable[ContextRule] | None = None) -> list[dict[str, str]]:
    path_norm = _normalize_value(path)
    if not path_norm:
        return []

    matched: list[tuple[int, int, dict[str, str]]] = []
    seen_prefixes: set[str] = set()
    for idx, rule in enumerate(_iter_rules(rules)):
        prefix_norm = _normalize_value(rule.prefix)
        if not prefix_norm or not _matches(path_norm, prefix_norm):
            continue
        if prefix_norm in seen_prefixes:
            continue
        seen_prefixes.add(prefix_norm)
        matched.append(
            (
                len(prefix_norm),
                idx,
                {
                    "prefix": prefix_norm,
                    "label": str(rule.label),
                    "text": str(rule.text),
                },
            )
        )

    matched.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in matched]


def format_contexts_inline(contexts: list[dict[str, str]]) -> str:
    if not contexts:
        return "(none)"

    parts: list[str] = []
    for ctx in contexts:
        label = str(ctx.get("label", "")).strip()
        text = str(ctx.get("text", "")).strip()
        if label and text and not text.lower().startswith(label.lower()):
            parts.append(f"{label}: {text}")
            continue
        if text:
            parts.append(text)
            continue
        if label:
            parts.append(label)
            continue
        fallback = str(ctx.get("prefix", "")).strip()
        parts.append(fallback or "(unknown)")

    return " -> ".join(parts)
