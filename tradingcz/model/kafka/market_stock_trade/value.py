from dataclasses_avroschema import types
import pydantic
import typing



class MarketStockTradeValue(pydantic.BaseModel):
    """
    Stock trade data received from Alpaca StockDataStream
    """
    symbol: str = pydantic.Field(description="Ticker symbol (e.g., AAPL, MSFT)")
    timestamp: types.DateTimeMicro = pydantic.Field(description="Trade timestamp in microseconds UTC (from Alpaca)")
    price: float = pydantic.Field(description="Trade execution price")
    size: float = pydantic.Field(description="Trade size (Alpaca returns float)")
    exchange: typing.Optional[str] = pydantic.Field(description="Exchange code where trade occurred (Alpaca exchange code)", default=None)
    trade_id: typing.Optional[int] = pydantic.Field(description="Unique trade ID from exchange", default=None)
    conditions: typing.List[str] = pydantic.Field(description="Trade condition codes from Alpaca (e.g., '@' for regular, 'T' for extended hours)", default_factory=list)
    tape: typing.Optional[str] = pydantic.Field(description="SIP tape identifier (A=NYSE, B=ARCA/regional, C=NASDAQ)", default=None)

    
    class Meta:
        namespace = "cz.trading.model.kafka.market_stock_trade"

