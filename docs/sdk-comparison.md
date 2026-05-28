# SDK Architecture Comparison & Final Recommendation

> **Date:** 2026-05-28
> **Context:** Comparing two SDK architecture proposals for `trading-sdk`
> **Goal:** Choose the approach that best serves simplicity, easy usage, performance, and maintainability.

---

## Overview of the Two Approaches

| | **Incremental** (`sdk-improvements.md`) | **Simplification** (`sdk-simplification.md`) |
|---|---|---|
| **Philosophy** | Fix what's broken in the current architecture. Keep the abstract transport layer. | Accept Kafka as permanent. Remove unnecessary abstraction. Add a business-level API. |
| **Transport ABCs** | Keep `Channel`/`Transport` ABCs | Remove them. `KafkaChannel`/`KafkaTransport` are the direct API. |
| **Message type** | Keep generic `Message` (add `headers` field) | Replace with honest `KafkaMessage` (has `offset`, `partition`, `topic` — no pretense) |
| **User-facing API** | `TypedProducer`/`TypedConsumer`/`RequestReplyClient` (same as today) | NEW business layer: `TradingApp.data.request_historical()`, `app.signals.publish()`, etc. |
| **Bootstrap code** | ~40 lines per service (unchanged) | ~4 lines per service |
| **Kafka knowledge required** | Yes — users must understand topics, channels, serializers, key functions | No — business-level API hides all Kafka concepts |
| **Disruption** | Low — additive changes, no breaking renames | Medium — removes files, renames modules, adds new layer |

---

## Detailed Comparison by Criterion

### 1. Simplicity

**Winner: Simplification.**

The incremental approach keeps complexity that exists today:
- A developer writing a strategy must still import 10+ SDK modules, create `KafkaSettings`, create `KafkaTransport`, create channels, create `TypedProducer`/`TypedConsumer`, create `RequestReplyClient`, wire up `key_fn` lambdas, create custom `Deserializer` classes for response filtering, etc.
- Every service copies the same ~40 lines of bootstrap code. This is the #1 source of bugs and onboarding friction.

The simplification approach makes the common case trivial:
```python
from tradingcz.sdk import TradingApp
app = TradingApp(env="dev", service_id="my-strategy")
await app.start()
bars = await app.data.request_historical(["AAPL"], days=14)
```

The incremental approach fixes internal architecture but never asks "what does the USER actually type?" The simplification approach starts from that question.

### 2. Easy Usage (No Kafka/Transport Knowledge)

**Winner: Simplification (decisively).**

This is the user's primary goal: *"they don't need to have any Kafka or transport layer knowledge — they focus on writing app more with business point of view."*

| Task | Incremental (user must know) | Simplification (user must know) |
|------|------------------------------|--------------------------------|
| Request historical bars | `DataRequest`, `DataReady`, `RequestReplyClient`, `request_serializer`, `response_deserializer`, `request_id_of`, `response_id_of`, `key_fn`, channel lifecycle, `Bar.model_validate_json()` | `app.data.request_historical(["AAPL"], days=14)` |
| Stream quotes | Same as above + `StreamQuote.model_validate_json()`, async channel management | `async for quote in app.data.stream_quotes(["AAPL"]):` |
| Publish signal | `TypedProducer`, `SignalKey`, `tracking_id`, `timestamp_utc_ms` computation | `await app.signals.publish(signal, tracking_id="...")` |

The incremental approach requires users to understand the `DataRequest → DataReady → consume channel` protocol. That's infrastructure knowledge, not business knowledge. The simplification approach encapsulates that protocol.

### 3. Clean Layering

**Winner: Tie — different trade-offs.**

**Incremental approach:**
```
TypedProducer/Consumer  →  Channel ABC  →  KafkaChannel
```
Clean in the academic sense: every layer has an interface, every dependency is abstract. But the interfaces exist for a future that will never come (non-Kafka transports). This is **speculative generality** — a recognized anti-pattern.

**Simplification approach:**
```
Business Layer (DataClient, SignalClient, etc.)
    ↓
Typed Layer (TypedProducer, TypedConsumer, RequestReplyClient)
    ↓
Kafka Layer (KafkaChannel, KafkaTransport, KafkaMessage)
    ↓
Serialization (JsonCodec)
    ↓
Models (Bar, Trade, TradingSignal, etc.)
```

Clean in the practical sense: each layer solves a real problem today. The business layer encapsulates patterns that are repeated in every service. The typed layer provides type-safe messaging. The Kafka layer provides direct access for power users. No layer exists "just in case."

**Assessment:** The simplification's layering is more honest and more useful. The only "abstraction" worth keeping is serialization (`Serializer`/`Deserializer`/`Codec` ABCs), because that has genuine value (future non-JSON formats).

### 4. Performance

**Winner: Tie.**

Both approaches use the same underlying `AIOProducer`/`AIOConsumer`, the same `JsonCodec`, the same async patterns. The business layer in the simplification approach is a thin wrapper — no extra copies, no extra serialization. `DataClient.stream_quotes()` is literally a generator that wraps `TypedConsumer` and adds parsing logic that users would otherwise write themselves.

The only theoretical overhead in the simplification approach is one extra function call through the business layer. This is negligible compared to network I/O.

### 5. Maintainability & Extensibility

**Winner: Simplification (narrow).**

**Adding a new message flow** (e.g., "request open positions"):

| | Incremental | Simplification |
|---|---|---|
| **Model** | Add `PositionRequest`/`PositionResponse` to `events.py` | Same |
| **Topic** | Add to `TopicRegistry` | Same |
| **User code** | Every consumer writes their own `RequestReplyClient` wiring, `key_fn`, `Deserializer` class, channel management | Add one method to `EventClient`: `request_positions()` |
| **New developer adopting it** | Copies 40 lines from another service, tweaks for positions | Calls `app.events.request_positions()` |

The business layer becomes the single place where message flows are implemented. When a flow changes (e.g., `DataRequest` gains a new field), only `DataClient` changes — not every strategy that uses it.

**Risk:** The business layer could become a "god object" if every possible flow is crammed into `DataClient`/`EventClient`. Mitigation: keep clients focused on one domain each (data, signals, events). If a new domain emerges (e.g., "risk checks"), add a new client (`RiskClient`).

### 6. Migration Cost

**Winner: Incremental.**

| | Incremental | Simplification |
|---|---|---|
| **Files changed** | ~8 (additive changes) | ~15 (removals, renames, additions) |
| **Breaking changes** | None (deprecation warnings only) | `Channel`/`Transport` removed, `kafka_key.py` renamed, `build_signal()` moved |
| **Services to update** | None required (but recommended for headers) | All 3 services need code changes |
| **Risk** | Very low | Medium |

The incremental approach is safer. You can merge it and services keep working. The simplification approach requires coordination.

**But:** Migration cost is a one-time pain. The simplification's benefits (less code in every service, easier onboarding, fewer bugs) are permanent. In a 3-service system, the migration is manageable.

### 7. Testability

**Winner: Tie.**

A common argument for keeping `Channel`/`Transport` ABCs is testability — you can mock the interface. But Python doesn't need ABCs for mocking. You can mock `KafkaChannel` directly:

```python
# Incremental approach — mock the ABC
mock_channel = unittest.mock.AsyncMock(spec=Channel)

# Simplification approach — mock the concrete class
mock_channel = unittest.mock.AsyncMock(spec=KafkaChannel)
```

Both work identically. The ABC adds no testability benefit in a duck-typed language.

### 8. Conceptual Integrity (Honesty)

**Winner: Simplification.**

The incremental approach pretends Kafka might be replaced. It has a `Message` dataclass that's "generic" but missing real Kafka fields. It has `Channel`/`Transport` ABCs with one implementation. It has docstrings mentioning REST/gRPC/WS that will never be implemented. This creates **false abstraction** — the worst kind, because it adds complexity without delivering flexibility.

The simplification approach is honest: "We use Kafka. Here's a clean Kafka-based SDK. Here's a business layer on top so you don't need to care."

---

## Common Ground: What Both Approaches Agree On

Both documents independently reached the same conclusions on these points — they are **non-negotiable fixes** regardless of which approach is chosen:

| Fix | Both agree |
|-----|-----------|
| Add Kafka headers support | ✅ |
| Move metadata from JSON keys to headers | ✅ |
| Keys should be plain strings for routing | ✅ |
| `build_signal()` should move out of `tradingcz.model` | ✅ |
| `StreamQuote` must be in SDK source | ✅ |
| Empty `__init__.py` files must be populated | ✅ |
| `TopicRegistry` should provide `key_fn`/`headers_fn` factories | ✅ |
| Executor must be bumped to latest SDK version | ✅ |
| Murmur2 hash utility should exist in SDK | ✅ |
| Shared error types needed | ✅ |

These are the "fix the foundation first" items. They should be done **before** any architectural refactor.

---

## Scored Comparison

| Criterion | Weight | Incremental | Simplification | Notes |
|-----------|--------|-------------|----------------|-------|
| Simplicity | 🔴 High | 5/10 | 9/10 | Simplification reduces bootstrap from 40→4 lines |
| Easy usage (no Kafka knowledge) | 🔴 High | 3/10 | 9/10 | Incremental still exposes Kafka concepts heavily |
| Clean layering | 🟡 Med | 7/10 | 8/10 | Incremental has speculative abstraction; simplification is honest |
| Performance | 🟡 Med | 9/10 | 9/10 | Same substrate |
| Maintainability | 🟡 Med | 6/10 | 8/10 | Business layer centralizes flow logic |
| Migration cost | 🟢 Low | 9/10 | 5/10 | One-time cost vs permanent benefit |
| Testability | 🟢 Low | 9/10 | 9/10 | Python mocks work without ABCs |
| Honesty / conceptual integrity | 🟡 Med | 5/10 | 9/10 | False abstraction vs honest Kafka |

**Weighted totals:**
- Incremental: (5×2 + 3×2 + 7×1 + 9×1 + 6×1 + 9×0.5 + 9×0.5 + 5×1) / 8.5 ≈ **5.6/10**
- Simplification: (9×2 + 9×2 + 8×1 + 9×1 + 8×1 + 5×0.5 + 9×0.5 + 9×1) / 8.5 ≈ **8.4/10**

---

## Final Recommendation

### Use the Simplification approach — with a phased execution plan.

**Why:**

1. **The user's primary goal is "easy usage" where developers write business logic, not plumbing.** The incremental approach never achieves this. It fixes internal architecture but leaves users with the same 40-line bootstrap they copy-paste today. The simplification approach makes the common case a one-liner.

2. **The only argument for keeping `Channel`/`Transport` ABCs is testability**, and Python doesn't need them for that. The ABCs are speculative generality — they exist for a future (non-Kafka transports) that the user has explicitly ruled out.

3. **The business layer is additive, not restrictive.** Power users who need custom flows can still use `TypedProducer`/`TypedConsumer`/`KafkaChannel` directly. The business layer is a convenience for the 80% case.

4. **The migration cost is manageable.** This is a 3-service system, not a 50-service monolith. The refactor can be done in phases over a few days.

### Execution Plan

```
Phase 1: Foundation (1-2 days) — do this FIRST, regardless of architecture choice
├── Add headers support to KafkaChannel.send()/receive()
├── Add KafkaMessage dataclass (honest Kafka wrapper)
├── Add shared error types (tradingcz/errors.py)
├── Add Murmur2 hash utility (tradingcz/transport/hash.py)
├── Add StreamQuote model to SDK source
├── Populate empty __init__.py files
├── Add key_fn/headers_fn factories to TopicRegistry
└── Rename kafka_key.py → message_headers.py (with deprecation shim)

Phase 2: Remove ABCs (1 day)
├── Remove tradingcz/transport/protocol.py (Channel/Transport/Message ABCs)
├── Update TypedProducer/TypedConsumer/RequestReplyClient to use KafkaChannel directly
└── Update all imports

Phase 3: Add Business Layer (1-2 days)
├── Add tradingcz/sdk/app.py (TradingApp)
├── Add tradingcz/sdk/data.py (DataClient)
├── Add tradingcz/sdk/signals.py (SignalClient)
└── Add tradingcz/sdk/events.py (EventClient)

Phase 4: Migrate Services (1 day each)
├── Migrate simple-strategy (easiest — just a consumer)
├── Migrate ingestion (slightly more complex — produces data)
└── Migrate executor (needs version bump first)

Phase 5: Cleanup (1 day)
├── Remove deprecated kafka_key.py
├── Remove build_signal() from model/signal.py
└── Update docs
```

### What to KEEP from the Incremental approach

The incremental analysis document (`sdk-improvements.md`) remains valuable as:
1. **An audit of current problems** — every finding (F-1 through F-11, C-1 through C-6, D-1 through D-7) is real and needs fixing.
2. **A reference for operational Kafka concerns** — the partition analysis, Murmur2 implementation, hot partition detection, and migration plan should be implemented regardless.
3. **A detailed implementation guide for Phase 1** — the corrected code snippets are directly usable.

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Business layer doesn't cover a flow someone needs | They use `TypedProducer`/`KafkaChannel` directly (still public). File an issue and we add it to the business layer. |
| `TradingApp` becomes a god object | Strict rule: one client class per domain (data, signals, events, risk, positions, ...). Each client is independently testable. |
| Migration breaks production | Phase services one at a time. Deploy ingestion first (it produces data), then strategies (they consume). Keep old and new code compatible during transition. |
| Team rejects the business layer as "too magical" | The business layer is thin (50-100 lines per client). It's not a framework — it's just a pre-wired convenience. Anyone can read the source in 5 minutes. |

---

## Summary

| Question | Answer |
|----------|--------|
| Which approach should we use? | **Simplification**, executed in phases. |
| Should we do the incremental fixes first? | **Yes — Phase 1 is shared.** Foundation fixes (headers, errors, hash, StreamQuote, init files, factories) are needed regardless. |
| When do we remove the ABCs? | **Phase 2** — after foundation is solid. |
| When does the business layer arrive? | **Phase 3** — after ABCs are gone. |
| Does power-user access go away? | **No.** `TypedProducer`, `TypedConsumer`, `KafkaChannel`, `KafkaTransport` remain public. The business layer is additive. |
| What about the original `sdk-improvements.md`? | Keep it as the detailed audit + implementation reference. It documents every problem found. |

**Bottom line:** The incremental approach fixes bugs. The simplification approach fixes the developer experience. We need both, but the simplification approach is the destination.
