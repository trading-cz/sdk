"""Converters between DTOs and Kafka schemas.

These functions bridge the gap between:
- DTOs (used in REST APIs and internal processing)
- Kafka schemas (generated from Avro, used for messaging)

Example:
    from tradingcz.model import Quote
    from tradingcz.model.utils import quote_to_kafka
    
    quote = Quote(symbol="AAPL", timestamp=..., bid_price=150.25, ask_price=150.30)
    kafka_msg = quote_to_kafka(quote)
    producer.send("market.stock.quotes", value=kafka_msg.model_dump_json())
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ..dto import Quote, Trade

# Lazy import to avoid circular dependencies and allow usage without generated models
if TYPE_CHECKING:
    from tradingcz.model.kafka.market_stock_quote import MarketStockQuoteValue
    from tradingcz.model.kafka.market_stock_trade import MarketStockTradeValue


def quote_to_kafka(quote: Quote) -> "MarketStockQuoteValue":
    """Convert Quote DTO to Kafka schema.
    
    Args:
        quote: Quote DTO from provider
        
    Returns:
        MarketStockQuoteValue ready for Kafka serialization
    """
    # Import here to avoid hard dependency on generated models
    from tradingcz.model.kafka.market_stock_quote import MarketStockQuoteValue
    
    return MarketStockQuoteValue(
        symbol=quote.symbol,
        timestamp=quote.timestamp,  # DateTimeMicro accepts datetime
        bid_price=quote.bid_price,
        ask_price=quote.ask_price,
        bid_size=quote.bid_size or 0.0,
        ask_size=quote.ask_size or 0.0,
        bid_exchange=quote.bid_exchange,
        ask_exchange=quote.ask_exchange,
        conditions=quote.conditions or [],
        tape=None,  # Not available in DTO
    )


def trade_to_kafka(trade: Trade) -> "MarketStockTradeValue":
    """Convert Trade DTO to Kafka schema.
    
    Args:
        trade: Trade DTO from provider
        
    Returns:
        MarketStockTradeValue ready for Kafka serialization
    """
    from tradingcz.model.kafka.market_stock_trade import MarketStockTradeValue
    
    return MarketStockTradeValue(
        symbol=trade.symbol,
        timestamp=trade.timestamp,  # DateTimeMicro accepts datetime
        price=trade.price,
        size=trade.size,
        exchange=trade.exchange,
        trade_id=trade.trade_id,
        conditions=trade.conditions or [],
        tape=None,
    )


def kafka_to_quote(msg: "MarketStockQuoteValue") -> Quote:
    """Convert Kafka schema to Quote DTO.
    
    Args:
        msg: MarketStockQuoteValue from Kafka
        
    Returns:
        Quote DTO for internal processing
    """
    return Quote(
        symbol=msg.symbol,
        timestamp=datetime.fromtimestamp(msg.timestamp / 1_000_000, tz=timezone.utc),
        bid_price=msg.bid_price,
        ask_price=msg.ask_price,
        bid_size=msg.bid_size,
        ask_size=msg.ask_size,
        bid_exchange=msg.bid_exchange,
        ask_exchange=msg.ask_exchange,
        conditions=msg.conditions if msg.conditions else None,
    )


def kafka_to_trade(msg: "MarketStockTradeValue") -> Trade:
    """Convert Kafka schema to Trade DTO.
    
    Args:
        msg: MarketStockTradeValue from Kafka
        
    Returns:
        Trade DTO for internal processing
    """
    return Trade(
        symbol=msg.symbol,
        timestamp=datetime.fromtimestamp(msg.timestamp / 1_000_000, tz=timezone.utc),
        price=msg.price,
        size=msg.size,
        exchange=msg.exchange,
        trade_id=msg.trade_id,
        conditions=msg.conditions if msg.conditions else None,
    )
