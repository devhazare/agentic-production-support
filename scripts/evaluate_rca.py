from __future__ import annotations

import json
import sys
from pathlib import Path

from models import IncidentState


def evaluate(state: IncidentState) -> dict[str, object]:
    citations = set(state.rca.citations if state.rca else [])
    retrieved = {doc.source_uri for doc in state.retrieved_documents}
    unsupported_citations = sorted(citations - retrieved)
    groundedness = bool(state.rca and state.rca.probable_root_cause and citations)
    coverage = len(citations) / max(1, len(state.retrieved_documents))
    hallucination_flag = bool(unsupported_citations)
    confidence_ok = bool(state.rca and state.rca.confidence_score >= 0.75)
    human_override = state.approval.status.value if state.approval else "none"
    return {
        "incident_id": state.incident_id,
        "groundedness_check": groundedness,
        "citation_coverage": round(coverage, 2),
        "hallucination_flag": hallucination_flag,
        "unsupported_citations": unsupported_citations,
        "confidence_threshold_check": confidence_ok,
        "human_override_tracking": human_override,
    }


def main() -> None:
    path = Path(sys.argv[1])
    state = IncidentState.model_validate(json.loads(path.read_text(encoding="utf-8")))
    print(json.dumps(evaluate(state), indent=2))


if __name__ == "__main__":
    main()

