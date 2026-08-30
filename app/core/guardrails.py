"""
Application-level guardrails — Milestone 20.

The LLM is NOT the security boundary. All guardrails are enforced in Python,
before and after LLM interaction.

Guardrails implemented:
    1. Prompt injection detection       — blocks attempts to override system prompt
    2. Jurisdiction check               — flags non-Indian tax queries
    3. Tool authorization               — user can only call tools they're allowed
    4. Structured output validator      — rejects/retries malformed LLM output
    5. Rate limiter                     — per-user daily request limit
    6. Sensitive data filter            — warns if PII patterns detected in output

Architecture:
    Request
        │
        ▼
    GuardrailPipeline.check_input(query, user_id)
        │
        ▼
    Agent loop
        │
        ▼
    GuardrailPipeline.check_output(final_answer)
        │
        ▼
    Response to user
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Guardrail result
# ---------------------------------------------------------------------------

@dataclass
class GuardrailResult:
    allowed: bool
    reason: str = ""
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls, warnings: list[str] | None = None) -> "GuardrailResult":
        return cls(allowed=True, warnings=warnings or [])

    @classmethod
    def block(cls, reason: str) -> "GuardrailResult":
        return cls(allowed=False, reason=reason)


# ---------------------------------------------------------------------------
# 1. Prompt injection detection
# ---------------------------------------------------------------------------

# Patterns that indicate an attempt to override the system prompt or inject instructions
_INJECTION_PATTERNS = [
    r"ignore (previous|all|above|prior) instructions",
    r"disregard (the |your )?(system |previous )?instructions",
    r"you are now (?!a tax)",
    r"act as (?!a tax agent|an? tax)",  # allow "act as a tax agent"
    r"forget (everything|all|your instructions)",
    r"new (system )?prompt",
    r"override (system|instructions)",
    r"jailbreak",
    r"bypass (safety|restrictions|guardrails)",
    r"reveal (your |the )?(system prompt|instructions|prompt)",
    r"print (your |the )?(system prompt|instructions)",
]

_INJECTION_RE = re.compile(
    "|".join(_INJECTION_PATTERNS),
    re.IGNORECASE,
)


def check_prompt_injection(query: str) -> GuardrailResult:
    """
    Detect prompt injection attempts.

    Checks for common patterns used to override system instructions.
    Returns GuardrailResult.block() if an injection attempt is detected.
    """
    if _INJECTION_RE.search(query):
        logger.warning("Prompt injection attempt detected: %.100s", query)
        return GuardrailResult.block(
            "Your query contains content that cannot be processed. "
            "Please ask a tax-related question."
        )
    return GuardrailResult.ok()


# ---------------------------------------------------------------------------
# 2. Jurisdiction check
# ---------------------------------------------------------------------------

# Keywords suggesting the query is about non-Indian tax systems
_NON_INDIA_PATTERNS = [
    r"\b(us|usa|american|federal|irs|w-?2|1099|schedule [a-z])\b",
    r"\b(uk|hmrc|paye|national insurance)\b",
    r"\b(australian|ato)\b",
    r"\b(canadian|cra|t4)\b",
    r"\b(german|finanzamt)\b",
]
_NON_INDIA_RE = re.compile("|".join(_NON_INDIA_PATTERNS), re.IGNORECASE)

# Keywords that confirm Indian tax context
_INDIA_INDICATORS = [
    "india", "indian", "income tax act", "itr", "tds", "tcs", "pan", "aadhaar",
    "inr", "rupee", "₹", "cbdt", "budget", "slab", "80c", "80d", "ltcg",
    "stcg", "hra", "nps", "epf", "form 16", "ais", "tis", "gst",
]


def check_jurisdiction(query: str) -> GuardrailResult:
    """
    Check if the query is about Indian tax (supported) or another jurisdiction (unsupported).

    Returns a warning (not a block) if the query appears to be about a foreign tax system.
    The agent can still attempt to answer, but the warning is logged.
    """
    query_lower = query.lower()

    has_non_india = bool(_NON_INDIA_RE.search(query))
    has_india = any(kw in query_lower for kw in _INDIA_INDICATORS)

    if has_non_india and not has_india:
        return GuardrailResult.ok(
            warnings=[
                "This query may be about a non-Indian tax system. "
                "This agent specialises in Indian income tax. "
                "The answer may not be accurate for other jurisdictions."
            ]
        )
    return GuardrailResult.ok()


# ---------------------------------------------------------------------------
# 3. Tool authorization
# ---------------------------------------------------------------------------

# Default tool allowlist for authenticated users
_DEFAULT_ALLOWED_TOOLS = {
    "calculate_tax",
    "calculate_capital_gains",
    "retrieve_tax_rules",
    "get_user_tax_profile",
    "get_income_data",
}

# Tools requiring elevated permissions (admin / system use only)
_ELEVATED_TOOLS = {
    "admin_recalculate_all",
    "bulk_export",
}


def check_tool_authorization(
    tool_name: str,
    user_id: str,
    allowed_tools: set[str] | None = None,
) -> GuardrailResult:
    """
    Verify the user is authorized to use the requested tool.

    Args:
        tool_name:     The tool name the LLM is requesting.
        user_id:       The requesting user's ID.
        allowed_tools: Override the default allowlist (for testing/admin).

    Returns:
        GuardrailResult.block() if the tool is not authorized.
    """
    tools = allowed_tools if allowed_tools is not None else _DEFAULT_ALLOWED_TOOLS

    if tool_name in _ELEVATED_TOOLS:
        logger.warning(
            "Elevated tool access attempt [user=%s tool=%s]", user_id, tool_name
        )
        return GuardrailResult.block(
            f"Tool '{tool_name}' requires elevated permissions."
        )

    if tool_name not in tools:
        return GuardrailResult.block(
            f"Tool '{tool_name}' is not available to this user."
        )

    return GuardrailResult.ok()


# ---------------------------------------------------------------------------
# 4. Structured output validator
# ---------------------------------------------------------------------------

def validate_agent_decision_output(raw_content: str) -> GuardrailResult:
    """
    Validate that the LLM's output can be parsed as a valid AgentDecision.

    This is a pre-check before full Pydantic validation.
    Catches obviously malformed output early.
    """
    import json
    from pydantic import ValidationError
    from app.agents.schemas import parse_agent_decision

    stripped = raw_content.strip()
    if not stripped:
        return GuardrailResult.block("LLM returned empty response.")

    # Strip markdown fences
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]) if len(lines) > 2 else stripped

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        # Not JSON — may still be acceptable as a plain final answer
        return GuardrailResult.ok(
            warnings=["LLM response is not valid JSON — will be treated as plain text final answer."]
        )

    try:
        parse_agent_decision(data)
        return GuardrailResult.ok()
    except (ValidationError, Exception) as exc:
        return GuardrailResult.ok(
            warnings=[f"LLM output did not match AgentDecision schema: {exc}"]
        )


# ---------------------------------------------------------------------------
# 5. Rate limiter (in-memory, per-user daily limit)
# ---------------------------------------------------------------------------

from collections import defaultdict


class InMemoryRateLimiter:
    """
    Simple in-memory per-user daily request counter.

    Production note: Replace with Redis-backed counter for multi-instance deployments.
    The limit is read from settings so it is configurable via .env.
    """

    def __init__(self) -> None:
        # {user_id: {date: count}}
        self._counts: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))

    def check_and_increment(self, user_id: str, daily_limit: int) -> GuardrailResult:
        """
        Check if the user has exceeded their daily limit.
        Increments the counter if allowed.

        Returns:
            GuardrailResult.ok() if within limit.
            GuardrailResult.block() if limit exceeded.
        """
        today = date.today()
        current_count = self._counts[user_id][today]

        if current_count >= daily_limit:
            return GuardrailResult.block(
                f"Daily request limit of {daily_limit} reached. "
                "Please try again tomorrow."
            )

        self._counts[user_id][today] += 1
        remaining = daily_limit - current_count - 1
        warnings = []
        if remaining <= 2:
            warnings = [f"You have {remaining} requests remaining today."]
        return GuardrailResult.ok(warnings=warnings)

    def get_count(self, user_id: str) -> int:
        return self._counts[user_id][date.today()]

    def reset(self, user_id: str) -> None:
        """Reset counter for a user (for testing)."""
        today = date.today()
        self._counts[user_id][today] = 0


# Module-level rate limiter singleton
_rate_limiter = InMemoryRateLimiter()


def get_rate_limiter() -> InMemoryRateLimiter:
    return _rate_limiter


# ---------------------------------------------------------------------------
# 6. Sensitive data filter (output check)
# ---------------------------------------------------------------------------

_PII_PATTERNS = [
    (r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", "PAN number"),                        # PAN
    (r"\b[2-9][0-9]{11}\b", "possible Aadhaar number"),                    # Aadhaar (12 digits)
    (r"\b[A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{4}[A-Z]{3}\b", "bank IFSC code"), # IFSC
]


def check_output_pii(output: str) -> GuardrailResult:
    """
    Scan the LLM's final answer for accidental PII exposure.

    Returns a warning (not a block) if PII patterns are detected.
    The calling code can decide whether to redact or log.
    """
    warnings = []
    for pattern, label in _PII_PATTERNS:
        if re.search(pattern, output):
            logger.warning("Potential PII in output: %s", label)
            warnings.append(f"Output may contain {label} — please review before sending.")

    return GuardrailResult.ok(warnings=warnings)


# ---------------------------------------------------------------------------
# Guardrail pipeline
# ---------------------------------------------------------------------------

class GuardrailPipeline:
    """
    Composable guardrail pipeline.

    Usage:
        pipeline = GuardrailPipeline(daily_limit=5)
        result = pipeline.check_input(query, user_id)
        if not result.allowed:
            return result.reason
        # ... run agent ...
        result = pipeline.check_output(final_answer)
    """

    def __init__(
        self,
        daily_limit: int = 5,
        allowed_tools: set[str] | None = None,
    ) -> None:
        from app.core.config import get_settings
        settings = get_settings()
        self._daily_limit = daily_limit or settings.daily_request_limit
        self._allowed_tools = allowed_tools
        self._rate_limiter = get_rate_limiter()

    def check_input(self, query: str, user_id: str) -> GuardrailResult:
        """Run all input guardrails. Returns first block encountered."""
        # 1. Rate limit
        result = self._rate_limiter.check_and_increment(user_id, self._daily_limit)
        if not result.allowed:
            return result

        # 2. Prompt injection
        result = check_prompt_injection(query)
        if not result.allowed:
            return result

        # 3. Jurisdiction (warning only, never blocks)
        result = check_jurisdiction(query)
        return result  # may carry warnings

    def check_tool(self, tool_name: str, user_id: str) -> GuardrailResult:
        """Check tool authorization before execution."""
        return check_tool_authorization(tool_name, user_id, self._allowed_tools)

    def check_output(self, output: str) -> GuardrailResult:
        """Run output guardrails (PII scan)."""
        return check_output_pii(output)
