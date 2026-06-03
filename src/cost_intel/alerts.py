"""Budget alert dispatch — Slack webhook + SMTP email."""

import smtplib
from email.mime.text import MIMEText
from typing import Any

import httpx

from cost_intel.budget import get_budget_status
from cost_intel.config import load_config


def send_slack_alert(webhook_url: str, message: str) -> bool:
    """Send alert to Slack via incoming webhook.

    Args:
        webhook_url: Slack incoming webhook URL.
        message: Plain text body for the Slack message.

    Returns:
        True on HTTP 200 response, False otherwise (including empty URL
        or any exception).
    """
    if not webhook_url:
        return False
    try:
        resp = httpx.post(
            webhook_url,
            json={"text": message},
            timeout=10.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


def send_email_alert(
    smtp_host: str,
    smtp_from: str,
    recipients: list[str],
    subject: str,
    body: str,
) -> bool:
    """Send alert via SMTP.

    Args:
        smtp_host: SMTP server hostname.
        smtp_from: Sender address.
        recipients: List of recipient addresses.
        subject: Email subject.
        body: Plain text email body.

    Returns:
        True on success, False if smtp_host or recipients are empty,
        or on any exception.
    """
    if not smtp_host or not recipients:
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = ", ".join(recipients)

        with smtplib.SMTP(smtp_host) as server:
            server.sendmail(smtp_from, recipients, msg.as_string())
        return True
    except Exception:
        return False


def _build_alert_message(status: dict[str, Any]) -> str:
    """Build a human-readable alert message from a budget status dict."""
    return (
        "⚠️ Cost Intelligence Budget Alert\n"
        f"Budget: ${status['monthly']:.2f}/month\n"
        f"Spent: ${status['spent']:.2f} ({status['percent_used']:.1f}%)\n"
        f"Remaining: ${status['remaining']:.2f}\n"
        f"Alert threshold: {status['alert_threshold']}%"
    )


def check_and_alert() -> dict[str, Any]:
    """Check budget status and dispatch alerts when threshold is reached.

    Reads ``slack_webhook_url``, ``smtp_host``, ``smtp_from``, and
    ``alert_recipients`` from config and routes the alert message to each
    configured channel.

    Returns:
        Dict with keys ``triggered`` (bool), ``alert_sent`` (bool), and
        ``message`` (str). ``alert_sent`` is True when at least one
        channel reported a successful dispatch.
    """
    result: dict[str, Any] = {
        "triggered": False,
        "alert_sent": False,
        "message": "",
    }

    status = get_budget_status()
    if not status["budget_set"]:
        return result

    if status["percent_used"] < status["alert_threshold"]:
        return result

    message = _build_alert_message(status)
    result["triggered"] = True
    result["message"] = message

    cfg = load_config()
    slack_webhook_url = cfg.get("slack_webhook_url", "") or ""
    smtp_host = cfg.get("smtp_host", "") or ""
    smtp_from = cfg.get("smtp_from", "") or ""
    recipients = cfg.get("alert_recipients", []) or []

    any_sent = False
    if slack_webhook_url:
        any_sent = send_slack_alert(slack_webhook_url, message) or any_sent
    if smtp_host and recipients:
        any_sent = (
            send_email_alert(
                smtp_host=smtp_host,
                smtp_from=smtp_from,
                recipients=list(recipients),
                subject="Cost Intelligence Budget Alert",
                body=message,
            )
            or any_sent
        )

    result["alert_sent"] = any_sent
    return result
