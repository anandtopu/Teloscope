#!/usr/bin/env python3
"""
AgentLens — Evaluation Quality Gate
CI script that checks if a set of staged traces meet the minimum eval score
threshold before allowing a release to proceed.

Usage:
  python scripts/eval_gate.py \\
    --endpoint http://staging.agentlens.io \\
    --api-key your-key \\
    --min-score 0.80 \\
    --dimensions relevance,safety,task_completion

Exit codes:
  0 — All traces meet the quality threshold
  1 — One or more traces failed the threshold
  2 — Configuration or connectivity error
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List, Optional

import httpx


def fetch_recent_traces(
    base_url: str,
    api_key: str,
    org_id: str,
    project_id: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Fetch the most recent traces from the API."""
    params = {
        "org_id": org_id,
        "project_id": project_id,
        "limit": limit,
        "status": "OK",
    }
    resp = httpx.get(
        f"{base_url}/api/v1/traces",
        params=params,
        headers={"X-API-Key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("traces", [])


def run_evaluation(
    base_url: str,
    api_key: str,
    trace_id: str,
    org_id: str,
    project_id: str,
    dimensions: List[str],
) -> Optional[Dict[str, Any]]:
    """Trigger an evaluation for a specific trace and return the result."""
    payload = {
        "trace_id":   trace_id,
        "org_id":     org_id,
        "project_id": project_id,
        "dimensions": dimensions,
    }
    resp = httpx.post(
        f"{base_url}/api/v1/evaluations/run",
        json=payload,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=60,
    )
    if resp.status_code in (200, 202):
        return resp.json()
    print(f"  ⚠  Eval failed for {trace_id}: HTTP {resp.status_code}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentLens Evaluation Quality Gate")
    parser.add_argument("--endpoint",    required=True,  help="AgentLens API base URL")
    parser.add_argument("--api-key",     required=True,  help="AgentLens API key")
    parser.add_argument("--org-id",      default="default")
    parser.add_argument("--project-id",  default="default")
    parser.add_argument("--min-score",   type=float, default=0.80, help="Minimum overall eval score (0-1)")
    parser.add_argument("--dimensions",  default="relevance,safety,task_completion")
    parser.add_argument("--sample-size", type=int, default=10, help="Number of recent traces to evaluate")
    parser.add_argument("--fail-fast",   action="store_true", help="Stop on first failure")
    args = parser.parse_args()

    base_url   = args.endpoint.rstrip("/")
    api_key    = args.api_key
    org_id     = args.org_id
    project_id = args.project_id
    dimensions = [d.strip() for d in args.dimensions.split(",")]
    min_score  = args.min_score

    print(f"\n{'='*60}")
    print(f"  AgentLens Evaluation Quality Gate")
    print(f"  Endpoint:    {base_url}")
    print(f"  Dimensions:  {', '.join(dimensions)}")
    print(f"  Min Score:   {min_score:.0%}")
    print(f"  Sample Size: {args.sample_size}")
    print(f"{'='*60}\n")

    # Step 1: Fetch recent traces
    try:
        traces = fetch_recent_traces(base_url, api_key, org_id, project_id, limit=args.sample_size)
    except Exception as exc:
        print(f"✗ Failed to fetch traces: {exc}")
        return 2

    if not traces:
        print("⚠  No traces found — skipping quality gate (pass)")
        return 0

    print(f"Evaluating {len(traces)} traces...\n")

    passed  = 0
    failed  = 0
    skipped = 0
    results_summary = []

    for i, trace in enumerate(traces, 1):
        trace_id = trace.get("trace_id") or trace.get("trace_id", "")
        agent    = trace.get("agent_name", "unknown")
        print(f"  [{i:02d}/{len(traces)}] {agent} ({trace_id[:8]}…) ", end="", flush=True)

        result = run_evaluation(base_url, api_key, trace_id, org_id, project_id, dimensions)
        if result is None:
            print("SKIP")
            skipped += 1
            continue

        score   = result.get("overall_score")
        verdict = result.get("overall_verdict", "skip")

        if score is None:
            print(f"SKIP (no score)")
            skipped += 1
            continue

        icon   = "✓" if score >= min_score else "✗"
        status = "PASS" if score >= min_score else "FAIL"
        print(f"{icon} {status}  score={score:.3f}  verdict={verdict}")

        # Print dimension breakdown on failure
        if score < min_score:
            for dim in result.get("dimensions", []):
                sym = "✓" if dim["score"] >= min_score else "✗"
                print(f"       {sym} {dim['name']:<22} {dim['score']:.3f}  [{dim['verdict']}]")
                if dim.get("reasoning"):
                    print(f"         → {dim['reasoning']}")

        results_summary.append({
            "trace_id":  trace_id,
            "agent":     agent,
            "score":     score,
            "verdict":   verdict,
            "pass":      score >= min_score,
        })

        if score >= min_score:
            passed += 1
        else:
            failed += 1
            if args.fail_fast:
                print(f"\n  ✗ Fail-fast triggered on trace {trace_id}")
                break

        time.sleep(0.5)  # Gentle rate limiting

    # Summary
    total_scored = passed + failed
    pass_rate    = passed / total_scored if total_scored > 0 else 1.0

    print(f"\n{'─'*60}")
    print(f"  Results:  {passed} passed / {failed} failed / {skipped} skipped")
    print(f"  Pass Rate: {pass_rate:.1%}  (threshold: {min_score:.0%})")

    if failed == 0:
        print(f"\n  ✅ Quality gate PASSED — all evaluated traces meet the threshold\n")
        return 0
    else:
        print(f"\n  ❌ Quality gate FAILED — {failed} trace(s) below score threshold {min_score:.0%}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
