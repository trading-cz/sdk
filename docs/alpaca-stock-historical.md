Historical Data
There are 3 historical data clients: StockHistoricalDataClient, CryptoHistoricalDataClient, and OptionHistoricalDataClient. The crypto data client does not require API keys to use.

Clients
Historical Data can be queried by using one of the two historical data clients: StockHistoricalDataClient, CryptoHistoricalDataClient, and OptionHistoricalDataClient. Historical data is available for Bar, Trade and Quote datatypes. For crypto, latest orderbook data is also available.

from alpaca.data import CryptoHistoricalDataClient, StockHistoricalDataClient, OptionHistoricalDataClient

# no keys required.
crypto_client = CryptoHistoricalDataClient()

# keys required
stock_client = StockHistoricalDataClient("api-key",  "secret-key")
option_client = OptionHistoricalDataClient("api-key",  "secret-key")
Retrieving Latest Quote Data
The latest quote data is available through the historical data clients. The method will return a dictionary of Trade objects that are keyed by the corresponding symbol. We will need to use the StockLatestQuoteRequest model to prepare the request parameters.

Attention

Models that are returned by both historical data clients are agnostic of the number of symbols that were passed in. This means that you must use the symbol as a key to access the data regardless of whether a single symbol or multiple symbols were queried. Below is an example of this in action.

Multi Symbol

Here is an example of submitting a data request for multiple symbols. The symbol_or_symbols parameter can accommodate both a single symbol or a list of symbols. Notice how the data for a single symbol is accessed after the query. We use the symbol we desire as a key to access the data.

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

# keys required for stock historical data client
client = StockHistoricalDataClient('api-key', 'secret-key')

# multi symbol request - single symbol is similar
multisymbol_request_params = StockLatestQuoteRequest(symbol_or_symbols=["SPY", "GLD", "TLT"])

latest_multisymbol_quotes = client.get_stock_latest_quote(multisymbol_request_params)

gld_latest_ask_price = latest_multisymbol_quotes["GLD"].ask_price
Single Symbol

This is a similar example but for a single symbol. The key thing to notice is how we still need to use the symbol as a key to access the data we desire. This might seem odd since we only queried a single symbol. However, this must be done since the data models are agnostic to the number of symbols.

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoLatestQuoteRequest

# no keys required
client = CryptoHistoricalDataClient()

# single symbol request
request_params = CryptoLatestQuoteRequest(symbol_or_symbols="ETH/USD")

latest_quote = client.get_crypto_latest_quote(request_params)

# must use symbol to access even though it is single symbol
latest_quote["ETH/USD"].ask_price
Retrieving Historical Bar Data
You can request bar (candlestick) data via the HistoricalDataClients. In this example, we query daily bar data for “BTC/USD” and “ETH/USD” since July 1st 2022 using CryptoHistoricalDataClient. You can convert the response to a multi-index pandas dataframe using the .df property.

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime

# no keys required for crypto data
client = CryptoHistoricalDataClient()

request_params = CryptoBarsRequest(
                        symbol_or_symbols=["BTC/USD", "ETH/USD"],
                        timeframe=TimeFrame.Day,
                        start=datetime(2022, 7, 1),
                        end=datetime(2022, 9, 1)
                 )

bars = client.get_crypto_bars(request_params)

# convert to dataframe
bars.df

# access bars as list - important to note that you must access by symbol key
# even for a single symbol request - models are agnostic to number of symbols
bars["BTC/USD"]


Historical Data
StockHistoricalDataClient
class alpaca.data.historical.stock.StockHistoricalDataClient(api_key: Optional[str] = None, secret_key: Optional[str] = None, oauth_token: Optional[str] = None, use_basic_auth: bool = False, raw_data: bool = False, url_override: Optional[str] = None, sandbox: bool = False)
The REST client for interacting with Alpaca Market Data API stock data endpoints.

Learn more on https://alpaca.markets/docs/market-data/

__init__(api_key: Optional[str] = None, secret_key: Optional[str] = None, oauth_token: Optional[str] = None, use_basic_auth: bool = False, raw_data: bool = False, url_override: Optional[str] = None, sandbox: bool = False) → None
Instantiates a Historical Data Client.

Parameters:
api_key (Optional[str], optional) – Alpaca API key. Defaults to None.

secret_key (Optional[str], optional) – Alpaca API secret key. Defaults to None.

oauth_token (Optional[str]) – The oauth token if authenticating via OAuth. Defaults to None.

use_basic_auth (bool, optional) – If true, API requests will use basic authorization headers. Set to true if using broker api sandbox credentials

raw_data (bool, optional) – If true, API responses will not be wrapped and raw responses will be returned from methods. Defaults to False. This has not been implemented yet.

url_override (Optional[str], optional) – If specified allows you to override the base url the client points to for proxy/testing.

sandbox (bool) – True if using sandbox mode. Defaults to False.

Get Stock Bars
StockHistoricalDataClient.get_stock_bars(request_params: StockBarsRequest) → Union[BarSet, Dict[str, Any]]
Returns bar data for an equity or list of equities over a given time period and timeframe.

Parameters:
request_params (GetStockBarsRequest) – The request object for retrieving stock bar data.

Returns:
The bar data either in raw or wrapped form

Return type:
Union[BarSet, RawData]

Get Stock Quotes
StockHistoricalDataClient.get_stock_quotes(request_params: StockQuotesRequest) → Union[QuoteSet, Dict[str, Any]]
Returns level 1 quote data over a given time period for a security or list of securities.

Parameters:
request_params (GetStockQuotesRequest) – The request object for retrieving stock quote data.

Returns:
The quote data either in raw or wrapped form

Return type:
Union[QuoteSet, RawData]

Get Stock Trades
StockHistoricalDataClient.get_stock_trades(request_params: StockTradesRequest) → Union[TradeSet, Dict[str, Any]]
Returns the price and sales history over a given time period for a security or list of securities.

Parameters:
request_params (GetStockTradesRequest) – The request object for retrieving stock trade data.

Returns:
The trade data either in raw or wrapped form

Return type:
Union[TradeSet, RawData]

Get Stock Latest Quote
StockHistoricalDataClient.get_stock_latest_quote(request_params: StockLatestQuoteRequest) → Union[Dict[str, Quote], Dict[str, Any]]
Retrieves the latest quote for an equity symbol or list of equity symbols.

Parameters:
request_params (StockLatestQuoteRequest) – The request object for retrieving the latest quote data.

Returns:
The latest quote in raw or wrapped format

Return type:
Union[Dict[str, Quote], RawData]

Get Stock Latest Trade
StockHistoricalDataClient.get_stock_latest_trade(request_params: StockLatestTradeRequest) → Union[Dict[str, Trade], Dict[str, Any]]
Retrieves the latest trade for an equity symbol or list of equities.

Parameters:
request_params (StockLatestTradeRequest) – The request object for retrieving the latest trade data.

Returns:
The latest trade in raw or wrapped format

Return type:
Union[Dict[str, Trade], RawData]

Get Stock Latest Bar
StockHistoricalDataClient.get_stock_latest_bar(request_params: StockLatestBarRequest) → Union[Dict[str, Bar], Dict[str, Any]]
Retrieves the latest minute bar for an equity symbol or list of equity symbols.

Parameters:
request_params (StockLatestBarRequest) – The request object for retrieving the latest bar data.

Returns:
The latest minute bar in raw or wrapped format

Return type:
Union[Dict[str, Bar], RawData]

Get Stock Snapshot
StockHistoricalDataClient.get_stock_snapshot(request_params: StockSnapshotRequest) → Union[Dict[str, Snapshot], Dict[str, Any]]
Returns snapshots of queried symbols. Snapshots contain latest trade, latest quote, latest minute bar, latest daily bar and previous daily bar data for the queried symbols.

Parameters:
request_params (StockSnapshotRequest) – The request object for retrieving snapshot data.

Returns:
The snapshot data either in raw or wrapped form

Return type:
Union[SnapshotSet, RawData]