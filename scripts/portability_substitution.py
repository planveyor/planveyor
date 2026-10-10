#!/usr/bin/env python3
"""Portable normalization without implicit workstation policy reads.

Public profiles share generic interpreter rules. Caller-owned mappings use the
existing PortabilityRules and portabilize_text(rules=...) Python interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_KNOWN_CONTENT_PROFILES = frozenset({"default", "planveyor", "target-local"})

class PortabilityPolicyError(ValueError):
    """The requested public content profile is unsupported."""


@dataclass(frozen=True)
class PortabilityRules:
    """The narrow data consumed by this module's text-normalization grammar."""

    literal_rules: tuple[tuple[str, str], ...]
    miniforge_replacement: str
    homebrew_source: str
    homebrew_replacement: str
    primary_product_source: str | None
    primary_product_replacement: str | None
    preserve_version_pinned_receipt: bool


# Generic invocation keeps the broad interpreter grammar that removes a local
# Python path. It deliberately has no owner/repository substitutions.
GENERIC_PORTABILITY_RULES = PortabilityRules(
    literal_rules=(),
    miniforge_replacement="python3",
    homebrew_source="/opt/homebrew/bin/python",
    homebrew_replacement="python3",
    primary_product_source=None,
    primary_product_replacement=None,
    preserve_version_pinned_receipt=True,
)

_USER_PATH_PREFIX_RE = "/" + "Users" + r"/[^/\s'\"`]+"
MINIFORGE_PYTHON_RE = re.compile(
    _USER_PATH_PREFIX_RE
    + r"/miniforge3(?:/envs/[^/\s'\"`]+)?/bin/python(?:3(?:\.\d+)?)?"
)
_DRY_RUN_RE = re.compile(r"pip\s+install\s+--dry-run")
_PYTHON_VERSION_RE = re.compile(r"Python\s+3\.\d+")


def load_portability_rules(
    *,
    content_profile_id: str = "default",
    policy_root: Path | None = None,
) -> PortabilityRules:
    """Return generic public rules; ``policy_root`` is never read.

    The parameter is retained for API compatibility. Explicit caller-owned
    mappings use PortabilityRules through portabilize_text(rules=...).
    """
    profile = content_profile_id.strip()
    if profile not in _KNOWN_CONTENT_PROFILES:
        raise PortabilityPolicyError(f"unsupported content_profile_id: {content_profile_id!r}")
    return GENERIC_PORTABILITY_RULES


def is_version_pinned_record(text: str) -> bool:
    """Return whether a historical receipt must retain its interpreter text."""

    return bool(
        MINIFORGE_PYTHON_RE.search(text)
        and _DRY_RUN_RE.search(text)
        and _PYTHON_VERSION_RE.search(text)
    )


def _primary_product_boundary_re(source: str) -> re.Pattern[str]:
    return re.compile(re.escape(source) + r"(?![\w.])")


def portabilize_text(
    text: str,
    *,
    rules: PortabilityRules | None = None,
    is_version_pinned: bool = False,
) -> str:
    """Normalize one text value using already-selected immutable rules."""

    selected = rules or GENERIC_PORTABILITY_RULES
    if not (is_version_pinned and selected.preserve_version_pinned_receipt):
        text = MINIFORGE_PYTHON_RE.sub(selected.miniforge_replacement, text)
    homebrew = re.compile(re.escape(selected.homebrew_source) + r"(3(?:\.\d+)?)")
    text = homebrew.sub(selected.homebrew_replacement, text)
    for source, replacement in selected.literal_rules:
        text = text.replace(source, replacement)
    if selected.primary_product_source is not None and selected.primary_product_replacement is not None:
        text = _primary_product_boundary_re(selected.primary_product_source).sub(
            selected.primary_product_replacement,
            text,
        )
    return text
