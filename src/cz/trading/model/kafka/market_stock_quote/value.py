from dataclasses_avroschema import types
import pydantic
import typing



class MarketStockQuoteValue(pydantic.BaseModel):
    """
    Stock quote data received from Alpaca StockDataStream
    """
    symbol: str = pydantic.Field(description="Ticker symbol (e.g., AAPL, MSFT)")
    timestamp: types.DateTimeMicro = pydantic.Field(description="Quote timestamp in microseconds UTC (from Alpaca)")
    bid_price: float = pydantic.Field(description="Best bid price")
    ask_price: float = pydantic.Field(description="Best ask price")
    bid_size: float = pydantic.Field(description="Bid size (Alpaca returns float)")
    ask_size: float = pydantic.Field(description="Ask size (Alpaca returns float)")
    bid_exchange: typing.Optional[str] = pydantic.Field(description="Exchange code for bid (Alpaca exchange code)", default=None)
    ask_exchange: typing.Optional[str] = pydantic.Field(description="Exchange code for ask (Alpaca exchange code)", default=None)
    conditions: typing.List[str] = pydantic.Field(description="Quote condition codes from Alpaca", default_factory=list)
    tape: typing.Optional[str] = pydantic.Field(description="SIP tape identifier (A=NYSE, B=ARCA/regional, C=NASDAQ)", default=None)

    
    class Meta:
        namespace = "cz.trading.model.kafka.market_stock_quote"

