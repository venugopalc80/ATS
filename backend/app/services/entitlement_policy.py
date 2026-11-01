"""Fail-closed entitlement policy helpers for AQERITH."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, TypeAlias

EntitlementValue: TypeAlias = bool | int | None


@dataclass(frozen=True)
class EntitlementDenied(Exception):
    key: str
    reason: str

    def __str__(self) -> str:
        return f"{self.key}: {self.reason}"


def feature_enabled(entitlements: Mapping[str, EntitlementValue], key: str) -> bool:
    """A feature is enabled only when its trusted server value is exactly True."""
    return entitlements.get(key) is True


def require_feature(entitlements: Mapping[str, EntitlementValue], key: str) -> None:
    """Fail closed when a feature is missing or not explicitly enabled."""
    if not feature_enabled(entitlements, key):
        raise EntitlementDenied(key, "feature_not_included")


def require_capacity(
    entitlements: Mapping[str, EntitlementValue],
    key: str,
    *,
    current_usage: int,
    increment: int = 1,
) -> None:
    """Enforce a quota. Explicit None means unlimited; missing values fail closed."""
    if current_usage < 0 or increment < 1:
        raise ValueError("Usage must be non-negative and increment must be positive")

    if key not in entitlements:
        raise EntitlementDenied(key, "quota_not_configured")

    limit = entitlements[key]
    if limit is None:
        return
    # bool subclasses int in Python; do not interpret True as a quota of one.
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise EntitlementDenied(key, "invalid_quota_configuration")
    if current_usage + increment > limit:
        raise EntitlementDenied(key, "quota_exceeded")
