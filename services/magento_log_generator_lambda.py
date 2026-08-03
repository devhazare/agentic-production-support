from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from core.config.settings import Settings, get_settings
from models import IncidentEvent, IncidentState
from services.ops_store import IncidentStore


class MagentoLogGenerateBody(BaseModel):
    total_events: int = Field(default=100, ge=1, le=1000)
    fail_percent: int = Field(default=20, ge=0, le=100)
    trigger_incidents: bool = True
    max_incidents: int = Field(default=3, ge=0, le=10)


class MagentoLogGenerateResponse(BaseModel):
    generated_events: int
    failure_events: int
    success_events: int
    incident_events_submitted: int
    log_samples: list[str]
    incidents: list[IncidentState]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _magento_log_samples(failure_events: int, success_events: int) -> list[str]:
    samples = [
        (
            "[{ts}] main.INFO: Product page rendered from cache "
            "{{\"cache_hit\":true}} []"
        ).format(ts=_utc_now()),
        (
            '10.42.10.8 - - [{ts}] "GET /checkout/cart HTTP/1.1" 200 4280 "-" '
            '"Magento-HealthCheck/1.0"'
        ).format(ts=datetime.now(timezone.utc).strftime("%d/%b/%Y:%H:%M:%S %z")),
    ]
    if failure_events:
        samples.extend(
            [
                (
                    "[{ts}] main.CRITICAL: Payment gateway timeout while placing order "
                    "{{\"gateway\":\"stripe\",\"timeout_ms\":30000}} []"
                ).format(ts=_utc_now()),
                (
                    '10.42.14.19 - - [{ts}] "POST /checkout/onepage/saveOrder HTTP/1.1" '
                    '503 912 "-" "Mozilla/5.0 Chrome/124.0"'
                ).format(ts=datetime.now(timezone.utc).strftime("%d/%b/%Y:%H:%M:%S %z")),
            ]
        )
    return samples[:4] if success_events else samples[2:]


def _build_magento_event(index: int, failure_events: int, total_events: int) -> IncidentEvent:
    error_rate = round((failure_events / max(total_events, 1)) * 100, 2)
    severity = "Critical" if error_rate >= 50 else "High" if error_rate >= 20 else "Medium"
    return IncidentEvent(
        incident_id=f"INC-MAGENTO-{uuid4().hex[:8].upper()}",
        service_name="magento-checkout",
        severity=severity,
        timestamp=_utc_now(),
        alert_type="MagentoLogFailureSpike",
        metric_name="checkout_failure_rate_percent",
        metric_value=max(error_rate, 1.0),
        logs_summary=(
            f"Magento sample batch #{index}: {failure_events}/{total_events} generated events "
            "were failures. Example errors include payment gateway timeout, database deadlock, "
            "checkout lock wait timeout, and Redis/cache pressure."
        ),
    )


def generate_magento_logs(
    body: MagentoLogGenerateBody,
    settings: Settings | None = None,
) -> MagentoLogGenerateResponse:
    settings = settings or get_settings()
    failures = sum(
        1 for _ in range(body.total_events) if random.randrange(100) < body.fail_percent
    )
    successes = body.total_events - failures
    incident_count = min(failures, body.max_incidents) if body.trigger_incidents else 0
    store = IncidentStore(settings)
    incidents = []
    for i in range(incident_count):
        event = _build_magento_event(i + 1, failures, body.total_events)
        state = IncidentState(
            incident_id=event.incident_id,
            event=event,
            status="detected",
            decision_path=["magento_logs_generator: generated sample incident"],
        )
        incidents.append(store.save(state))
    return MagentoLogGenerateResponse(
        generated_events=body.total_events,
        failure_events=failures,
        success_events=successes,
        incident_events_submitted=len(incidents),
        log_samples=_magento_log_samples(failures, successes),
        incidents=incidents,
    )


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _payload_from_event(event: dict[str, Any]) -> dict[str, Any]:
    if "body" not in event:
        return event
    body = event.get("body") or "{}"
    if isinstance(body, dict):
        return body
    return json.loads(body)


def handler(event: dict[str, Any], context: object | None = None) -> dict[str, Any]:
    try:
        body = MagentoLogGenerateBody.model_validate(_payload_from_event(event))
        result = generate_magento_logs(body)
        return _response(200, result.model_dump(mode="json"))
    except (json.JSONDecodeError, ValidationError) as exc:
        return _response(400, {"message": "Invalid request body.", "detail": str(exc)})
    except Exception as exc:  # noqa: BLE001 - Lambda boundary must return JSON
        return _response(500, {"message": "Magento log generation failed.", "detail": str(exc)})
