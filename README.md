# cost-intel

AI spending tracker with cost-quality correlation.

A standalone Python CLI that tracks AI spending at the task level, optionally correlates it with quality scores, and produces cost-efficiency metrics.

## Install

```bash
pip install cost-intel
```

## Quick Start

```bash
# Record a cost run
cost-intel record --model "openai/gpt-4o" --input-tokens 150 --output-tokens 80 --label "summarize-doc"

# Show cost report
cost-intel report --last 7d

# Refresh model pricing
cost-intel refresh-pricing
```

## License

MIT
