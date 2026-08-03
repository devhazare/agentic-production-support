from __future__ import annotations

from pathlib import Path

from core.config.settings import get_settings
from services.aws_knowledge import KnowledgeService


def main() -> None:
    settings = get_settings()
    service = KnowledgeService(settings)
    uploaded = 0
    for folder, doc_type in [("runbooks", "runbook"), ("rca_docs", "rca")]:
        for path in (Path(settings.local_data_dir) / folder).glob("*.md"):
            service.upload_text(
                title=path.stem.replace("-", " ").replace("_", " ").title(),
                text=path.read_text(encoding="utf-8"),
                doc_type=doc_type,
            )
            uploaded += 1
    print({"uploaded": uploaded, "indexed": service.index_documents()})


if __name__ == "__main__":
    main()
