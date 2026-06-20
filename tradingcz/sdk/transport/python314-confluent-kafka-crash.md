# Python 3.14 + confluent-kafka Segfault/Abort on Cleanup

> **Status**: Workaround applied (2026-06-20)  
> **confluent-kafka tested**: 2.14.0, 2.14.2 — **both affected**  
> **librdkafka**: 2.14.x (bundled)  
> **Python**: 3.14.4  
> **OS**: Linux Ubuntu x86_64  
> **Kafka broker**: `confluentinc/cp-kafka:7.8.0` (Docker, single-node KRaft)

---

## 1. Symptoms — Exact Error Messages

Any code path that creates a confluent-kafka resource and later cleans it up
crashes the Python process. Two crash modes observed:

### Crash Mode 1: Segmentation Fault

```
Fatal Python error: Segmentation fault

Thread 0x00007619cffff6c0 [ThreadPoolExecu] (most recent call first):
  File "/usr/lib/python3.14/concurrent/futures/thread.py", line 116 in _worker
  File "/usr/lib/python3.14/threading.py", line 1024 in run

Extension modules: confluent_kafka.cimpl (total: 1)
Segmentation fault (core dumped)
```

Happens in `rd_kafka_consume_batch_queue` inside `librdkafka.so` when
`AIOConsumer.consume()` (batch) is used.

### Crash Mode 2: Fatal Abort

```
Fatal Python error: Aborted

Thread 0x000070a4d27fc6c0 [ThreadPoolExecu] (most recent call first):
  File "/usr/lib/python3.14/concurrent/futures/thread.py", line 119 in _worker
  File "/usr/lib/python3.14/threading.py", line 1024 in run

Current thread's C stack trace (most recent call first):
  Binary file "/usr/lib/x86_64-linux-gnu/libc.so.6", at abort+0x27

Extension modules: confluent_kafka.cimpl (total: 1)
Aborted (core dumped)
```

Happens during `ThreadPoolExecutor.shutdown(wait=True)` or when
`SyncProducer.__del__` / `AdminClient.__del__` runs during GC.

### When It Happens

Crashes happen during **cleanup / process exit**, NOT during normal operation.
Test logic executes correctly — messages are published, lifecycle events emitted.
Only cleanup crashes.

### Three Affected Resources

| Resource | Used by | Crash Location |
|---|---|---|
| `AIOConsumer` (async consumer) | `TransportConsumer` | `rd_kafka_consume_batch_queue` or executor shutdown |
| `AdminClient` | `KafkaTopicAdmin` | GC destructor when `self._admin = None` |
| `SyncProducer` | `TransportProducer` | `producer.flush()` inside `close()` → `__del__` |

---

## 2. Root Cause

### AIOConsumer

`confluent_kafka.aio.AIOConsumer.__init__` creates a `ThreadPoolExecutor(max_workers=2)`
internally, but `AIOConsumer.close()` **never shuts it down**:

```python
# confluent_kafka/aio/_AIOConsumer.py (v2.14.0, v2.14.2 — identical)

def __init__(self, consumer_conf, max_workers=2, executor=None):
    if executor is not None:
        self.executor = executor
    else:
        self.executor = ThreadPoolExecutor(max_workers=max_workers)  # ← created

async def close(self, *args, **kwargs):
    return await self._call(self._consumer.close, ...)  # ← executor NOT shut down!
```

On Python 3.14, when the process exits with librdkafka threads still running in
the executor, Python's interpreter shutdown triggers a segfault or abort.

Additionally, `rd_kafka_consume_batch_queue` (called by `consume()`) has a
Python 3.14-specific incompatibility that causes a segfault even during normal
operation. `poll()` (single-message retrieval) does not trigger this path.

### SyncProducer

`confluent_kafka.Producer.__del__` crashes on Python 3.14 when GC collects the
object. Setting `self._producer = None` triggers this. `Producer.close()` (added
in confluent-kafka 2.13.0) properly cleans up librdkafka resources.

### AdminClient

`confluent_kafka.admin.AdminClient` has **no `close()` method**. Its `__del__`
crashes on Python 3.14 during GC. The only safe option is to avoid triggering GC
by keeping the reference alive until process exit.

---

## 3. What Was Tried & Rejected

### Approach A: Self-managed executor + keep `consume()` (batch)

```python
# transport_consumer.py
self._executor = ThreadPoolExecutor(max_workers=2)
self._consumer = AIOConsumer(config, executor=self._executor)

async def poll(self):
    raw_msgs = await self._consumer.consume(num_messages=100, timeout=0.5)
    # ... process batch
```

**Result**: ❌ CRASH — `rd_kafka_consume_batch_queue` segfault still occurs.
The batch queue C code path has a Python 3.14 incompatibility that `poll()`
avoids.

### Approach B: `poll()` loop only, no self-managed executor

```python
# transport_consumer.py
self._consumer = AIOConsumer(config)  # let it own the executor

async def poll(self):
    msg = await self._consumer.poll(0.5)
    # ... single message
```

**Result**: ❌ CRASH — executor is never shut down, crash on process exit.

### Approach C: `consume(num_messages=1)` instead of full `poll()` loop

**Result**: ❌ CRASH — still goes through `rd_kafka_consume_batch_queue` internally.

### Upgrade: confluent-kafka 2.14.0 → 2.14.2

**Result**: ❌ No change. `AIOConsumer.close()` still does not shut down executor.
The `_AIOConsumer.py` source is identical in both versions for the `close()` method.

| Version | AIOConsumer.close() shuts executor? | rd_kafka_consume_batch_queue safe? |
|---|---|---|
| 2.14.0 | ❌ No | ❌ No |
| 2.14.2 | ❌ No | ❌ No |

---

## 4. How We Tested

### Test Command

```bash
# Start Kafka (if not running)
docker compose -f /home/ubuntu/git/testing/docker-compose.yml up -d kafka

# Run lifecycle integration tests
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 TEST_ENVIRONMENT=tst \
  timeout 120 .venv/bin/python -m pytest \
  tests/integration/sdk-service-app/test_lifecycle.py \
  -v --tb=long -m integration
```

### Test Coverage

The `test_lifecycle.py` tests exercise all three affected resources in a single
test (`test_start_emits_initializing_and_ready`):
- Creates a `ServiceApp` → creates `TransportProducer` (SyncProducer)
- Calls `app.start()` → creates `TransportConsumer` (AIOConsumer), `KafkaTopicAdmin` (AdminClient)
- Calls `app.close()` → flushes producer, closes consumer, closes admin
- Validates lifecycle events on Kafka topic

### How to Reproduce the Original Crash

To reproduce the original (unfixed) crash, temporarily revert the 3 fixes:

```bash
cd /home/ubuntu/git/sdk
git diff HEAD -- tradingcz/sdk/transport/ > /tmp/fixes.patch
git checkout HEAD -- tradingcz/sdk/transport/
# Run the test — it will crash
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 TEST_ENVIRONMENT=tst \
  timeout 30 .venv/bin/python -m pytest \
  /home/ubuntu/git/testing/tests/integration/sdk-service-app/test_lifecycle.py \
  -v --tb=long -m integration
# Re-apply fixes
git apply /tmp/fixes.patch
```

### How to Retest with Future confluent-kafka Releases

1. Upgrade confluent-kafka:
   ```bash
   cd /home/ubuntu/git/sdk
   .venv/bin/pip install confluent-kafka==<NEW_VERSION>
   ```

2. **Temporarily revert ONLY the `poll()` workaround** to test if `consume()` works:
   ```bash
   cd /home/ubuntu/git/sdk
   # Edit transport_consumer.py: replace poll() loop with consume() call
   # (the self-managed executor fix should stay)
   ```

3. Run the test:
   ```bash
   KAFKA_BOOTSTRAP_SERVERS=localhost:9092 TEST_ENVIRONMENT=tst \
     timeout 120 .venv/bin/python -m pytest \
     /home/ubuntu/git/testing/tests/integration/sdk-service-app/test_lifecycle.py \
     -v --tb=long -m integration
   ```

4. If `consume()` no longer crashes, the `poll()` workaround can be removed.
   The self-managed executor fix should remain until `AIOConsumer.close()`
   properly shuts down its executor.

5. To test if `AIOConsumer.close()` shuts down the executor (remove self-managed executor fix):
   ```bash
   git diff HEAD -- tradingcz/sdk/transport/transport_consumer.py  # review
   # Revert the self._executor lines, let AIOConsumer own it
   ```

6. To test if `AdminClient.__del__` is safe (remove admin keep-alive fix):
   ```bash
   git diff HEAD -- tradingcz/sdk/transport/kafka_topic.py  # review
   # Restore self._admin = None in close()
   ```

---

## 5. The Fix — What We Applied

### Fix 1: `transport_consumer.py` — Self-managed executor + `poll()` loop

**Failing code** (original):
```python
# __init__
self._consumer = AIOConsumer(config)  # creates own executor, never shuts down

# poll()
raw_msgs = await self._consumer.consume(
    num_messages=batch_size,
    timeout=timeout_s,
)
for msg in raw_msgs:
    if msg.error():
        await self._handle_error(msg)
        continue
    result.append(self._build_message(msg))
```

**Fixed code**:
```python
# __init__
# Own the executor so we can shut it down after consumer close.
# AIOConsumer creates its own ThreadPoolExecutor if none is passed,
# but never shuts it down — causing segfault on Python 3.14.
self._executor = ThreadPoolExecutor(max_workers=2)
self._consumer = AIOConsumer(config, executor=self._executor)

# poll()
# Use poll() (single message) instead of consume() (batch) to avoid
# a segfault in rd_kafka_consume_batch_queue on Python 3.14 +
# librdkafka 2.14.x.  Individual poll() calls are safe.
deadline = asyncio.get_running_loop().time() + timeout_s
while len(result) < batch_size:
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        break
    msg = await self._consumer.poll(min(remaining, 1.0))
    if msg is None:
        continue
    if msg.error():
        await self._handle_error(msg)
        continue
    result.append(self._build_message(msg))

# __aiter__ finally
await self._consumer.close()
self._closed = True
self._executor.shutdown(wait=False)  # non-blocking from __aiter__

# close()
await self._consumer.close()
self._closed = True
self._executor.shutdown(wait=True)   # blocking from main context
```

### Fix 2: `transport_producer.py` — Call `producer.close()` before dropping ref

**Failing code** (original):
```python
async def close(self) -> None:
    if not self._closed:
        try:
            await self.flush()
        except RuntimeError:
            pass
    self._producer = None       # ← __del__ crashes on Python 3.14
    self._closed = True
```

**Fixed code**:
```python
async def close(self) -> None:
    if not self._closed:
        try:
            await self.flush()
        except RuntimeError:
            pass
        # Close the underlying librdkafka producer to avoid segfault
        # during GC on Python 3.14.  Producer.close() was added in
        # confluent-kafka 2.13.0.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._producer.close)
        self._producer = None
        self._closed = True
```

### Fix 3: `kafka_topic.py` — Keep AdminClient reference alive

**Failing code** (original):
```python
async def close(self) -> None:
    self._admin = None           # ← __del__ crashes on Python 3.14
    self._created.clear()
    self._closed = True
```

**Fixed code**:
```python
async def close(self) -> None:
    """Mark the admin as closed. The underlying AdminClient reference
    is intentionally kept alive to avoid a segfault in AdminClient.__del__
    on Python 3.14. It will be released at process exit."""
    self._created.clear()
    self._closed = True
```

---

## 6. Note on Future confluent-kafka Releases

- **confluent-kafka 2.14.2** does NOT fix this issue.
- **What needs to happen upstream**:
  1. `AIOConsumer.close()` should call `self.executor.shutdown(wait=True)` after closing the consumer.
  2. `rd_kafka_consume_batch_queue` needs a Python 3.14 compatibility fix in librdkafka.
  3. `AdminClient` needs a `close()` method (or `__del__` must be Python 3.14-safe).
  4. `SyncProducer.__del__` must be Python 3.14-safe (already mitigated by explicit `.close()`).
- **When a new release arrives**, follow the retest procedure in §4 to check which
  workarounds can be removed. The `poll()` loop is the first candidate — if
  `consume()` no longer crashes, revert to `consume()` for better throughput.
  The self-managed executor should be kept until upstream fixes `close()`.

---

## 7. Related Issues

- [confluentinc/confluent-kafka-python #2146](https://github.com/confluentinc/confluent-kafka-python/issues/2146) — "Segfault in test suite with Python 3.14" (closed, fixed in 2.13.0 for C-level segfaults on closed objects)
- [confluentinc/confluent-kafka-python #2275](https://github.com/confluentinc/confluent-kafka-python/issues/2275) — "delete_records leads to crash with Python 3.14.6" (open)
- [confluentinc/confluent-kafka-python #2092](https://github.com/confluentinc/confluent-kafka-python/issues/2092) — "Add Free-Threaded Python Support in 3.14" (open)
- confluent-kafka v2.13.0: "Fixed segfault exceptions on calls against objects that had closed internal objects"
- confluent-kafka v2.12.1: "Added Python 3.14 support and dropped 3.7 support"
