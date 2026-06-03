"""Braintrust adapter — import quality scores via the Braintrust REST API."""

from typing import Optional

import httpx

from cost_intel.quality import import_score


def import_from_api(
    api_key: str,
    project_id: str,
    experiment_id: Optional[str] = None,
    source: str = "braintrust",
    base_url: str = "https://api.braintrust.dev/v1",
) -> int:
    """Fetch quality scores from Braintrust and import them.

    Args:
        api_key: Braintrust API key (sent as ``Authorization: Bearer``).
        project_id: Braintrust project identifier.
        experiment_id: Optional experiment id. If omitted, all
            experiments under the project are imported.
        source: Provenance label written to ``quality_scores.source``.
        base_url: Braintrust API base URL.

    Returns:
        Count of imported rows.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    count = 0

    with httpx.Client(base_url=base_url, headers=headers, timeout=30) as client:
        if experiment_id:
            exp_ids = [experiment_id]
        else:
            resp = client.get(f"/projects/{project_id}/experiments")
            resp.raise_for_status()
            experiments = resp.json().get("data", [])
            exp_ids = [exp["id"] for exp in experiments]

        for eid in exp_ids:
            resp = client.get(f"/experiments/{eid}/events")
            resp.raise_for_status()
            events = resp.json().get("data", [])

            for event in events:
                run_id = event.get("run_id") or event.get("id")
                scores = event.get("scores", {})
                if not run_id or not scores:
                    continue
                score_val = scores.get("quality") or scores.get("score")
                if score_val is None:
                    numeric = [
                        v for v in scores.values() if isinstance(v, (int, float))
                    ]
                    score_val = numeric[0] if numeric else None
                if score_val is not None:
                    import_score(
                        run_id=str(run_id),
                        score=float(score_val),
                        source=source,
                        eval_dimensions=scores if len(scores) > 1 else None,
                    )
                    count += 1

    return count
