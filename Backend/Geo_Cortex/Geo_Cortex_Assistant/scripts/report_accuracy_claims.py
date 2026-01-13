from __future__ import annotations

import os
import re
import subprocess
from typing import List, Tuple


def wilson_lower(successes: int, n: int, z: float = 1.96) -> float:
    # Wilson score interval lower bound for a binomial proportion.
    if n <= 0:
        return 0.0
    p = successes / n
    denom = 1.0 + (z * z) / n
    center = p + (z * z) / (2 * n)
    adj = z * ((p * (1 - p) / n + (z * z) / (4 * n * n)) ** 0.5)
    return max(0.0, (center - adj) / denom)


def _parse_ratio(line: str) -> Tuple[int, int]:
    m = re.search(r"\((\d+)\s*/\s*(\d+)\)", line)
    if not m:
        return 0, 0
    return int(m.group(1)), int(m.group(2))

def _summarize_rag_output(out: str, max_misses_show: int = 3) -> List[str]:
    """
    Make a stable, readable summary independent of how many misses are printed.
    """
    lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    golden_items = next((ln for ln in lines if ln.startswith("golden_items:")), "golden_items: ?")
    recall = next((ln for ln in lines if ln.startswith("recall@")), "recall@: ?")
    retrieval = next((ln for ln in lines if ln.startswith("retrieval_ms:")), "retrieval_ms: ?")
    misses = next((ln for ln in lines if ln.startswith("misses:")), "misses: ?")
    miss_lines = [ln for ln in lines if ln.startswith("- ")]
    if miss_lines:
        miss_lines = miss_lines[:max_misses_show]
    return [golden_items, recall, retrieval, misses] + miss_lines


def main() -> int:
    """
    Runs:
    - Golden RAG recall@5 on golden_rag.jsonl and holdout_rag.jsonl
    - Golden LLM workflow validated rate on a sample from golden and holdout

    Then prints Wilson 95% lower bounds so you can make a defensible claim.
    """
    # Keep runs short enough for demo environments; user can increase sample sizes.
    llm_n = int(os.getenv("CLAIM_LLM_N", "25"))
    rag_k = int(os.getenv("CLAIM_RAG_K", "5"))

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    eval_dir = os.path.join(root, "eval")

    golden_rag = os.path.join(eval_dir, "golden_rag.jsonl")
    holdout_rag = os.path.join(eval_dir, "holdout_rag.jsonl")
    golden_llm = os.path.join(eval_dir, "golden_llm_workflow.jsonl")
    holdout_llm = os.path.join(eval_dir, "holdout_llm_workflow.jsonl")

    print("== Defensible accuracy report ==")
    print(f"RAG k={rag_k}")
    print(f"LLM sample size per set={llm_n} (use CLAIM_LLM_N to change)")

    def run(cmd: list[str], env: dict) -> str:
        out = subprocess.check_output(cmd, cwd=root, env=env, text=True, stderr=subprocess.STDOUT)
        return out

    # RAG golden
    env = dict(os.environ)
    env["RAG_K"] = str(rag_k)
    env["RAG_GOLDEN_PATH"] = golden_rag
    out = run(["python", "scripts/eval_golden_rag.py"], env)
    print("\n-- RAG (golden) --")
    print(_summarize_rag_output(out))
    hits, total = 0, 0
    for line in out.splitlines():
        if line.startswith("recall@"):
            hits, total = _parse_ratio(line)
    rag_golden_lb = wilson_lower(hits, total)

    # RAG holdout
    env["RAG_GOLDEN_PATH"] = holdout_rag
    out = run(["python", "scripts/eval_golden_rag.py"], env)
    print("\n-- RAG (holdout) --")
    print(_summarize_rag_output(out))
    hits2, total2 = 0, 0
    for line in out.splitlines():
        if line.startswith("recall@"):
            hits2, total2 = _parse_ratio(line)
    rag_holdout_lb = wilson_lower(hits2, total2)

    # LLM golden (sample)
    env = dict(os.environ)
    env["EVAL_MAX_ITEMS"] = str(llm_n)
    env["EVAL_TIMEOUT_SEC"] = os.getenv("EVAL_TIMEOUT_SEC", "45")
    env["LLM_GOLDEN_PATH"] = golden_llm
    out = run(["python", "scripts/eval_golden_llm_workflow.py"], env)
    print("\n-- LLM summaries (golden sample) --")
    print(out.strip().splitlines()[-10:])
    ok, n = 0, 0
    for line in out.splitlines():
        if line.startswith("system_validated_rate:"):
            ok, n = _parse_ratio(line)
    llm_golden_lb = wilson_lower(ok, n)

    # LLM holdout (sample)
    env["LLM_GOLDEN_PATH"] = holdout_llm
    out = run(["python", "scripts/eval_golden_llm_workflow.py"], env)
    print("\n-- LLM summaries (holdout sample) --")
    print(out.strip().splitlines()[-10:])
    ok2, n2 = 0, 0
    for line in out.splitlines():
        if line.startswith("system_validated_rate:"):
            ok2, n2 = _parse_ratio(line)
    llm_holdout_lb = wilson_lower(ok2, n2)

    print("\n== 95% Wilson lower bounds (defensible) ==")
    print(f"RAG recall@{rag_k} golden lower bound:  {rag_golden_lb:.3f} (n={total})")
    print(f"RAG recall@{rag_k} holdout lower bound: {rag_holdout_lb:.3f} (n={total2})")
    print(f"LLM summary validated rate golden LB:   {llm_golden_lb:.3f} (n={n})")
    print(f"LLM summary validated rate holdout LB:  {llm_holdout_lb:.3f} (n={n2})")

    print("\nSuggested claim wording:")
    print(
        "- RAG retrieval: measured recall@5 on frozen golden and holdout sets.\n"
        "- LLM summaries: measured faithfulness/anti-dump validation rate on held-out prompts,\n"
        "  with deterministic fallback when the LLM is slow or violates constraints."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

