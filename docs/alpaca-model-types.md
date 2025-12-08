Source: https://alpaca.markets/sdks/python/api_reference/data/models.html
Models
Bar
class alpaca.data.models.bars.Bar(symbol: str, raw_data: Dict[str, Any])
Represents one bar/candlestick of aggregated trade data over a specified interval.

symbol
The ticker identifier for the security whose data forms the bar.

Type:
str

timestamp
The opening timestamp of the bar.

Type:
datetime

open
The opening price of the interval.

Type:
float

high
The high price during the interval.

Type:
float

low
The low price during the interval.

Type:
float

close
The closing price of the interval.

Type:
float

volume
The volume traded over the interval.

Type:
float

trade_count
The number of trades that occurred.

Type:
Optional[float]

vwap
The volume weighted average price.

Type:
Optional[float]

exchange
The exchange the bar was formed on.

Type:
Optional[float]

BarSet
class alpaca.data.models.bars.BarSet(raw_data: Dict[str, Any])
A collection of Bars.

data
The collection of Bars keyed by symbol.

Type:
Dict[str, List[Bar]]

Quote
class alpaca.data.models.quotes.Quote(symbol: str, raw_data: Dict[str, Any])
Level 1 ask/bid pair quote data. Contains information about size and origin exchange.

symbol
The ticker identifier for the security whose data forms the quote.

Type:
str

timestamp
The time of submission of the quote.

Type:
datetime

bid_price
The bidding price of the quote.

Type:
float

bid_size
The size of the quote bid.

Type:
float

bid_exchange
The exchange the quote bid originates. Defaults to None.

Type:
Optional[Union[str, Exchange]]

ask_price
The asking price of the quote.

Type:
float

ask_size
The size of the quote ask.

Type:
float

ask_exchange
The exchange the quote ask originates. Defaults to None.

Type:
Optional[Union[str, Exchange]]

conditions
The quote conditions. Defaults to None.

Type:
Optional[Union[List[str], str]]

tape
The quote tape. Defaults to None.

Type:
Optional[str]

QuoteSet
class alpaca.data.models.quotes.QuoteSet(raw_data: Dict[str, Any])
A collection of Quotes.

data
The collection of Quotes keyed by symbol.

Type:
Dict[str, List[Quote]]

Trade
class alpaca.data.models.trades.Trade(symbol: str, raw_data: Dict[str, Any])
A transaction from the price and sales history of a security.

symbol
The ticker identifier for the security whose data forms the trade.

Type:
str

timestamp
The time of submission of the trade.

Type:
datetime

exchange
The exchange the trade occurred.

Type:
Optional[Exchange]

price
The price that the transaction occurred at.

Type:
float

size
The quantity traded

Type:
float

id
The trade ID

Type:
Optional[int]

conditions
The trade conditions. Defaults to None.

Type:
Optional[Union[List[str], str]]

tape
The trade tape. Defaults to None.

Type:
Optional[str]

TradeSet
class alpaca.data.models.trades.TradeSet(raw_data: Dict[str, Any])
A collection of Trade objects.

data
The collection of Trades keyed by symbol.

Type:
Dict[str, List[Trade]]]

Snapshot
class alpaca.data.models.snapshots.Snapshot(symbol: str, raw_data: Dict[str, Dict[str, Any]])
A Snapshot contains the latest trade, latest quote, minute bar daily bar and previous daily bar data for a given ticker symbol.

symbol
The identifier for the snapshot security.

Type:
str

latest_trade
The latest transaction on the price and sales tape

Type:
Optional[Trade]

latest_quote
Level 1 ask/bid pair quote data.

Type:
Optional[Quote]

minute_bar
The latest minute OHLC bar data

Type:
Optional[Bar]

daily_bar
The latest daily OHLC bar data

Type:
Optional[Bar]

previous_daily_bar
The 2nd to latest (2 trading days ago) daily OHLC bar data

Type:
Optional[Bar]

OptionsGreeks
class alpaca.data.models.snapshots.OptionsGreeks(raw_data: Dict[str, Any])
Options Greeks are a set of risk measures that are used in the options market to evaluate the risk and reward of an option.

delta
The rate of change of an option’s price relative to a change in the price of the underlying asset.

Type:
float

gamma
The rate of change in an option’s delta relative to a change in the price of the underlying asset.

Type:
float

rho
The rate of change in an option’s price relative to a change in the risk-free rate of interest.

Type:
float

theta
The rate of change in an option’s price relative to a change in time.

Type:
float

vega
The rate of change in an option’s price relative to a change in the volatility of the underlying asset.

Type:
float

OptionsSnapshot
class alpaca.data.models.snapshots.OptionsSnapshot(symbol: str, raw_data: Dict[str, Dict[str, Any]])
An options snapshot contains the latest trade, latest quote, greeks and implied volatility data for a given symbol.

symbol
The identifier for the snapshot security.

Type:
str

latest_trade
The latest transaction on the price and sales tape

Type:
Optional[Trade]

latest_quote
Level 1 ask/bid pair quote data.

Type:
Optional[Quote]

implied_volatility
The implied volatility of the option

Type:
Optional[float]

greeks
The option greeks data

Type:
Optional[OptionGreeks]

Orderbook
class alpaca.data.models.orderbooks.Orderbook(symbol: str, raw_data: Dict[str, Any])
Level 2 ask/bid pair orderbook data.

symbol
The ticker identifier for the security whose data forms the orderbook.

Type:
str

timestamp
The time of submission of the orderbook.

Type:
datetime

bids
The list of bid quotes for the orderbook

Type:
List[OrderbookQuote]

asks
The list of ask quotes for the orderbook

Type:
List[OrderbookQuote]

reset
if true, the orderbook message contains the whole server side orderbook.

Type:
bool

This indicates to the client that they should reset their orderbook.
Typically sent as the first message after subscription.
OrderbookQuote
class alpaca.data.models.orderbooks.OrderbookQuote(*, p: float, s: float)
A single bid or ask quote in the orderbook

ActiveStock
class alpaca.data.models.screener.ActiveStock(*, symbol: str, volume: float, trade_count: float)
Represent one asset that was a most active on the most actives endpoint.

symbol
Symbol of market moving asset.

Type:
str

volume
Cumulative volume for the current trading day.

Type:
float

trade_count
Cumulative trade count for the current trading day.

Type:
float

MostActives
class alpaca.data.models.screener.MostActives(*, most_actives: List[ActiveStock], last_updated: datetime)
Represent the response model for the MostActives endpoint. .. attribute:: most_actives

list of top N most active symbols.

type:
List[ActiveStock]

last_updated
Time when the MostActives were last computed. Formatted as a RFC 3339 formatted datetime with nanosecond precision.

Type:
datetime

Mover
class alpaca.data.models.screener.Mover(*, symbol: str, percent_change: float, change: float, price: float)
Represent one asset that was a top mover on the top market movers endpoint. .. attribute:: symbol

Symbol of market moving asset.

type:
str

percent_change
Percentage difference change for the day.

Type:
float

change
Difference in change for the day.

Type:
float

price
Current price of market moving asset.

Type:
float

Movers
class alpaca.data.models.screener.Movers(*, gainers: List[Mover], losers: List[Mover], market_type: MarketType, last_updated: datetime)
Represent the response model for the top market movers endpoint. .. attribute:: gainers

list of top N gainers.

type:
List[Mover]

losers
list of top N losers.

Type:
List[Mover]

market_type
Market type (stocks or crypto).

Type:
MarketType

last_updated
Time when the movers were last computed. Formatted as a RFC 3339 formatted datetime with nanosecond precision.

Type:
datetime

CorporateAction
alpaca.data.models.corporate_actions.CorporateAction
alias of Union[ForwardSplit, ReverseSplit, UnitSplit, StockDividend, CashDividend, SpinOff, CashMerger, StockMerger, StockAndCashMerger, Redemption, NameChange, WorthlessRemoval, RightsDistribution]

CorporateActionsSet
class alpaca.data.models.corporate_actions.CorporateActionsSet(raw_data: Dict[str, Any])
A collection of Corporate actions. ref. https://docs.alpaca.markets/reference/corporateactions-1

data
The collection of corporate actions.

Type:
Dict[str, List[CorporateAction]]