# Cost Intelligence — Dogfood Retrospective & Pricing Research

> **Date:** June 3, 2026
> **Purpose:** Real-world testing with Hermes session data + pricing system analysis

---

## What We Found

### 1. Hermes Real Usage (Last 30 Days)

| Metric | Value |
|--------|-------|
| Sessions | 153 |
| Total tokens | 6.5M in, 221K out |
| **Total cost** | **$0.18** |
| Free sessions | 138 (90%) |
| Paid sessions | 15 (10%) |

Cost breakdown by model:
- `llama-4-scout`: 7 runs, $0.17 (94% of spend)
- `granite4.1:3b`: 2 runs, $0.003
- `qwen-3-235b`: 1 run, $0.002
- `gpt-oss-120b`: 1 run, $0.001
- All free models (owl-alpha, nemotron-free): $0.00

### 2. Critical Bug: `* 1_000_000` in `refresh_all_pricing`

**File:** `src/cost_intel/pricing.py`, lines 185-186

```python
# Comment says: "OpenRouter returns per-million-token pricing"
# Reality: OpenRouter returns per-token pricing (e.g., 0.000000039)
input_price = float(pricing.get("prompt", 0)) * 1_000_000
output_price = float(pricing.get("completion", 0)) * 1_000_000
```

For `gpt-oss-120b`:
- OpenRouter returns: `prompt = "0.000000039"` (per-token)
- After `* 1_000_000`: `0.039` stored as "per-1K tokens"
- But `0.039` is actually the **per-1M** price, not per-1K
- `_compute_cost` then does `(tokens / 1000) * 0.039` = **1000x too high**

The comment is wrong. OpenRouter returns per-token pricing. The multiplication by 1M converts it to per-1M pricing. But the column is named `per_1k_tokens`. The `_compute_cost` function divides by 1000, expecting per-1K pricing. So the final result is 1000x inflated.

**Actual pricing for reference (per 1M tokens):**
| Model | Input | Output |
|-------|-------|--------|
| gpt-oss-120b | $0.039 | $0.18 |
| llama-4-scout | $0.08 | $0.30 |
| qwen-3-235b | $0.071 | $0.099 |
| granite-4.0-h-micro | $0.017 | $0.112 |
| owl-alpha | FREE | FREE |

### 3. Model Name Mismatch Problem

Hermes state.db uses different names than OpenRouter API:
- Hermes: `granite4.1:3b` → OpenRouter: `ibm-granite/granite-4.1-8b`
- Hermes: `gpt-oss-120b` → OpenRouter: `openai/gpt-oss-120b`
- Hermes: `openrouter/owl-alpha` → OpenRouter: `openrouter/owl-alpha` (matches)

When `get_pricing()` can't find a match, it returns None and cost = $0.
This silently zeros out costs for unmatched models.

### 4. Cost Is Dynamic — Three Moving Parts

```
cost = tokens × price_per_token
```

**All three variables change:**

1. **Tokens per session**: 2K to 1.5M input tokens (3 orders of magnitude)
2. **Model used**: 8+ models, $0 to $150/1M tokens (5 orders of magnitude)
3. **Pricing itself**: Models change price over time

### 5. Model Pricing Evolution (OpenRouter data, June 2026)

From the 343 models on OpenRouter:
- 25 models are free (7.3%)
- 318 models are paid (92.7%)
- Price range: $0.01 to $150 per 1M input tokens
- Median: $0.40 per 1M input tokens

**Key observation:** Every major model family has BOTH free and paid variants:
- `nvidia/nemotron-3-super-120b-a12b:free` → FREE
- `nvidia/nemotron-3-super-120b-a12b` → $0.09/1M in, $0.45/1M out
- `openai/gpt-oss-120b:free` → FREE  
- `openai/gpt-oss-120b` → $0.039/1M in, $0.18/1M out

This suggests OpenRouter (and providers) use a strategy of offering free tiers that can be upgraded. The `:free` suffix models are often rate-limited or lower-priority versions.

### 6. Historical Pricing — The Real Challenge

Model pricing changes over time. Examples from OpenRouter:
- Models start as free during beta, then become paid
- Prices decrease as models get more efficient (e.g., llama-3 vs llama-4)
- Prices increase when demand spikes
- Free tiers get discontinued

**The current schema is designed for this:**
- `model_pricing` has `(model_id, effective_date)` composite PK
- `is_current` flag for quick lookups
- Old pricing rows are preserved when prices change

**But the cost computation bakes the price:**
- `cost_run_calls.call_cost` is computed at record time using current pricing
- If pricing changes later, historical costs don't update
- This is a **design tension**: do we store the price at time of use, or recompute?

For the Hermes dogfood, this doesn't matter much because:
- Most sessions use free models (price = $0, won't change)
- The paid sessions are tiny ($0.18 total)
- Pricing for stable models changes slowly

But at scale (thousands of $, enterprise usage), pricing history matters.

---

## Architectural Implications

### Cost Tracking Needs a Reconciliation Layer

The current flow:
```
Hermes session → model name → get_pricing(model_name) → cost
```

This breaks when:
1. Model names don't match between systems (naming drift)
2. Pricing is missing for a model (new model, API lag)
3. Pricing changed retroactively (provider refunds, corrections)

**Needed:**
1. Model name mapping table (Hermes name ↔ OpenRouter ID)
2. Pricing fallback chain: exact match → prefix match → fuzzy match → default
3. Pricing freshness tracking with alerts
4. Cost recomputation capability for historical data

### Cost Is Effectively Free at Small Scale

90% of sessions use free models. The 10% paid sessions average $0.012 each.
At this scale, cost tracking is about:
- **Anomaly detection**: alert when a paid model is used unexpectedly
- **Trend tracking**: monitor the ratio of free vs paid over time
- **Audit trail**: know which tasks required paid models

### The Value Proposition Shifts with Scale

- **Small scale (<$10/month)**: Cost tracking = anomaly detection
- **Medium scale ($10-100/month)**: Cost tracking = optimization opportunities
- **Large scale ($100+/month)**: Cost tracking = cost avoidance, budget enforcement

Hermes is currently at the small scale. The OWL value prop ("unified cost-quality metric") is most valuable at medium-to-large scale.

---

## Action Items

1. [x] Fix `* 1_000_000` bug in `refresh_all_pricing` — Fixed in commit `6a12f43`. Changed `/ 1000` to `/ 1_000_000` and updated display label to `/1M`.
2. [ ] Add model name mapping/normalization layer — Deferred (structural limitation, see §Structural Accuracy Limitation)
3. [ ] Add pricing freshness tracking and alerts — Deferred
4. [ ] Add cost recomputation for historical data — Deferred
5. [ ] Add cost anomaly detection (alert when cost > Nσ for model) — Deferred
6. [x] Determine pricing unit convention — Fixed to per-1M tokens throughout. Verified in commit `6a12f43`.

_Note: items 2-5 are improvement ideas from dogfooding. The project is feature-complete per the 4-phase plan. These would be Phase 5+ work if AI spending scale justifies them._
