Example of use for events

##################################OCA BREAKOUT STRATEGY###########################

oto_short_leg_oca_breakout = {
    "id": str(uuid6.uuid7()),
    "symbol": "SPY",
    "side": "sell",
    "type": "limit",
    "limit_price": 648.00,
    "qty": 3,
    "time_in_force": "day",
    "order_class": "oto",
    "sl_stop_price": 648.01,
    # "sl_limit_price": 649.00, - kdyz toto je akomentovane, stop loss se aktivuje na cene 440, a posle se do trhu
}

oto_long_leg_oca_breakout = {
    "id": str(uuid6.uuid7()),
    "symbol": "SPY",
    "side": "buy",
    "type": "limit",
    "limit_price": 658.00,
    "qty": 3,
    "time_in_force": "day",
    "order_class": "oto",
    "sl_stop_price": 657.99,
    # "sl_limit_price": 657.00, - kdyz toto je akomentovane, stop loss se aktivuje na cene 440, a posle se do trhu
}
# raise APIError(error, http_error)
# alpaca.common.exceptions.APIError: {"base_price":"658","code":42210000,"message":"stop_loss.stop_price must be \u003c= base_price - 0.01"}

execution_request_oca_breakout = {
    "id": str(uuid6.uuid7()),
    "event_type": "execution_request",
    "strategy_type": "oca_breakout",
    "market_orders": [oto_short_leg_oca_breakout, oto_long_leg_oca_breakout],
}
