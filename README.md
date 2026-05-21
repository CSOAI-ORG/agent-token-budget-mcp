# Agent Token Budget MCP

> ## 🧱 Part of the MEOK A2A Substrate
>
> 13 A2A primitives as one signed pipeline for **£499/mo** (100K calls).
> See [meok.ai/a2a](https://meok.ai/a2a).

# Hard spend cap per agent session

<!-- mcp-name: io.github.CSOAI-ORG/agent-token-budget-mcp -->

[![PyPI](https://img.shields.io/pypi/v/agent-token-budget-mcp)](https://pypi.org/project/agent-token-budget-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## The product

Hard token + spend cap per agent session. Agent declares a budget at session start. Every action records its token cost. When 80% of budget is consumed, the agent gets a soft warning. At 100%, the next call is **refused** with a signed budget-exhausted attestation that auditors can verify.

This is the BFT Progress Council MCP's twin — Progress Council halts on **stall**, this MCP halts on **spend**. Together they're the two-axis guardrail for agentic loops.

## Tools

| Tool | Purpose |
|---|---|
| `start_budget(budget_gbp, session_id?, tenant_id?, description?)` | Open a budgeted session |
| `record_call(session_id, model, input_tokens, output_tokens, note?)` | Record cost of one LLM call |
| `check_budget(session_id, estimated_next_call_gbp?)` | Pre-flight: should the next call proceed? |
| `get_summary(session_id)` | Full breakdown by model + signed total |
| `list_models()` | Supported model IDs + blended £/1K rates |
| `estimate_cost(model, input_tokens, output_tokens)` | Cost preview |

## Supported models

Pre-loaded blended £/1K-token rates for: Claude Opus 4.7, Sonnet 4.6, Haiku 4.5, GPT-5, GPT-5-mini, Gemini 2.5 Pro/Flash, Llama 3.3 70B, Step 3.6 Flash, DeepSeek-R1, Qwen 2.5, Kimi K2.5, Ollama (local = £0). Default rate £0.025/1K applies for unknown models. Override per-session if you have negotiated pricing.

## Use cases

- **Cap one agent run at £5** of tokens → user upgrades after
- **Multi-tenant fleets** — track per-tenant spend for billing
- **Trial users** — £0.50 budget, then upgrade gate fires
- **Customer support** — "agent used £X helping ticket #Y" as signed evidence
- **Pair with `bft-progress-council-mcp`** for combined stall + spend guards

## Quick install

```bash
uvx agent-token-budget-mcp
pip install agent-token-budget-mcp
```

```json
{
  "mcpServers": {
    "agent-token-budget": {
      "command": "uvx",
      "args": ["agent-token-budget-mcp"]
    }
  }
}
```

## Worked example

```python
# Open £5 budget for one agent session
{"tool": "start_budget", "args": {"budget_gbp": 5.00, "description": "Customer support ticket #42"}}
# → { session_id: "budget_1779...", budget_gbp: 5.0 }

# Every time the agent calls an LLM, record it
{"tool": "record_call", "args": {
  "session_id": "budget_1779...",
  "model": "claude-opus-4.7",
  "input_tokens": 8000,
  "output_tokens": 1500,
  "note": "Initial diagnosis"
}}
# → { call_cost_gbp: 0.38, total_spent_gbp: 0.38, budget_remaining_gbp: 4.62, status: "ok" }

# Before any expensive call, check_budget()
{"tool": "check_budget", "args": {"session_id": "budget_1779...", "estimated_next_call_gbp": 0.50}}
# → { allowed: true, budget_remaining_gbp: 4.62 }

# When budget hits 100%, next check_budget returns:
# → { allowed: false, reason: "budget_exhausted", signed_attestation: {...verify.meok.ai...} }
```

## Sister MCPs

Part of the MEOK **A2A** pack:

- `bft-progress-council-mcp` — twin guardrail (stall axis)
- `agent-rate-limiter-mcp` — call-count throttle
- `agent-audit-logger-mcp` — hash-chained log of every record_call
- `agent-policy-enforcement-mcp` — per-agent IAM gates

Full catalogue: [meok.ai/anthropic-registry](https://meok.ai/anthropic-registry)

## Protocol coverage + Universal PAYG

| Option | Price | Best for |
|---|---|---|
| Self-host | £0 — MIT | Devs |
| Universal PAYG | £29/mo + £0.0002/call | Spiky usage |
| A2A Substrate | £499/mo | All 13 A2A MCPs |
| Universe | £1,499/mo | All 49 MCPs |
| Defence | £4,990/mo | Enterprise |

Buy: https://meok.ai/a2a

## Licence

MIT. By [MEOK AI Labs](https://meok.ai) (CSOAI LTD, UK Companies House 16939677).
