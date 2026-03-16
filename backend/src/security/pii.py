"""
AgentLens — PII Redaction & Security Service
Detects and redacts PII from trace payloads before storage.
Supports regex patterns + optional Presidio ML-based detection.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..core.config import get_settings
from ..core.logging import get_logger

logger = get_logger("security.pii")

# ─── Regex-based PII Patterns ────────────────────────────────────────────────

PATTERNS: Dict[str, re.Pattern] = {
    "email": re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b"
    ),
    "phone": re.compile(
        r"\b(\+?1?\s?)?(\(?\d{3}\)?[\s.\-]?)(\d{3}[\s.\-]?\d{4})\b"
    ),
    "ssn": re.compile(
        r"\b(?!000|666|9\d{2})\d{3}[-\s]?(?!00)\d{2}[-\s]?(?!0{4})\d{4}\b"
    ),
    "credit_card": re.compile(
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|"
        r"3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b"
    ),
    "ipv4": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
    "api_key": re.compile(
        r"\b(sk-[A-Za-z0-9]{32,}|sk-ant-[A-Za-z0-9\-_]{32,}|AIza[A-Za-z0-9\-_]{35})\b"
    ),
    "aws_key": re.compile(r"\b(AKIA|ASIA|AROA)[A-Z0-9]{16}\b"),
}

REDACT_PLACEHOLDER = "[REDACTED]"


class PIIRedactor:
    """
    Redacts personally identifiable information from arbitrary data structures.
    Operates on strings, dicts, and lists recursively.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = settings.pii_redaction_enabled
        enabled_keys = [
            k.strip() for k in settings.pii_redaction_patterns.split(",")
        ]
        self.active_patterns: Dict[str, re.Pattern] = {
            k: v for k, v in PATTERNS.items() if k in enabled_keys
        }
        # Optionally load Presidio for ML-based detection
        self._presidio_analyzer = None
        self._presidio_anonymizer = None
        self._try_load_presidio()

    def _try_load_presidio(self) -> None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine

            self._presidio_analyzer = AnalyzerEngine()
            self._presidio_anonymizer = AnonymizerEngine()
            logger.info("Presidio PII engine loaded")
        except ImportError:
            logger.debug("Presidio not available; using regex-only redaction")

    def redact_string(self, text: str) -> str:
        """Redact all PII patterns from a string."""
        if not self.enabled or not text:
            return text

        # 1. Regex patterns
        for pattern_name, pattern in self.active_patterns.items():
            text = pattern.sub(
                lambda m, pn=pattern_name: f"[{pn.upper()}_REDACTED]",
                text,
            )

        # 2. Presidio ML-based detection (if available)
        if self._presidio_analyzer:
            try:
                results = self._presidio_analyzer.analyze(
                    text=text, language="en"
                )
                if results:
                    anonymized = self._presidio_anonymizer.anonymize(
                        text=text, analyzer_results=results
                    )
                    text = anonymized.text
            except Exception as exc:
                logger.warning("Presidio redaction failed", error=str(exc))

        return text

    def redact(self, value: Any) -> Any:
        """Recursively redact PII from any value type."""
        if not self.enabled:
            return value
        if isinstance(value, str):
            return self.redact_string(value)
        if isinstance(value, dict):
            return {k: self.redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        return value

    def redact_trace_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Redact PII from trace input/output payloads.
        Operates on the serialized span/trace dict before storage.
        """
        sensitive_keys = {"input", "output", "error", "prompt", "completion",
                          "content", "message", "text", "query", "response"}
        result = {}
        for k, v in payload.items():
            if k in sensitive_keys:
                result[k] = self.redact(v)
            elif isinstance(v, dict):
                result[k] = self.redact_trace_payload(v)
            else:
                result[k] = v
        return result


# ─── RBAC ─────────────────────────────────────────────────────────────────────

ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "viewer": [
        "traces:read",
        "metrics:read",
        "alerts:read",
        "sessions:read",
    ],
    "developer": [
        "traces:read",
        "traces:write",
        "metrics:read",
        "alerts:read",
        "alerts:write",
        "sessions:read",
        "evals:read",
        "evals:write",
    ],
    "analyst": [
        "traces:read",
        "metrics:read",
        "alerts:read",
        "sessions:read",
        "evals:read",
        "datasets:read",
        "datasets:write",
    ],
    "admin": [
        "traces:read",
        "traces:write",
        "traces:delete",
        "metrics:read",
        "alerts:read",
        "alerts:write",
        "sessions:read",
        "evals:read",
        "evals:write",
        "datasets:read",
        "datasets:write",
        "api_keys:read",
        "api_keys:write",
        "settings:read",
        "settings:write",
        "users:read",
        "users:write",
    ],
    "security": [
        "traces:read",
        "metrics:read",
        "alerts:read",
        "audit_logs:read",
        "settings:read",
        "shadow_agents:read",
    ],
}


def check_permission(role: str, permission: str) -> bool:
    """Check if a role has a given permission."""
    return permission in ROLE_PERMISSIONS.get(role, [])


def require_permission(role: str, permission: str) -> None:
    """Raise PermissionError if the role lacks the required permission."""
    if not check_permission(role, permission):
        raise PermissionError(
            f"Role '{role}' does not have permission '{permission}'"
        )


# ─── Singletons ───────────────────────────────────────────────────────────────

_redactor: Optional[PIIRedactor] = None


def get_redactor() -> PIIRedactor:
    global _redactor
    if _redactor is None:
        _redactor = PIIRedactor()
    return _redactor
