"""Tests for budget alerts — Slack webhook + SMTP email dispatch."""

from unittest.mock import MagicMock, patch

from cost_intel.alerts import (
    check_and_alert,
    send_email_alert,
    send_slack_alert,
)


class TestSendSlackAlert:
    """Tests for send_slack_alert."""

    def test_send_slack_alert_success(self):
        """Posts {"text": message} to webhook and returns True on HTTP 200."""
        with patch("cost_intel.alerts.httpx.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            result = send_slack_alert(
                webhook_url="https://hooks.slack.com/services/T/B/X",
                message="Budget alert: 85% used",
            )
            assert result is True
            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            assert kwargs["json"] == {"text": "Budget alert: 85% used"}

    def test_send_slack_alert_skips_without_url(self):
        """Returns False without making any HTTP call when URL is empty."""
        with patch("cost_intel.alerts.httpx.post") as mock_post:
            result = send_slack_alert(webhook_url="", message="test")
            assert result is False
            mock_post.assert_not_called()

    def test_send_slack_alert_returns_false_on_exception(self):
        """Swallows exceptions and returns False."""
        with patch("cost_intel.alerts.httpx.post", side_effect=RuntimeError("boom")):
            result = send_slack_alert(
                webhook_url="https://hooks.slack.com/x", message="msg"
            )
            assert result is False


class TestSendEmailAlert:
    """Tests for send_email_alert."""

    def test_send_email_alert_success(self):
        """Sends via smtplib.SMTP and returns True."""
        with patch("cost_intel.alerts.smtplib.SMTP") as mock_smtp:
            server = MagicMock()
            mock_smtp.return_value.__enter__.return_value = server
            mock_smtp.return_value.__exit__.return_value = False

            result = send_email_alert(
                smtp_host="smtp.example.com",
                smtp_from="alerts@example.com",
                recipients=["team@example.com"],
                subject="Budget Alert",
                body="Budget 85% used",
            )
            assert result is True
            mock_smtp.assert_called_once_with("smtp.example.com")
            server.sendmail.assert_called_once()
            args, _ = server.sendmail.call_args
            assert args[0] == "alerts@example.com"
            assert args[1] == ["team@example.com"]
            assert "Budget Alert" in args[2]
            assert "Budget 85% used" in args[2]

    def test_send_email_alert_skips_without_host(self):
        """Returns False when smtp_host is empty."""
        with patch("cost_intel.alerts.smtplib.SMTP") as mock_smtp:
            result = send_email_alert(
                smtp_host="",
                smtp_from="a@b.com",
                recipients=["c@d.com"],
                subject="test",
                body="test",
            )
            assert result is False
            mock_smtp.assert_not_called()

    def test_send_email_alert_skips_without_recipients(self):
        """Returns False when recipients list is empty."""
        with patch("cost_intel.alerts.smtplib.SMTP") as mock_smtp:
            result = send_email_alert(
                smtp_host="smtp.example.com",
                smtp_from="a@b.com",
                recipients=[],
                subject="test",
                body="test",
            )
            assert result is False
            mock_smtp.assert_not_called()


class TestCheckAndAlert:
    """Tests for check_and_alert."""

    def test_check_and_alert_triggers(self, tmp_cost_intel_home):
        """Budget at threshold (0%) triggers Slack alert."""
        from cost_intel.budget import set_budget
        from cost_intel.db import init_db

        init_db()
        set_budget(monthly=100.0, alert_threshold=0)

        with (
            patch(
                "cost_intel.alerts.send_slack_alert", return_value=True
            ) as mock_slack,
            patch(
                "cost_intel.alerts.load_config",
                return_value={
                    "slack_webhook_url": "https://hooks.slack.com/test",
                    "smtp_host": "",
                    "smtp_from": "",
                    "alert_recipients": [],
                },
            ),
        ):
            result = check_and_alert()

        assert result["triggered"] is True
        assert result["alert_sent"] is True
        assert "Budget" in result["message"]
        mock_slack.assert_called_once()

    def test_check_and_alert_no_trigger(self, tmp_cost_intel_home):
        """Budget below threshold (99%) does not trigger alerts."""
        from cost_intel.budget import set_budget
        from cost_intel.db import init_db

        init_db()
        set_budget(monthly=1000.0, alert_threshold=99)

        with (
            patch("cost_intel.alerts.send_slack_alert") as mock_slack,
            patch("cost_intel.alerts.send_email_alert") as mock_email,
            patch(
                "cost_intel.alerts.load_config",
                return_value={
                    "slack_webhook_url": "https://hooks.slack.com/test",
                    "smtp_host": "smtp.example.com",
                    "smtp_from": "alerts@example.com",
                    "alert_recipients": ["team@example.com"],
                },
            ),
        ):
            result = check_and_alert()

        assert result["triggered"] is False
        assert result["alert_sent"] is False
        mock_slack.assert_not_called()
        mock_email.assert_not_called()

    def test_check_and_alert_no_budget_set(self, tmp_cost_intel_home):
        """No budget configured → not triggered, no alerts sent."""
        from cost_intel.db import init_db

        init_db()
        result = check_and_alert()
        assert result["triggered"] is False
        assert result["alert_sent"] is False
