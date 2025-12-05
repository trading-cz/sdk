# Trading Model Repository

Shared data models for the trading platform.

## Overview

- **Schema format**: Avro Schema (`.avsc`) - single source of truth
- **Generated code**: Python classes (Pydantic) via `dc-avro` CLI
- **Kafka payload**: JSON (key and value) - Avro binary planned for future

## GitHub Actions

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `generate-models-on-pr.yml` | Pull Request | Detects `.avsc` changes → generates Python models → auto-commits to PR |
| `build-and-push.yml` | Tag `v*.*.*` | Builds package from pre-generated models → publishes to GitHub Packages |

**Install published package:**
```bash
pip install trading-model --index-url https://pypi.pkg.github.com/trading-cz/simple
```

## Repository Structure

```
schemas/                          # Avro schemas (source of truth)
├── kafka/                        # Kafka message schemas
│   └── <topic-name>/
│       ├── key.avsc
│       └── value.avsc
└── <future-system>/              # Other systems can be added here

src/                              # Generated at build time (not in repo)
└── cz/trading/model/
    └── kafka/<topic-name>/
        ├── key.py
        └── value.py
```

## Developer Workflow

### 1. Design a new schema

Create Avro schemas in `schemas/kafka/<topic-name>/`:

```bash
schemas/kafka/market-data/key.avsc
schemas/kafka/market-data/value.avsc
```

### 2. Create Pull Request

GitHub Actions (`generate-models-on-pr.yml`) will automatically:
- Detect if any `.avsc` files changed
- Validate schemas (`dc-avro lint`)
- Generate Python models and commit them to your PR

### 3. Release

Create a git tag:

```bash
git tag v0.0.1
git push origin v0.0.1
```

GitHub Actions (`build-and-push.yml`) will:
- Verify generated models exist
- Build Python package
- Publish to GitHub Packages

### 4. Consume in other repositories

```toml
# pyproject.toml
dependencies = ["trading-model>=0.0.1"]
```

```python
from cz.trading.model.kafka.market_data import MarketDataKey, MarketDataValue

# Serialize to JSON for Kafka
key = MarketDataKey(message_id="...", tracking_id="...", ...)
value = MarketDataValue(symbol="AAPL", price=150.0, ...)

producer.send(
    topic="market-data",
    key=key.model_dump_json().encode(),
    value=value.model_dump_json().encode(),
)

# Deserialize from Kafka JSON
key = MarketDataKey.model_validate_json(msg.key)
value = MarketDataValue.model_validate_json(msg.value)
```

## CLI Tool: dc-avro

Generate Python classes from Avro schemas using [dataclasses-avroschema](https://github.com/marcosschroh/dataclasses-avroschema).

### Installation

```bash
pip install "dataclasses-avroschema[cli]"
```

### Commands

```bash
# Generate Pydantic model from schema
dc-avro generate-model --path schemas/kafka/<topic>/key.avsc --model-type pydantic

# Validate schemas
dc-avro lint schemas/**/*.avsc

# Compare schema versions (for evolution)
dc-avro schema-diff --source-path v1.avsc --target-path v2.avsc
```

### Model Types

| Type | Description |
|------|-------------|
| `dataclass` | Python dataclass with `AvroModel` (default) |
| `pydantic` | Pydantic `BaseModel` - **recommended for JSON** |
| `avrodantic` | Pydantic + Avro helpers - for future Avro binary |

## Local Development

```bash
# Install CLI
pip install "dataclasses-avroschema[cli]"

# Validate schemas
dc-avro lint schemas/kafka/**/*.avsc

# Generate a model (to stdout)
dc-avro generate-model --path schemas/kafka/common/key.avsc --model-type pydantic

# Save to file
dc-avro generate-model --path schemas/kafka/common/key.avsc --model-type pydantic > key.py
```

## Example Schema

### Key Schema (`schemas/kafka/common/key.avsc`)

```json
{
  "type": "record",
  "name": "CommonKey",
  "namespace": "cz.trading.model.kafka.common",
  "doc": "Standard Kafka message key with envelope metadata",
  "fields": [
    {
      "name": "message_id",
      "type": { "type": "string", "logicalType": "uuid" },
      "doc": "UUID v4: Unique identifier for this message"
    },
    {
      "name": "tracking_id",
      "type": "string",
      "doc": "Correlation ID that travels with the trade"
    },
    {
      "name": "timestamp_utc",
      "type": { "type": "long", "logicalType": "timestamp-millis" },
      "doc": "Message generation time in UTC as epoch millis"
    },
    {
      "name": "system_id",
      "type": "string",
      "doc": "Source system identifier"
    },
    {
      "name": "version",
      "type": "string",
      "default": "1.0",
      "doc": "Schema version string"
    }
  ]
}
```

## Future: Avro Binary Serialization

Currently using JSON for Kafka payloads. To migrate to Avro binary:

1. Change `--model-type pydantic` to `--model-type avrodantic`
2. Use `serialize()` / `deserialize()` methods instead of `model_dump_json()`

```python
# Future Avro binary usage
key = CommonKey(...)
binary = key.serialize()  # Avro binary
key = CommonKey.deserialize(binary)
```
