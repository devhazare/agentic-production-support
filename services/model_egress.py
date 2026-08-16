from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.config.settings import Settings, get_settings
from core.exceptions import LLMError
from utils.security import scrub_sensitive_text


@dataclass(frozen=True)
class RedactionSummary:
    category: str
    count: int


@dataclass(frozen=True)
class SanitizedPayload:
    text: str
    redactions: list[RedactionSummary] = field(default_factory=list)

    @property
    def was_modified(self) -> bool:
        return any(item.count > 0 for item in self.redactions)


@dataclass(frozen=True)
class _Rule:
    category: str
    pattern: re.Pattern[str]


_RULES: tuple[_Rule, ...] = (
    _Rule("aws_arn", re.compile(r"\barn:(aws|aws-us-gov|aws-cn):[^\s,;\"']+", re.I)),
    _Rule("aws_account_id", re.compile(r"\b\d{12}\b")),
    _Rule("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    _Rule("jwt", re.compile(r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b")),
    _Rule("authorization_header", re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[a-z0-9._\-]+")),
    _Rule("secret_assignment", re.compile(r"(?i)\b(api[_-]?key|token|password|passwd|secret|credential)\s*[:=]\s*['\"]?[^'\"\s,;]+")),
    _Rule("connection_string", re.compile(r"(?i)\b(?:postgres|postgresql|mysql|mongodb|redis)://[^\s\"']+")),
    _Rule("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    _Rule("phone", re.compile(r"\+?\d[\d .()\-]{8,}\d")),
    _Rule("ip_address", re.compile(r"\b(?:10|127|169\.254|172\.(?:1[6-9]|2\d|3[01])|192\.168|[1-9]\d?|1\d\d|2[0-4]\d|25[0-5])(?:\.(?:\d{1,3})){3}\b")),
    _Rule("hostname", re.compile(r"\b[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?){2,}\b", re.I)),
    _Rule("file_path", re.compile(r"(?:(?:/[A-Za-z0-9._ -]+){2,}|(?:[A-Za-z]:\\(?:[^\\\s]+\\)+[^\\\s]+))")),
    _Rule("s3_uri", re.compile(r"\bs3://[^\s,;\"']+", re.I)),
    _Rule("resource_id", re.compile(r"\b(?:i|ami|sg|subnet|vpc|eni|vol|snap|igw|rtb|acl|nat)-[0-9a-f]{8,}\b", re.I)),
    _Rule("k8s_resource", re.compile(r"\b(?:pod|deployment|service|namespace|node|cluster)[/\s:=]+[a-z0-9][a-z0-9.-]*\b", re.I)),
    _Rule("env_resource_name", re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+){2,}-(?:dev|qa|stage|staging|prod|production)(?:-[a-z0-9]+)*\b", re.I)),
    _Rule("instance_type", re.compile(r"\b(?:[cmrtgxipz][0-9][a-z]*|inf[0-9]|trn[0-9]|p[0-9])\.(?:nano|micro|small|medium|large|xlarge|[0-9]+xlarge)\b", re.I)),
    _Rule("capacity", re.compile(r"(?i)\b(?:memory[_ -]?size|timeout|capacity|instance[_ -]?count|desired[_ -]?count|reserved[_ -]?concurrency|vcpus?|cpu|ram)\s*[:=]?\s*\d+(?:\.\d+)?\s*(?:mb|mib|gb|gib|tb|tib|ms|s|sec|seconds|minutes?|vcpu|cores?)?\b")),
    _Rule("capacity_value", re.compile(r"(?i)\b\d+(?:\.\d+)?\s*(?:mib|mb|gib|gb|tib|tb|vcpu|cores?)\b")),
)


def sanitize_for_model(text: str, purpose: str = "llm", settings: Settings | None = None) -> SanitizedPayload:
    settings = settings or get_settings()
    if not settings.model_egress_sanitization_enabled:
        return SanitizedPayload(text=text or "")

    redaction_token = settings.model_egress_redaction_token
    sanitized = scrub_sensitive_text(text or "", replacement=redaction_token)
    summaries: list[RedactionSummary] = []

    for rule in _RULES:
        sanitized, count = rule.pattern.subn(f"{redaction_token}:{rule.category}", sanitized)
        if count:
            summaries.append(RedactionSummary(rule.category, count))

    if settings.model_egress_fail_closed and _has_unredacted_high_risk_data(sanitized):
        raise LLMError(
            "Model egress blocked: sensitive data remained after sanitization",
            context={"purpose": purpose},
        )

    return SanitizedPayload(text=sanitized, redactions=summaries)


def sanitize_for_embedding(text: str, settings: Settings | None = None) -> SanitizedPayload:
    return sanitize_for_model(text, purpose="embedding", settings=settings)


def _has_unredacted_high_risk_data(text: str) -> bool:
    high_risk_patterns = (
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        re.compile(r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b"),
        re.compile(r"(?i)\b(?:password|secret|token|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s,;]+"),
        re.compile(r"(?i)\b(?:postgres|postgresql|mysql|mongodb|redis)://[^\s\"']+"),
    )
    return any(pattern.search(text) for pattern in high_risk_patterns)
