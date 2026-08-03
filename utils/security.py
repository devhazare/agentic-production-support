from __future__ import annotations

import re

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[^'\"\s]+"),
    re.compile(r"(?i)authorization:\s*bearer\s+[a-z0-9._\-]+"),
]
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d .()\-]{8,}\d")
PROMPT_INJECTION_RE = re.compile(
    r"(?i)(ignore (all )?(previous|prior) instructions|developer message|system prompt|"
    r"reveal (the )?(prompt|secret)|act as|jailbreak)"
)


def scrub_sensitive_text(text: str, replacement: str = "[REDACTED]") -> str:
    scrubbed = text or ""
    for pattern in SECRET_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    scrubbed = EMAIL_RE.sub(replacement, scrubbed)
    scrubbed = PHONE_RE.sub(replacement, scrubbed)
    return scrubbed


def has_prompt_injection(text: str) -> bool:
    return bool(PROMPT_INJECTION_RE.search(text or ""))

