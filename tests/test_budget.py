"""Smoke tests for agent-token-budget-mcp."""
import sys, os, inspect, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (
    start_budget,
    record_call,
    check_budget,
    get_summary,
    list_models,
    estimate_cost,
    _BUDGETS,
)


def test_start_budget_creates_session():
    _BUDGETS.clear()
    r = start_budget(5.00, description="test")
    assert r["budget_gbp"] == 5.00
    assert r["session_id"].startswith("budget_")


def test_record_call_charges():
    _BUDGETS.clear()
    r1 = start_budget(5.00)
    sid = r1["session_id"]
    r2 = record_call(sid, "claude-opus-4.7", 8000, 1500)
    # 9500 / 1000 * 0.040 = 0.38
    assert abs(r2["call_cost_gbp"] - 0.38) < 0.001
    assert r2["status"] == "ok"


def test_record_call_warns_at_80pct():
    _BUDGETS.clear()
    r1 = start_budget(0.10)
    sid = r1["session_id"]
    # 9500 tokens of opus = £0.38 which exceeds 80% of £0.10 (warning at 0.08) → already exhausted
    r2 = record_call(sid, "claude-opus-4.7", 8000, 1500)
    assert r2["status"] == "exhausted"


def test_check_budget_refuses_when_exhausted():
    _BUDGETS.clear()
    r1 = start_budget(0.01)
    sid = r1["session_id"]
    record_call(sid, "claude-opus-4.7", 5000, 1000)
    r3 = check_budget(sid)
    assert r3["allowed"] is False
    assert "exhausted" in r3["reason"]
    assert "signed_attestation" in r3


def test_check_budget_refuses_on_estimated_overage():
    _BUDGETS.clear()
    r1 = start_budget(5.00)
    sid = r1["session_id"]
    r2 = check_budget(sid, estimated_next_call_gbp=10.00)
    assert r2["allowed"] is False
    assert r2["reason"] == "estimated_overage"


def test_check_budget_allows_within():
    _BUDGETS.clear()
    r1 = start_budget(5.00)
    sid = r1["session_id"]
    r2 = check_budget(sid, estimated_next_call_gbp=0.50)
    assert r2["allowed"] is True


def test_get_summary_breaks_down_by_model():
    _BUDGETS.clear()
    r1 = start_budget(10.00)
    sid = r1["session_id"]
    record_call(sid, "claude-opus-4.7", 1000, 500)
    record_call(sid, "gpt-5", 2000, 1000)
    record_call(sid, "claude-opus-4.7", 500, 200)
    s = get_summary(sid)
    assert s["total_calls"] == 3
    assert "claude-opus-4.7" in s["model_breakdown"]
    assert "gpt-5" in s["model_breakdown"]
    assert s["model_breakdown"]["claude-opus-4.7"]["calls"] == 2


def test_list_models_includes_known():
    r = list_models()
    ids = {m["id"] for m in r["models"]}
    assert "claude-opus-4.7" in ids
    assert "gpt-5" in ids
    assert "ollama-local" in ids


def test_estimate_cost_basic():
    r = estimate_cost("claude-sonnet-4.6", 5000, 500)
    # 5500 / 1000 * 0.012 = 0.066
    assert abs(r["cost_gbp"] - 0.066) < 0.001


def test_ollama_local_is_free():
    _BUDGETS.clear()
    r1 = start_budget(0.001)  # tiny budget
    sid = r1["session_id"]
    r2 = record_call(sid, "ollama-local", 1000000, 500000)  # huge tokens
    assert r2["call_cost_gbp"] == 0.0
    assert r2["status"] == "ok"


if __name__ == "__main__":
    g = dict(globals())
    fns = [v for k, v in g.items() if k.startswith("test_") and inspect.isfunction(v)]
    passed = failed = 0
    for fn in fns:
        try:
            fn()
            print(f"✓ {fn.__name__}")
            passed += 1
        except Exception as e:
            print(f"✗ {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
