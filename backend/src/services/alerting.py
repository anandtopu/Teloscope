"""
AgentLens — Alerting & Anomaly Detection Service
Evaluates alert rules against live metrics and fires notifications.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

import httpx

from ..core.config import get_settings
from ..core.logging import get_logger
from ..models.trace import Alert, AlertRule, AlertSeverity

logger = get_logger("services.alerting")


# ─── Rule Evaluator ───────────────────────────────────────────────────────────

OPERATOR_MAP = {
    "gt":  lambda v, t: v > t,
    "gte": lambda v, t: v >= t,
    "lt":  lambda v, t: v < t,
    "lte": lambda v, t: v <= t,
    "eq":  lambda v, t: v == t,
}


class AlertingService:
    """
    Evaluates alert rules against current metrics and dispatches notifications.
    Intended to be called periodically (e.g., every 60 seconds by a background task).
    """

    def __init__(self, storage) -> None:
        self.storage = storage
        self.settings = get_settings()
        # In-memory rule cache — production would load from DB
        self._rules: Dict[str, AlertRule] = {}
        # Track fired-but-not-resolved alerts to avoid duplicates
        self._active_alerts: Dict[str, Alert] = {}

    def register_rule(self, rule: AlertRule) -> None:
        self._rules[rule.rule_id] = rule
        logger.info("Alert rule registered", rule_id=rule.rule_id, name=rule.name)

    def remove_rule(self, rule_id: str) -> None:
        self._rules.pop(rule_id, None)

    async def evaluate_all_rules(self) -> List[Alert]:
        """Evaluate all registered rules against current metrics."""
        fired: List[Alert] = []
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            try:
                alert = await self._evaluate_rule(rule)
                if alert:
                    fired.append(alert)
                    await self._dispatch_alert(alert, rule)
            except Exception as exc:
                logger.error("Rule evaluation failed", rule_id=rule.rule_id, error=str(exc))
        return fired

    async def _evaluate_rule(self, rule: AlertRule) -> Optional[Alert]:
        """Check a single alert rule against current metrics."""
        metrics = self.storage.get_metrics_summary(
            org_id=rule.org_id,
            project_id=rule.project_id,
            window_minutes=rule.window_minutes,
            agent_name=rule.agent_filter,
        )
        if not metrics:
            return None

        current_value = metrics.get(rule.metric)
        if current_value is None:
            logger.debug("Metric not found in summary", metric=rule.metric)
            return None

        operator_fn = OPERATOR_MAP.get(rule.operator)
        if not operator_fn:
            logger.warning("Unknown operator", operator=rule.operator)
            return None

        if operator_fn(current_value, rule.threshold):
            # Check if already firing to avoid duplicate alerts
            dedupe_key = f"{rule.rule_id}:{rule.metric}"
            if dedupe_key in self._active_alerts:
                return None  # Already active

            alert = Alert(
                rule_id=rule.rule_id,
                org_id=rule.org_id,
                severity=rule.severity,
                title=f"Alert: {rule.name}",
                description=(
                    f"Metric '{rule.metric}' is {current_value:.4f}, "
                    f"which is {rule.operator} threshold {rule.threshold:.4f} "
                    f"over the last {rule.window_minutes} minutes."
                ),
                metric=rule.metric,
                current_value=current_value,
                threshold=rule.threshold,
                agent_name=rule.agent_filter,
            )
            self._active_alerts[dedupe_key] = alert
            logger.warning(
                "Alert fired",
                rule_name=rule.name,
                metric=rule.metric,
                current=current_value,
                threshold=rule.threshold,
            )
            return alert
        else:
            # Metric back to normal — resolve active alert if any
            dedupe_key = f"{rule.rule_id}:{rule.metric}"
            if dedupe_key in self._active_alerts:
                self._active_alerts[dedupe_key].resolved_at = datetime.utcnow()
                del self._active_alerts[dedupe_key]
                logger.info("Alert auto-resolved", rule_name=rule.name, metric=rule.metric)
        return None

    async def _dispatch_alert(self, alert: Alert, rule: AlertRule) -> None:
        """Send alert notifications to configured channels."""
        tasks = []
        if rule.notify_slack and self.settings.slack_webhook_url:
            tasks.append(self._notify_slack(alert))
        if rule.notify_pagerduty and self.settings.pagerduty_api_key:
            tasks.append(self._notify_pagerduty(alert))
        if rule.notify_email:
            tasks.append(self._notify_email(alert, rule.notify_email))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _notify_slack(self, alert: Alert) -> None:
        severity_emoji = {
            AlertSeverity.INFO:     "ℹ️",
            AlertSeverity.WARNING:  "⚠️",
            AlertSeverity.ERROR:    "🔴",
            AlertSeverity.CRITICAL: "🚨",
        }.get(alert.severity, "⚠️")

        payload = {
            "text": f"{severity_emoji} *AgentLens Alert* [{alert.severity.upper()}]",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": f"{severity_emoji} {alert.title}"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": alert.description}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Metric:*\n{alert.metric}"},
                    {"type": "mrkdwn", "text": f"*Current:*\n{alert.current_value:.4f}"},
                    {"type": "mrkdwn", "text": f"*Threshold:*\n{alert.threshold:.4f}"},
                    {"type": "mrkdwn", "text": f"*Agent:*\n{alert.agent_name or 'all'}"},
                ]},
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(self.settings.slack_webhook_url, json=payload)
                resp.raise_for_status()
            logger.debug("Slack notification sent", alert_id=alert.alert_id)
        except Exception as exc:
            logger.error("Slack notification failed", error=str(exc))

    async def _notify_pagerduty(self, alert: Alert) -> None:
        payload = {
            "routing_key": self.settings.pagerduty_api_key,
            "event_action": "trigger",
            "dedup_key": alert.alert_id,
            "payload": {
                "summary": alert.title,
                "severity": alert.severity.value,
                "source": "agentlens",
                "custom_details": {
                    "description": alert.description,
                    "metric": alert.metric,
                    "current_value": alert.current_value,
                    "threshold": alert.threshold,
                },
            },
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json=payload,
                )
                resp.raise_for_status()
            logger.debug("PagerDuty event sent", alert_id=alert.alert_id)
        except Exception as exc:
            logger.error("PagerDuty notification failed", error=str(exc))

    async def _notify_email(self, alert: Alert, recipients: List[str]) -> None:
        # Email sending via SMTP — stub for extensibility
        logger.info(
            "Email alert (stub)",
            recipients=recipients,
            title=alert.title,
        )

    def get_active_alerts(self) -> List[Alert]:
        return list(self._active_alerts.values())
