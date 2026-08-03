# Runbook: CUDA Out of Memory — ML Inference

## Symptoms
- `torch.cuda.OutOfMemoryError: CUDA out of memory`
- `Tried to allocate X GiB` in logs
- ML inference service returning 503 or timing out
- GPU memory utilisation at 95–100% on `nvidia-smi`

## Root Causes
1. **Batch size too large** — input batch does not fit in GPU VRAM
2. **GPU instance downgrade** — migrated from A100 (40GB) to T4 (16GB) without adjusting batch size
3. **Model cache not cleared** — multiple model versions resident simultaneously
4. **Memory leak in inference loop** — tensors not released after each batch

## Immediate Remediation Steps

### Step 1 — Reduce batch size immediately
```python
# Reduce from 128 → 32 to stabilise
import torch
device = torch.cuda.get_device_properties(0)
safe_batch = max(1, int(device.total_memory / (1024**3) / 2))
model.batch_size = safe_batch
```

### Step 2 — Clear GPU cache
```python
import torch
torch.cuda.empty_cache()
torch.cuda.synchronize()
```

### Step 3 — Restart inference service
```bash
kubectl rollout restart deployment/ml-inference
# or locally:
kill -9 $(pgrep -f ml-inference)
python ml_service.py &
```

### Step 4 — Monitor GPU memory
```bash
nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv -l 5
```

## Long-term Fix
- Use `torch.cuda.get_device_properties()` to set batch size dynamically
- Add GPU memory alert at 80% threshold
- Implement canary deployment for model updates
- Separate model loading from inference workers

## Escalation
- MTTR target: < 15 minutes
- Severity: HIGH if single pod; CRITICAL if all replicas affected
- Page ML platform team if memory leak suspected
