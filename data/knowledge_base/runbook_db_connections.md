# Runbook: Database Connection Pool Exhaustion

## Symptoms
- `Connection is not available, request timed out after 30000ms`
- `DBPool Active:25 Idle:0 Max:25` in logs
- API returning 503 or very high latency
- Error rate spike on database-dependent endpoints

## Root Causes
1. **Pool size too small** — default pool size (10) insufficient for traffic
2. **Connection leak** — connections not returned on exception paths
3. **Long-running queries** — slow queries holding connections for minutes
4. **Missing timeout** — no connection timeout causes stale connections to accumulate

## Immediate Remediation Steps

### Step 1 — Check active connections
```python
# SQLAlchemy engine inspection
from sqlalchemy import inspect, text
with engine.connect() as conn:
    result = conn.execute(text("SELECT count(*), state FROM pg_stat_activity GROUP BY state"))
    print(result.fetchall())
```

### Step 2 — Kill long-running queries (PostgreSQL)
```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'active'
  AND query_start < NOW() - INTERVAL '5 minutes'
  AND query NOT LIKE '%pg_stat_activity%';
```

### Step 3 — Increase pool size temporarily
```python
# In your SQLAlchemy engine config
engine = create_engine(
    DATABASE_URL,
    pool_size=25,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True,
)
```

### Step 4 — Restart affected service
```bash
# Kubernetes
kubectl rollout restart deployment/order-service
# Local
kill $(lsof -t -i:8001) && python app.py &
```

## Prevention
- Set `pool_pre_ping=True` to detect stale connections
- Add `pool_timeout=30` — never wait forever
- Wrap all DB calls in try/finally to ensure connection return
- Monitor: alert when active connections > 80% of max_pool

## SLA
- MTTR target: < 10 minutes
- Severity: HIGH (service degraded), CRITICAL (service down)
