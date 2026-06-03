"""Tests for CSV import — ingest cost data from CSV files."""

from cost_intel.ingest import ingest_csv


class TestIngestCsv:
    """Tests for ingest_csv."""

    def test_ingest_standard_format(self, tmp_cost_intel_home):
        """Ingest standard CSV with timestamp, model, tokens, cost."""
        from cost_intel.db import init_db

        init_db()
        csv_content = (
            "timestamp,model,input_tokens,output_tokens,cost\n"
            "2026-06-03T10:00:00,openai/gpt-4o,1000,500,0.025\n"
            "2026-06-03T11:00:00,openai/gpt-4o,2000,1000,0.050\n"
            "2026-06-03T12:00:00,google/gemini-2.5-flash,500,200,0.008\n"
        )
        csv_path = tmp_cost_intel_home / "activity.csv"
        csv_path.write_text(csv_content)

        count = ingest_csv(str(csv_path), source="test")
        assert count == 3

    def test_ingest_with_source_tag(self, tmp_cost_intel_home):
        """Ingest CSV and verify source label is applied."""
        from cost_intel.db import get_connection, init_db

        init_db()
        csv_content = (
            "timestamp,model,input_tokens,output_tokens,cost\n"
            "2026-06-03T10:00:00,test/model,100,50,0.01\n"
        )
        csv_path = tmp_cost_intel_home / "test.csv"
        csv_path.write_text(csv_content)

        ingest_csv(str(csv_path), source="openrouter-export")

        conn = get_connection()
        row = conn.execute(
            "SELECT label FROM cost_runs WHERE model_id = ?", ("test/model",)
        ).fetchone()
        assert "openrouter-export" in row["label"]
        conn.close()

    def test_ingest_aggregated_format(self, tmp_cost_intel_home):
        """Ingest aggregated CSV with model, min, max, avg, sum columns."""
        from cost_intel.db import init_db

        init_db()
        csv_content = (
            "Model,Min,Max,Avg,Sum\n"
            "DeepSeek V4 Flash,$0.00,$0.25,$0.12,$0.25\n"
            "Gemini 3 Flash Preview,$0.04,$0.04,$0.04,$0.04\n"
        )
        csv_path = tmp_cost_intel_home / "aggregated.csv"
        csv_path.write_text(csv_content)

        count = ingest_csv(str(csv_path), format="aggregated")
        assert count == 2

    def test_ingest_auto_detect_format(self, tmp_cost_intel_home):
        """Auto-detect per-call vs aggregated format."""
        from cost_intel.db import init_db

        init_db()
        # Per-call format has timestamp column
        csv_per_call = (
            "timestamp,model,input_tokens,output_tokens,cost\n"
            "2026-06-03T10:00:00,test/model,100,50,0.01\n"
        )
        csv_path = tmp_cost_intel_home / "per_call.csv"
        csv_path.write_text(csv_per_call)

        count = ingest_csv(str(csv_path))
        assert count == 1

        # Aggregated format has Model column (capital M) and Min/Max/Avg/Sum
        csv_agg = "Model,Min,Max,Avg,Sum\nTest Model,$0.00,$0.25,$0.12,$0.25\n"
        csv_path2 = tmp_cost_intel_home / "agg.csv"
        csv_path2.write_text(csv_agg)

        count2 = ingest_csv(str(csv_path2))
        assert count2 == 1

    def test_ingest_dollar_signs_stripped(self, tmp_cost_intel_home):
        """CSV cost values with $ signs are parsed correctly."""
        from cost_intel.db import get_connection, init_db

        init_db()
        csv_content = (
            "timestamp,model,input_tokens,output_tokens,cost\n"
            "2026-06-03T10:00:00,test/model,100,50,$0.025\n"
        )
        csv_path = tmp_cost_intel_home / "dollar.csv"
        csv_path.write_text(csv_content)

        ingest_csv(str(csv_path))

        conn = get_connection()
        row = conn.execute(
            "SELECT call_cost FROM cost_run_calls WHERE model = ?", ("test/model",)
        ).fetchone()
        assert abs(row["call_cost"] - 0.025) < 0.001
        conn.close()

    def test_ingest_skips_invalid_rows(self, tmp_cost_intel_home):
        """Rows with missing or invalid data are skipped."""
        from cost_intel.db import init_db

        init_db()
        csv_content = (
            "timestamp,model,input_tokens,output_tokens,cost\n"
            "2026-06-03T10:00:00,test/model,100,50,0.01\n"
            "2026-06-03T11:00:00,,200,100,0.02\n"  # missing model
            "2026-06-03T12:00:00,test/model,abc,50,0.01\n"  # invalid tokens
            "2026-06-03T13:00:00,test/model,100,50,0.03\n"
        )
        csv_path = tmp_cost_intel_home / "invalid.csv"
        csv_path.write_text(csv_content)

        count = ingest_csv(str(csv_path))
        assert count == 2  # only valid rows

    def test_ingest_nonexistent_file(self, tmp_cost_intel_home):
        """Ingesting a nonexistent file returns 0."""
        count = ingest_csv("/nonexistent/file.csv")
        assert count == 0

    def test_ingest_empty_file(self, tmp_cost_intel_home):
        """Ingesting an empty CSV returns 0."""
        csv_path = tmp_cost_intel_home / "empty.csv"
        csv_path.write_text("timestamp,model,input_tokens,output_tokens,cost\n")

        count = ingest_csv(str(csv_path))
        assert count == 0

    def test_ingest_cost_stored_directly(self, tmp_cost_intel_home):
        """When CSV has a cost column, use it directly instead of computing."""
        from cost_intel.db import get_connection, init_db

        init_db()
        csv_content = (
            "timestamp,model,input_tokens,output_tokens,cost\n"
            "2026-06-03T10:00:00,test/model,100,50,0.123\n"
        )
        csv_path = tmp_cost_intel_home / "direct_cost.csv"
        csv_path.write_text(csv_content)

        ingest_csv(str(csv_path))

        conn = get_connection()
        row = conn.execute(
            "SELECT call_cost FROM cost_run_calls WHERE model = ?", ("test/model",)
        ).fetchone()
        assert abs(row["call_cost"] - 0.123) < 0.001
        conn.close()
