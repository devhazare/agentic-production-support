# Runbook: Kafka Consumer Lag

## Symptoms
- `Kafka consumer lag at N messages (threshold: 5000)`
- Consumers not keeping up with producers
- Event processing delays causing downstream timeouts
- `Group: ml-pipeline` or similar consumer group falling behind

## Root Causes
1. **Single-threaded consumer** — one consumer thread cannot keep up with burst traffic
2. **Slow message processing** — each message takes too long (ML inference, DB writes)
3. **Partition imbalance** — all partitions assigned to one consumer instance
4. **Broker rebalance** — partition rebalancing stalled consumer group
5. **Dead letter queue backlog** — failed messages retried repeatedly

## Immediate Remediation Steps

### Step 1 — Check current lag
```bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group ml-pipeline
```

### Step 2 — Scale consumer threads
```python
# Increase from 1 → 8 consumer threads
from confluent_kafka import Consumer
consumer = Consumer({
    'bootstrap.servers': 'localhost:9092',
    'group.id': 'ml-pipeline',
    'max.poll.interval.ms': 300000,
    'session.timeout.ms': 45000,
})
# Use concurrent.futures.ThreadPoolExecutor for parallel processing
```

### Step 3 — Trigger partition rebalance
```bash
# Force rebalance by bouncing one consumer
kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --group ml-pipeline --reset-offsets --to-latest \
  --topic product-events --execute
```

### Step 4 — Temporarily skip to latest (if lag is unrecoverable)
```python
consumer.seek_to_end(*consumer.assignment())
```

## Prevention
- Alert threshold: lag > 5000 messages
- Use `cooperative-sticky` partition assignment strategy
- Add consumer thread count to auto-scaling metrics
- Separate fast-path and slow-path consumers

## MTTR Target: < 20 minutes
