# API Examples

## Trigger

```bash
curl -X POST http://localhost:8000/incidents/trigger \
  -H 'content-type: application/json' \
  -d @sample_data/incidents/sqs_backlog.json
```

## List

```bash
curl http://localhost:8000/incidents
```

## Approve

```bash
curl -X POST http://localhost:8000/incidents/INC-1005/approve \
  -H 'content-type: application/json' \
  -d '{"approver":"sre@example.com","comment":"approved dry-run rollback"}'
```

## Upload Knowledge

```bash
curl -X POST http://localhost:8000/knowledge/upload \
  -H 'content-type: application/json' \
  -d '{"title":"Cache Saturation Runbook","doc_type":"runbook","text":"Symptoms: cache evictions and latency..."}'
```

