"""Pure deterministic business logic for the synthetic payment service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeConfig:
    service_name: str
    service_version: str
    mode: str
    checkout_timeout_ms: int
    downstream_latency_ms: int
    downstream_status: str
    dependency_warning_threshold_ms: int

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RuntimeConfig":
        required = {
            "service_name",
            "service_version",
            "mode",
            "checkout_timeout_ms",
            "downstream_latency_ms",
            "downstream_status",
            "dependency_warning_threshold_ms",
        }
        missing = sorted(required - set(raw))
        if missing:
            raise ValueError(f"runtime config missing fields: {', '.join(missing)}")
        config = cls(
            service_name=str(raw["service_name"]),
            service_version=str(raw["service_version"]),
            mode=str(raw["mode"]),
            checkout_timeout_ms=int(raw["checkout_timeout_ms"]),
            downstream_latency_ms=int(raw["downstream_latency_ms"]),
            downstream_status=str(raw["downstream_status"]),
            dependency_warning_threshold_ms=int(raw["dependency_warning_threshold_ms"]),
        )
        if min(
            config.checkout_timeout_ms,
            config.downstream_latency_ms,
            config.dependency_warning_threshold_ms,
        ) <= 0:
            raise ValueError("runtime timing values must be positive")
        if config.downstream_status not in {"ok", "error"}:
            raise ValueError("downstream_status must be ok or error")
        return config


@dataclass(frozen=True)
class CheckoutResult:
    status_code: int
    outcome: str
    error_code: str | None
    downstream_latency_ms: int
    dependency_warning: bool


class SyntheticPaymentService:
    """A small service model with a single deterministic failure mode."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.checkout_attempts = 0
        self.checkout_timeouts = 0
        self.checkout_successes = 0

    def health(self) -> dict[str, Any]:
        # Liveness intentionally does not prove that the checkout budget is safe.
        return {
            "status": "ok",
            "service": self.config.service_name,
            "version": self.config.service_version,
            "downstream_status": self.config.downstream_status,
            "checkout_path": "degraded"
            if self.config.downstream_latency_ms > self.config.checkout_timeout_ms
            else "ready",
        }

    def checkout(self, order_id: str, amount_cents: int) -> CheckoutResult:
        if not order_id or amount_cents <= 0:
            raise ValueError("order_id and a positive amount_cents are required")
        self.checkout_attempts += 1
        warning = (
            self.config.downstream_latency_ms
            > self.config.dependency_warning_threshold_ms
        )
        if self.config.downstream_status != "ok":
            self.checkout_timeouts += 1
            return CheckoutResult(
                status_code=502,
                outcome="rejected",
                error_code="payment_gateway_unavailable",
                downstream_latency_ms=self.config.downstream_latency_ms,
                dependency_warning=warning,
            )
        if self.config.downstream_latency_ms > self.config.checkout_timeout_ms:
            self.checkout_timeouts += 1
            return CheckoutResult(
                status_code=504,
                outcome="timeout",
                error_code="checkout_dependency_timeout",
                downstream_latency_ms=self.config.downstream_latency_ms,
                dependency_warning=warning,
            )
        self.checkout_successes += 1
        return CheckoutResult(
            status_code=200,
            outcome="authorized",
            error_code=None,
            downstream_latency_ms=self.config.downstream_latency_ms,
            dependency_warning=warning,
        )

    def metrics(self) -> dict[str, Any]:
        return {
            "service": self.config.service_name,
            "version": self.config.service_version,
            "checkout_attempts": self.checkout_attempts,
            "checkout_timeouts": self.checkout_timeouts,
            "checkout_successes": self.checkout_successes,
            "downstream_latency_ms": self.config.downstream_latency_ms,
            "downstream_status": self.config.downstream_status,
        }

