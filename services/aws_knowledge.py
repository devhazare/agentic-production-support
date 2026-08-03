from __future__ import annotations

import math
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path

from core.config.settings import Settings
from models import IncidentEvent, KnowledgeDocument

TOKEN_RE = re.compile(r"[a-zA-Z0-9_/-]+")
VECTOR_DIMENSIONS = 128


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def text_vector(text: str, dimensions: int = VECTOR_DIMENSIONS) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class KnowledgeService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._s3 = None
        self._os = None
        if settings.use_aws:
            import boto3
            from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

            self._s3 = boto3.client("s3", region_name=settings.aws_region)
            if settings.opensearch_endpoint:
                credentials = boto3.Session().get_credentials()
                auth = AWSV4SignerAuth(credentials, settings.aws_region, "aoss")
                self._os = OpenSearch(
                    hosts=[settings.opensearch_endpoint],
                    http_auth=auth,
                    connection_class=RequestsHttpConnection,
                    use_ssl=True,
                    verify_certs=True,
                )

    def upload_text(self, title: str, text: str, doc_type: str = "runbook") -> KnowledgeDocument:
        document_id = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        source_uri = f"s3://{self.settings.s3_bucket_name}/{doc_type}/{document_id}.md"
        if self._s3:
            self._s3.put_object(
                Bucket=self.settings.s3_bucket_name,
                Key=f"{doc_type}/{document_id}.md",
                Body=text.encode("utf-8"),
                ContentType="text/markdown",
            )
        else:
            path = Path(self.settings.local_data_dir) / ("runbooks" if doc_type == "runbook" else "rca_docs")
            path.mkdir(parents=True, exist_ok=True)
            (path / f"{document_id}.md").write_text(text, encoding="utf-8")
        doc = KnowledgeDocument(
            document_id=document_id,
            title=title,
            source_uri=source_uri,
            text=text,
            doc_type=doc_type if doc_type in {"runbook", "rca"} else "unknown",  # type: ignore[arg-type]
        )
        self.index_documents([doc])
        return doc

    def load_documents(self) -> list[KnowledgeDocument]:
        if self._s3:
            docs: list[KnowledgeDocument] = []
            for prefix, doc_type in [("runbook/", "runbook"), ("rca/", "rca")]:
                for obj in self._s3.list_objects_v2(Bucket=self.settings.s3_bucket_name, Prefix=prefix).get("Contents", []):
                    body = self._s3.get_object(Bucket=self.settings.s3_bucket_name, Key=obj["Key"])["Body"].read().decode("utf-8")
                    docs.append(self._doc_from_path(Path(obj["Key"]), body, doc_type))
            return docs
        docs = []
        for folder, doc_type in [("runbooks", "runbook"), ("rca_docs", "rca")]:
            for path in (Path(self.settings.local_data_dir) / folder).glob("*.md"):
                docs.append(self._doc_from_path(path, path.read_text(encoding="utf-8"), doc_type))
        return docs

    def index_documents(self, docs: list[KnowledgeDocument] | None = None) -> int:
        docs = docs or self.load_documents()
        if self._os:
            self._ensure_vector_index()
            for doc in docs:
                body = {
                    **doc.model_dump(),
                    "content_vector": text_vector(f"{doc.title} {doc.text}"),
                }
                # OpenSearch Serverless vector collections reject explicit IDs on
                # create/index requests. Keep the stable document_id in the body
                # for citations and allow AOSS to assign the storage ID.
                self._os.index(index=self.settings.opensearch_index, body=body)
        return len(docs)

    def search(self, event: IncidentEvent, top_k: int | None = None) -> list[KnowledgeDocument]:
        top_k = top_k or self.settings.rag_top_k
        query = f"{event.service_name} {event.alert_type} {event.metric_name} {event.logs_summary}"
        if self._os:
            try:
                result = self._os.search(
                    index=self.settings.opensearch_index,
                    body={
                        "size": top_k,
                        "query": {
                            "knn": {
                                "content_vector": {
                                    "vector": text_vector(query),
                                    "k": top_k,
                                }
                            }
                        },
                    },
                )
            except Exception:
                result = self._os.search(
                    index=self.settings.opensearch_index,
                    body={
                        "query": {"multi_match": {"query": query, "fields": ["title^2", "text"]}},
                        "size": top_k,
                    },
                )
            return [
                KnowledgeDocument.model_validate({**hit["_source"], "score": hit["_score"]})
                for hit in result["hits"]["hits"]
            ]
        return self._local_search(query, top_k)

    def _local_search(self, query: str, top_k: int) -> list[KnowledgeDocument]:
        docs = self.load_documents()
        q = Counter(tokenize(query))
        scored = []
        for doc in docs:
            d = Counter(tokenize(f"{doc.title} {doc.text}"))
            dot = sum(q[token] * d[token] for token in q)
            denom = math.sqrt(sum(v * v for v in q.values())) * math.sqrt(sum(v * v for v in d.values()))
            score = dot / denom if denom else 0.0
            scored.append(doc.model_copy(update={"score": score}))
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]

    def _doc_from_path(self, path: Path, text: str, doc_type: str) -> KnowledgeDocument:
        return KnowledgeDocument(
            document_id=path.stem,
            title=path.stem.replace("-", " ").replace("_", " ").title(),
            source_uri=f"s3://{self.settings.s3_bucket_name}/{doc_type}/{path.name}",
            text=text,
            doc_type=doc_type if doc_type in {"runbook", "rca"} else "unknown",  # type: ignore[arg-type]
        )

    def _ensure_vector_index(self) -> None:
        if not self._os or self._os.indices.exists(index=self.settings.opensearch_index):
            return
        self._os.indices.create(
            index=self.settings.opensearch_index,
            body={
                "settings": {"index": {"knn": True}},
                "mappings": {
                    "properties": {
                        "document_id": {"type": "keyword"},
                        "title": {"type": "text"},
                        "source_uri": {"type": "keyword"},
                        "text": {"type": "text"},
                        "doc_type": {"type": "keyword"},
                        "content_vector": {
                            "type": "knn_vector",
                            "dimension": VECTOR_DIMENSIONS,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "faiss",
                            },
                        },
                    }
                },
            },
        )
