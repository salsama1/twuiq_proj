# Evaluation (Golden + Holdout Sets)

This folder contains **frozen evaluation datasets** used to make defensible accuracy claims.
We keep **two sets**:

- **Golden**: initial frozen benchmark set (used for regression).
- **Holdout**: separate frozen set (used to reduce overfitting risk).

## Files

- `golden_rag.jsonl`
  - Held-out queries with expected MODS ids.
  - Used to compute **RAG recall@k**.

- `golden_llm_workflow.jsonl`
  - Held-out workflow prompts used to evaluate **LLM summary faithfulness** and **fallback rate**.

- `holdout_rag.jsonl`
  - Separate frozen RAG set (different phrasing templates).

- `holdout_llm_workflow.jsonl`
  - Separate frozen workflow set (different prompts/templates).

## How to run

From `Geo_Cortex_Assistant/`:

```bash
python scripts/eval_golden_rag.py
python scripts/eval_golden_llm_workflow.py
```

### Holdout runs

```bash
# RAG holdout
RAG_GOLDEN_PATH=eval/holdout_rag.jsonl python scripts/eval_golden_rag.py

# LLM workflow holdout
LLM_GOLDEN_PATH=eval/holdout_llm_workflow.jsonl python scripts/eval_golden_llm_workflow.py
```

### One-command “defensible accuracy” report

```bash
python scripts/report_accuracy_claims.py
```

