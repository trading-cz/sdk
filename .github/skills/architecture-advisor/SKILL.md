---
name: architecture-advisor
description: >-
  Use when: architecture review, design review, code review, validate design,
  architectural analysis, refactoring, SOLID, layer separation, clean architecture,
  SDK changes, messaging patterns, event routing, typed consumer, separation of concerns.
  NOT for: simple bug fixes, typos, config changes, one-line patches.
---

# Architecture Advisor — trading-cz SDK

## Core Rule

**Validate, don't redesign.** User states problem + proposed fix. Your job:

1. Verify against actual code across all repos
2. If correct → minimal implementation, zero extras
3. If issue found → state it concisely with specific code evidence
4. If missed consideration → raise it, don't silently "fix" it

## Architecture — Layer Model (3 layers)

```
L1: TransportProducer/Consumer     — raw bytes, Kafka protocol
L2: TypedProducer/TypedConsumer    — Pydantic serialization/deserialization
L3: EventRouter/RequestReply/F&F   — messaging patterns, routing, dispatch
```

**Non-negotiable rules:**
- L2 does NOT route or filter — it deserializes and yields. `types` is a deserialization capability map, NOT a filter.
- L3 does NOT deserialize — it routes and dispatches. L3 owns all filtering/routing decisions.
- No layer imports from a higher layer (L1 never imports L2/L3, L2 never imports L3).
- Dependencies: L3 → L2 → L1 → models/ (shared).

## Known Violations (to fix)

### `market_data/_base.py` — manual deserialization bypasses L2
- `_request_historical` (~line 243): Uses raw `TransportConsumer` + `model_validate_json()` instead of `TypedConsumer`
- `_stream` (~line 307): Same pattern — raw consumer + manual deserialize
- Both mix L2 (deserialization) + L3 (filtering/dedup) at application level
- Fix: Use `TypedConsumer` for deserialization, keep dedup/filtering in application code

## Project Conventions

- **Pylint 10.00/10** required, `mypy` strict, `ruff` clean
- **Python 3.12+**, modern syntax (union types `|`, no `Optional`)
- **Pydantic v2** for all models and settings
- **Event-driven**: Kafka as message bus, header-based dispatch via `event_type`
- **Shared topics**: Multiple services publish on same topic → consumers tolerate unknown event types silently

## Before Making Any Edit

- "Is this the minimal change that solves the stated problem?"
- "Am I adding anything the user didn't request?"
- "Does this respect the existing layer boundaries?"

## Common Pitfalls

1. **Filtering at wrong layer**: L2 must not ERROR on unknown types. L3 owns filtering.
2. **Deserialization at wrong layer**: L3 must not call `model_validate_json`. L2 owns deserialization.
3. **Redundant checks**: When L2 guarantees something, don't double-check in L3.
4. **Unasked generalization**: Don't add features unless explicitly requested.
5. **Using TransportConsumer directly** in application code: Always go through TypedConsumer for typed access.

## Repos Using This SDK

| Repo | Key files using SDK patterns |
|------|------------------------------|
| ingestion | `tradingcz/ingestion/app.py` — EventRouter |
| executor | `main.py` — EventRouter + typed dispatch |
| risk | `tradingcz/risk/app.py` — EventRouter |
| simple-strategy | `main.py` — strategy execution |
| testing | `simulator/`, `testkit/` — integration tests |
