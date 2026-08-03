from __future__ import annotations

from pathlib import Path

from core.config.settings import Settings
from services.magento_log_generator_lambda import MagentoLogGenerateBody, generate_magento_logs


def test_generate_magento_logs_submits_bounded_incidents(tmp_path: Path) -> None:
    settings = Settings(
        local_store_path=tmp_path / "store.json",
        local_audit_path=tmp_path / "audit.jsonl",
    )
    result = generate_magento_logs(
        MagentoLogGenerateBody(total_events=5, fail_percent=100, max_incidents=2),
        settings=settings,
    )

    assert result.generated_events == 5
    assert result.failure_events == 5
    assert result.success_events == 0
    assert result.incident_events_submitted == 2
    assert len(result.incidents) == 2
    assert all(
        state.event and state.event.service_name == "magento-checkout"
        for state in result.incidents
    )
