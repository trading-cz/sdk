Requests
BaseStockLatestDataRequest
class alpaca.data.requests.BaseStockLatestDataRequest(*, symbol_or_symbols: Union[str, List[str]], feed: Optional[DataFeed] = None, currency: Optional[SupportedCurrencies] = None)
A base request object for retrieving the latest data for stocks. You most likely should not use this directly and instead use the asset class specific request objects.

symbol_or_symbols
The ticker identifier or list of ticker identifiers.

Type:
Union[str, List[str]]

feed
The stock data feed to retrieve from.

Type:
Optional[DataFeed]

currency
The currency the data should be returned in. Default to USD.

Type:
Optional[SupportedCurrencies]

StockBarsRequest
class alpaca.data.requests.StockBarsRequest(*, symbol_or_symbols: Union[str, List[str]], start: Optional[datetime] = None, end: Optional[datetime] = None, limit: Optional[int] = None, currency: Optional[SupportedCurrencies] = None, sort: Optional[Sort] = None, timeframe: TimeFrame, adjustment: Optional[Adjustment] = None, feed: Optional[DataFeed] = None, asof: Optional[str] = None)
The request model for retrieving bar data for equities.

See BaseBarsRequest for more information on available parameters.

symbol_or_symbols
The ticker identifier or list of ticker identifiers.

Type:
Union[str, List[str]]

timeframe
The period over which the bars should be aggregated. (i.e. 5 Min bars, 1 Day bars)

Type:
TimeFrame

start
The beginning of the time interval for desired data. Timezone naive inputs assumed to be in UTC.

Type:
Optional[datetime]

end
The end of the time interval for desired data. Defaults to now. Timezone naive inputs assumed to be in UTC.

Type:
Optional[datetime]

limit
Upper limit of number of data points to return. Defaults to None.

Type:
Optional[int]

adjustment
The type of corporate action data normalization.

Type:
Optional[Adjustment]

feed
The stock data feed to retrieve from.

Type:
Optional[DataFeed]

sort
The chronological order of response based on the timestamp. Defaults to ASC.

Type:
Optional[Sort]

asof
The asof date of the queried stock symbol(s) in YYYY-MM-DD format.

Type:
Optional[str]

currency
The currency of all prices in ISO 4217 format. Default is USD.

Type:
Optional[SupportedCurrencies]

StockQuotesRequest
class alpaca.data.requests.StockQuotesRequest(*, symbol_or_symbols: Union[str, List[str]], start: Optional[datetime] = None, end: Optional[datetime] = None, limit: Optional[int] = None, currency: Optional[SupportedCurrencies] = None, sort: Optional[Sort] = None, feed: Optional[DataFeed] = None, asof: Optional[str] = None)
This request class is used to submit a request for stock quote data.

See BaseTimeseriesDataRequest for more information on available parameters.

symbol_or_symbols
The ticker identifier or list of ticker identifiers.

Type:
Union[str, List[str]]

start
The beginning of the time interval for desired data. Timezone naive inputs assumed to be in UTC.

Type:
Optional[datetime]

end
The end of the time interval for desired data. Defaults to now. Timezone naive inputs assumed to be in UTC.

Type:
Optional[datetime]

limit
Upper limit of number of data points to return. Defaults to None.

Type:
Optional[int]

feed
The stock data feed to retrieve from.

Type:
Optional[DataFeed]

sort
The chronological order of response based on the timestamp. Defaults to ASC.

Type:
Optional[Sort]

asof
The asof date of the queried stock symbol(s) in YYYY-MM-DD format.

Type:
Optional[str]

currency
The currency of all prices in ISO 4217 format. Default is USD.

Type:
Optional[SupportedCurrencies]

StockTradesRequest
class alpaca.data.requests.StockTradesRequest(*, symbol_or_symbols: Union[str, List[str]], start: Optional[datetime] = None, end: Optional[datetime] = None, limit: Optional[int] = None, currency: Optional[SupportedCurrencies] = None, sort: Optional[Sort] = None, feed: Optional[DataFeed] = None, asof: Optional[str] = None)
This request class is used to submit a request for stock trade data.

See BaseTimeseriesDataRequest for more information on available parameters.

symbol_or_symbols
The ticker identifier or list of ticker identifiers.

Type:
Union[str, List[str]]

start
The beginning of the time interval for desired data. Timezone naive inputs assumed to be in UTC.

Type:
Optional[datetime]

end
The end of the time interval for desired data. Defaults to now. Timezone naive inputs assumed to be in UTC.

Type:
Optional[datetime]

limit
Upper limit of number of data points to return. Defaults to None.

Type:
Optional[int]

feed
The stock data feed to retrieve from.

Type:
Optional[DataFeed]

sort
The chronological order of response based on the timestamp. Defaults to ASC.

Type:
Optional[Sort]

asof
The asof date of the queried stock symbol(s) in YYYY-MM-DD format.

Type:
Optional[str]

currency
The currency of all prices in ISO 4217 format. Default is USD.

Type:
Optional[SupportedCurrencies]

StockLatestQuoteRequest
class alpaca.data.requests.StockLatestQuoteRequest(*, symbol_or_symbols: Union[str, List[str]], feed: Optional[DataFeed] = None, currency: Optional[SupportedCurrencies] = None)
This request class is used to submit a request for the latest stock quote data.

See BaseStockLatestDataRequest for more information on available parameters.

symbol_or_symbols
The ticker identifier or list of ticker identifiers.

Type:
Union[str, List[str]]

feed
The stock data feed to retrieve from.

Type:
Optional[DataFeed]

currency
The currency the data should be returned in. Default to USD.

Type:
Optional[SupportedCurrencies]

StockLatestTradeRequest
class alpaca.data.requests.StockLatestTradeRequest(*, symbol_or_symbols: Union[str, List[str]], feed: Optional[DataFeed] = None, currency: Optional[SupportedCurrencies] = None)
This request class is used to submit a request for the latest stock trade data.

See BaseStockLatestDataRequest for more information on available parameters.

symbol_or_symbols
The ticker identifier or list of ticker identifiers.

Type:
Union[str, List[str]]

feed
The stock data feed to retrieve from.

Type:
Optional[DataFeed]

currency
The currency the data should be returned in. Default to USD.

Type:
Optional[SupportedCurrencies]

StockSnapshotRequest
class alpaca.data.requests.StockSnapshotRequest(*, symbol_or_symbols: Union[str, List[str]], feed: Optional[DataFeed] = None, currency: Optional[SupportedCurrencies] = None)
This request class is used to submit a request for snapshot data for stocks.

symbol_or_symbols
The ticker identifier or list of ticker identifiers.

Type:
Union[str, List[str]]

feed
The stock data feed to retrieve from.

Type:
Optional[DataFeed]

currency
The currency the data should be returned in. Default to USD.

Type:
Optional[SupportedCurrencies]

MostActivesRequest
class alpaca.data.requests.MostActivesRequest(*, top: int = 10, by: MostActivesBy = 'volume')
This request class is used to submit a request for most actives screener endpoint.

by
The metric used for ranking the most active stocks.

Type:
MostActivesBy

top
Number of top most active stocks to fetch per day.

Type:
int

MarketMoversRequest
class alpaca.data.requests.MarketMoversRequest(*, top: int = 10, market_type: MarketType = MarketType.STOCKS)
This request class is used to submit a request for most actives screener endpoint.

market_type
Screen specific market (stocks or crypto).

Type:
MarketType

top
Number of top most active stocks to fetch per day.

Type:
int