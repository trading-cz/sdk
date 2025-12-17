import pydantic



class MarketStockTradeKey(pydantic.BaseModel):
    """
    Key for stock trade messages. Symbol for filtering, sequence for traceability. Use random partitioner to avoid hot symbol bottleneck.
    """
    symbol: str = pydantic.Field(description="Ticker symbol (e.g., AAPL, SPY) - used for consumer filtering")
    sequence: int = pydantic.Field(description="Monotonically increasing sequence number from ingestion service - used for gap detection and debugging")

    
    class Meta:
        namespace = "cz.trading.model.kafka.market_stock_trade"

