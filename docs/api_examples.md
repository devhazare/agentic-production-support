# API Examples

Start the API first:

```bash
uvicorn api.main:app --reload --port 8000
```

## Versioned Health

```bash
curl http://localhost:8000/api/v1/health
```

## Versioned Incident Analysis

```bash
curl -X POST http://localhost:8000/api/v1/incidents/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "service": "checkout-api",
    "alert_type": "LatencySpike",
    "metrics": {
      "cpu_percent": 72,
      "error_rate": 0.12,
      "latency_p99_ms": 4200
    },
    "logs_snippet": "database connection acquisition timeout",
    "severity": "HIGH",
    "log_source": "java"
  }'
```

## MVP Incident Trigger

```bash
python scripts/simulate_incident.py sample_data/incidents/checkout_latency.json
```

## RAG Search

```bash
curl -X POST http://localhost:8000/api/v1/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query":"checkout database timeout","top_k":5}'
```

For the full route list, see [api_reference.md](api_reference.md).
