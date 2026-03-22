# OCA BREAKOUT STRATEGY EXAMPLE
import uuid6

# Short leg configuration
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
}

# Long leg configuration
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
}

# Execution request object
execution_request_oca_breakout = {
    "id": str(uuid6.uuid7()),
    "event_type": "execution_request",
    "strategy_type": "oca_breakout",
    "market_orders": [oto_short_leg_oca_breakout, oto_long_leg_oca_breakout],
}

"""
NOTE: API Validation Error Reference
alpaca.common.exceptions.APIError: {
    "base_price": "658",
    "code": 42210000,
    "message": "stop_loss.stop_price must be <= base_price - 0.01"
}
"""
