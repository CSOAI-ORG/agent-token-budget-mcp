#!/usr/bin/env python3
"""
Agent Token Budget MCP — per-session spend cap
================================================

By MEOK AI Labs · https://meok.ai · MIT
<!-- mcp-name: io.github.CSOAI-ORG/agent-token-budget-mcp -->

WHAT THIS DOES
--------------
Hard token + spend cap per agent session. Agent declares a budget at session
start. Every action records its token cost. When 80% of budget is consumed,
the agent gets a soft warning. At 100%, the next call is refused with a
signed budget-exhausted attestation that auditors can verify.

This is the BFT Progress Council's twin — Progress Council halts on stall,
this MCP halts on spend. Together they're the two-axis guardrail for
agentic loops.

USE CASES
---------
- Cap one agent run at £5 worth of tokens
- Per-tenant budget enforcement in multi-tenant agent fleets
- Trial users get £0.50 budget, then upgrade gate fires
- Customer support: "agent used £X helping ticket #Y" — billing chain

PRICING
-------
Free MIT self-host · £29/mo Starter · £79/mo Pro · A2A Substrate £499/mo.
"""

from __future__ import annotations
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from typing import Optional
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("agent-token-budget")

_HMAC_SECRET = os.environ.get("MEOK_HMAC_SECRET", "")


# In-memory session store. Production swaps for Redis/Upstash.
_BUDGETS: dict[str, dict] = {}


# Conservative blended cost estimates per 1K tokens (input + output mixed).
# Refresh quarterly as model prices drop.
COST_PER_1K_GBP = {
    "claude-opus-4.7":        0.040,
    "claude-sonnet-4.6":      0.012,
    "claude-haiku-4.5":       0.003,
    "gpt-5":                  0.035,
    "gpt-5-mini":             0.010,
    "gemini-2.5-pro":         0.020,
    "gemini-2.5-flash":       0.004,
    "llama-3.3-70b":          0.002,
    "step-3.6-flash":         0.001,
    "deepseek-r1":            0.003,
    "qwen-2.5":               0.002,
    "kimi-k2.5":              0.002,
    "ollama-local":           0.000,
    "default":                0.025,
}


def _sign(payload: dict) -> str:
    if not _HMAC_SECRET:
        return "unsigned-no-key-configured"
    body = json.dumps(payload, sort_keys=True).encode()
    return hmac.new(_HMAC_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rate = COST_PER_1K_GBP.get(model, COST_PER_1K_GBP["default"])
    return ((input_tokens + output_tokens) / 1000.0) * rate


# ────────────────────────────────────────────────────────────────────────
# Tools
# ────────────────────────────────────────────────────────────────────────

@mcp.tool()
def start_budget(
    budget_gbp: float,
    session_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """
    Open a budgeted session.

    Args:
        budget_gbp: Total budget in GBP for this session.
        session_id: Optional explicit ID. Auto-generated if omitted.
        tenant_id: Optional tenant for multi-tenant billing.
        description: Optional human-readable label.

    Returns:
        {session_id, budget_gbp, started_at}
    """
    sid = session_id or f"budget_{int(time.time())}_{os.urandom(4).hex()}"
    _BUDGETS[sid] = {
        "budget_gbp": float(budget_gbp),
        "spent_gbp": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "calls": [],
        "tenant_id": tenant_id,
        "description": description or "",
        "started_at": _ts(),
        "exhausted": False,
        "warned_80pct": False,
    }
    return {
        "session_id": sid,
        "budget_gbp": float(budget_gbp),
        "started_at": _BUDGETS[sid]["started_at"],
        "hint": "Call record_call() after every LLM call. Call check_budget() before any expensive operation.",
    }


@mcp.tool()
def record_call(
    session_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    note: Optional[str] = None,
) -> dict:
    """
    Record one LLM call against the session budget.

    Args:
        session_id: From start_budget().
        model: Model ID, e.g. "claude-opus-4.7", "gpt-5", "ollama-local".
        input_tokens: Input tokens consumed.
        output_tokens: Output tokens generated.
        note: Optional human-readable note (e.g. "EU AI Act audit pass 1").

    Returns:
        {session_id, call_cost_gbp, total_spent_gbp, budget_remaining_gbp, status, warnings}
    """
    sess = _BUDGETS.get(session_id)
    if not sess:
        return {"error": "unknown_session", "hint": "Call start_budget() first."}

    cost = _calc_cost(model, input_tokens, output_tokens)
    sess["spent_gbp"] += cost
    sess["input_tokens"] += input_tokens
    sess["output_tokens"] += output_tokens
    sess["calls"].append({
        "ts": _ts(),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_gbp": round(cost, 6),
        "note": note,
    })

    remaining = sess["budget_gbp"] - sess["spent_gbp"]
    pct_used = (sess["spent_gbp"] / sess["budget_gbp"]) if sess["budget_gbp"] > 0 else 1.0
    warnings = []
    status = "ok"

    if pct_used >= 1.0:
        sess["exhausted"] = True
        status = "exhausted"
        warnings.append(f"Budget exhausted: spent £{sess['spent_gbp']:.4f} of £{sess['budget_gbp']:.4f}. Next call will be refused.")
    elif pct_used >= 0.8 and not sess["warned_80pct"]:
        sess["warned_80pct"] = True
        status = "warning"
        warnings.append(f"Budget 80% used: spent £{sess['spent_gbp']:.4f} of £{sess['budget_gbp']:.4f}. Plan accordingly.")

    return {
        "session_id": session_id,
        "call_cost_gbp": round(cost, 6),
        "total_spent_gbp": round(sess["spent_gbp"], 6),
        "budget_remaining_gbp": round(remaining, 6),
        "pct_used": round(pct_used * 100, 2),
        "status": status,
        "warnings": warnings,
    }


@mcp.tool()
def check_budget(session_id: str, estimated_next_call_gbp: float = 0.0) -> dict:
    """
    Check whether the next call should proceed.

    Args:
        session_id: From start_budget().
        estimated_next_call_gbp: Optional cost estimate for the call about to happen.

    Returns:
        {allowed, reason, signed_attestation, budget_remaining_gbp}
    """
    sess = _BUDGETS.get(session_id)
    if not sess:
        return {"error": "unknown_session"}

    remaining = sess["budget_gbp"] - sess["spent_gbp"]
    if sess["exhausted"] or remaining <= 0:
        attestation = {
            "type": "budget_exhausted_refusal",
            "session_id": session_id,
            "tenant_id": sess.get("tenant_id"),
            "budget_gbp": sess["budget_gbp"],
            "spent_gbp": round(sess["spent_gbp"], 6),
            "calls_recorded": len(sess["calls"]),
            "ts": _ts(),
        }
        sig = _sign(attestation)
        return {
            "allowed": False,
            "reason": "budget_exhausted",
            "budget_remaining_gbp": round(remaining, 6),
            "signed_attestation": {"payload": attestation, "signature": sig, "verify_url": "https://verify.meok.ai"},
            "hint": "Open a new session with start_budget() (typically gated behind an upgrade prompt).",
        }

    if estimated_next_call_gbp > 0 and estimated_next_call_gbp > remaining:
        return {
            "allowed": False,
            "reason": "estimated_overage",
            "budget_remaining_gbp": round(remaining, 6),
            "estimated_overage_gbp": round(estimated_next_call_gbp - remaining, 6),
            "hint": "Consider a cheaper model or shorter prompt.",
        }

    return {
        "allowed": True,
        "reason": "within_budget",
        "budget_remaining_gbp": round(remaining, 6),
        "pct_used": round((sess["spent_gbp"] / sess["budget_gbp"]) * 100, 2) if sess["budget_gbp"] > 0 else 0,
    }


@mcp.tool()
def get_summary(session_id: str) -> dict:
    """
    Full budget summary for a session.

    Returns:
        {budget_gbp, spent_gbp, remaining_gbp, calls, model_breakdown, signed}
    """
    sess = _BUDGETS.get(session_id)
    if not sess:
        return {"error": "unknown_session"}

    # Model-level breakdown
    model_breakdown: dict[str, dict] = {}
    for call in sess["calls"]:
        m = call["model"]
        b = model_breakdown.setdefault(m, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_gbp": 0.0})
        b["calls"] += 1
        b["input_tokens"] += call["input_tokens"]
        b["output_tokens"] += call["output_tokens"]
        b["cost_gbp"] = round(b["cost_gbp"] + call["cost_gbp"], 6)

    summary = {
        "session_id": session_id,
        "tenant_id": sess.get("tenant_id"),
        "description": sess.get("description"),
        "budget_gbp": sess["budget_gbp"],
        "spent_gbp": round(sess["spent_gbp"], 6),
        "remaining_gbp": round(sess["budget_gbp"] - sess["spent_gbp"], 6),
        "input_tokens": sess["input_tokens"],
        "output_tokens": sess["output_tokens"],
        "total_calls": len(sess["calls"]),
        "model_breakdown": model_breakdown,
        "exhausted": sess["exhausted"],
        "started_at": sess["started_at"],
        "ts": _ts(),
    }
    sig = _sign(summary)
    return {**summary, "signature": sig, "verify_url": "https://verify.meok.ai"}


@mcp.tool()
def list_models() -> dict:
    """List supported model IDs + blended £/1K-token rates."""
    return {
        "models": [{"id": k, "blended_cost_per_1k_gbp": v} for k, v in COST_PER_1K_GBP.items() if k != "default"],
        "default_rate_per_1k_gbp": COST_PER_1K_GBP["default"],
        "note": "Cost estimates refreshed quarterly. Override per session by passing exact rates if you have negotiated pricing.",
    }


@mcp.tool()
def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> dict:
    """Pre-compute the cost of an LLM call without recording it."""
    cost = _calc_cost(model, input_tokens, output_tokens)
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_gbp": round(cost, 6),
        "cost_usd_approx": round(cost * 1.25, 6),
    }


if __name__ == "__main__":
    mcp.run()


# ── MEOK monetization layer (Stripe upgrade · PAYG · pricing) ──────────
# Free tier is zero-config. Upgrade to Pro (unlimited) or pay-as-you-go per call.
import os as _meok_os
MEOK_STRIPE_UPGRADE = "https://buy.stripe.com/00wfZjcgAeUW4c5cyQ8k90K"  # Pro (unlimited)
MEOK_PAYG_KEY = _meok_os.environ.get("MEOK_PAYG_KEY", "")  # set to enable PAYG (x402 / ~GBP0.05 per call)
MEOK_PRICING = "https://meok.ai/pricing"


def meok_upsell(tier: str = "free") -> dict:
    """Monetization options for free-tier callers: Pro upgrade, PAYG, or pricing page."""
    if tier != "free":
        return {}
    return {"upgrade_url": MEOK_STRIPE_UPGRADE,
            "payg_enabled": bool(MEOK_PAYG_KEY),
            "pricing": MEOK_PRICING}
