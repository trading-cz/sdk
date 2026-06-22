# market_data — Data Clients

Historical and streaming market data via request/reply over Kafka.

## Architecture

```text
StockDataClient / StockStreamClient / OptionsHistoricDataClient / CorporateActionsClient
            │
     BaseDataClient          ← shared transport logic
       │        │
  RequestReply  KafkaTransport
```

## StockDataClient (historic)

```python
from tradingcz.sdk.market_data import StockDataClient

# Created via TradingApp (recommended):
async with TradingApp(service_id="my-strategy") as app:
    # ── Historical ───────────────────────────────────────────────
    bars = await app.stock.bars(["AAPL", "MSFT"], days=30, timeframe="1Hour")
    quotes = await app.stock.latest_quotes(["AAPL"])
    trades = await app.stock.latest_trades(["AAPL"])
    latest = await app.stock.latest_bars(["AAPL"])
```

## StockStreamClient (streaming)

```python
from tradingcz.sdk.market_data import StockStreamClient

async with TradingApp(service_id="my-strategy") as app:
    # ── Streaming (context manager = guaranteed unsubscribe) ─────
    async with app.stock_stream.stream_quotes(["AAPL"]) as stream:
        async for quote in stream:
            if quote.bid_price > threshold:
                break

    async with app.stock_stream.stream_bars(["AAPL"], timeframe=Timeframe.H4) as stream:
        async for bar in stream:
            ...
```

## OptionsHistoricDataClient

```python
async with TradingApp(service_id="my-strategy") as app:
    snapshots = await app.options.snapshots(["AAPL250620C00150000"])
```

## CorporateActionsClient

```python
async with TradingApp(service_id="my-strategy") as app:
    dividends = await app.corporate_actions.dividends(["AAPL"], days=365)
    splits = await app.corporate_actions.splits(["AAPL"], days=365)
```

## TimeKeeper — market clock

```python
from tradingcz.sdk.market_data import TimeKeeper

clock = TimeKeeper(trading_client)
await clock.start_timekeeping()

# Emits pre-close warning events before market close
# Used by strategies to wind down positions
```
