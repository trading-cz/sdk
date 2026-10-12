"""Unit tests for the account clients' request correlation."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from tradingcz.sdk.account.balance import Balance, BalanceClient, BalanceResponse
from tradingcz.sdk.account.positions import PositionClient, PositionList


@pytest.mark.asyncio
async def test_service_requests_use_their_payload_event_id_as_header() -> None:
    """Executor replies with the ServiceRequestEvent's payload event_id as header, so RR must send the same ID."""
    rr = MagicMock()
    rr.request = AsyncMock(
        side_effect=[
            BalanceResponse(event_id=uuid4(), balance=Balance(cash=1.0, buying_power=1.0)),
            PositionList(event_id=uuid4(), positions=[]),
        ]
    )

    await BalanceClient(rr).get_balance()
    await PositionClient(rr).get_positions()

    for call in rr.request.await_args_list:
        assert call.kwargs["event_id"] == str(call.args[0].event_id)
