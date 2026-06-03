# cost-intel

AI spending tracker with cost-quality correlation.

A standalone Python CLI that tracks AI spending at the task level, optionally correlates it with quality scores, and produces cost-efficiency metrics.

**Value prop:** No unified cost-quality metric in a CLI-native package.

## Install

```bash
pip install cost-intel
```

## Quick Start

```bash
# Record a cost run
cost-intel record --model "openai/gpt-4o" --input-tokens 150 --output-tokens 80 --label "summarize-doc"

# Show cost report for the last 7 days
cost-intel report --last 7d

# Show cost per quality point (CPQP) with percentile ratings
cost-intel cpqp --last 30d

# Refresh model pricing from OpenRouter
cost-intel refresh-pricing

# Set a monthly budget
cost-intel budget set --monthly 500

# Check budget status
cost-intel budget status
```

## Features

- **Cost tracking** — Record AI runs with token counts, compute costs from live pricing
- **Quality correlation** — Import quality scores, compute CPQP (cost-per-quality-point) with A/B/C/D/F percentile ratings
- **Waste detection** — Identify expensive low-quality runs
- **Model comparison** — Compare models by efficiency delta
- **Budget alerts** — Slack + SMTP alerts when spending exceeds thresholds
- **CI/CD gates** — Fail builds when CPQP exceeds a threshold
- **OTel traces** — Ingest OpenTelemetry spans, get trace-level cost breakdowns
- **Prompt optimization** — Analyze high-cost patterns and get trimming suggestions
- **Budget enforcement** — Hard-stop guard that blocks when budget is exceeded

## Commands

```
cost-intel record              Record a cost run
cost-intel report              Cost summary report
cost-intel trends              Daily spending or CPQP trends
cost-intel export              Export to CSV
cost-intel budget set          Set a budget
cost-intel budget status       Check budget status
cost-intel refresh-pricing     Fetch latest pricing from OpenRouter
cost-intel pricing set/show    Manual pricing override
cost-intel estimate            Estimate tokens/cost before a call
cost-intel ingest-api-responses  Ingest JSONL API responses
cost-intel cpqp                CPQP report with percentile ratings
cost-intel waste               Waste analysis + waste index
cost-intel compare-models      Compare models by efficiency
cost-intel optimize            Model routing + target CPQP suggestions
cost-intel import-scores       Import quality scores (CSV, Eval Harness, Braintrust)
cost-intel gate                CI/CD cost gate (exit 0/1)
cost-intel alert check         Run budget alerts
cost-intel alert test          Show configured alert channels
cost-intel trace-cost          OTel trace cost breakdown
cost-intel prompt-opt          Prompt optimization analysis
cost-intel guard               Budget enforcement guard
```

## Configuration

Config lives at `~/.cost-intel/config.yaml` (override with `COST_INTEL_HOME`):

```yaml
budget:
  monthly: 500

alerts:
  slack_webhook_url: "https://hooks.slack.com/..."
  email:
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    from: "alerts@example.com"
    to: "you@example.com"

quality:
  weights:
    accuracy: 0.5
    relevance: 0.3
    coherence: 0.2
```

## License

MIT
