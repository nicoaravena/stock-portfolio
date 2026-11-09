from decimal import Decimal

import pytest

from stock_portfolio.domain import InvalidPriceError, PriceSnapshot, Stock

SNAP = PriceSnapshot({"META": Decimal(510)})


def test_current_price_reads_provider():
    assert Stock("META", SNAP).current_price() == Decimal(510)


def test_current_price_reflects_provider_updates():
    """The price is read from the provider on every call, never stored."""
    prices = {"META": Decimal(1)}
    stock = Stock("META", PriceSnapshot(prices))
    prices["META"] = Decimal(2)
    assert stock.current_price() == Decimal(2)


@pytest.mark.parametrize("price", ["0", "-1"])
def test_current_price_rejects_non_positive(price: str):
    with pytest.raises(InvalidPriceError, match="META"):
        Stock("META", PriceSnapshot({"META": Decimal(price)})).current_price()


def test_snapshot_missing_symbol():
    with pytest.raises(InvalidPriceError, match="No price for AAPL"):
        Stock("AAPL", SNAP).current_price()


def test_stock_identity_is_symbol():
    assert Stock("META", SNAP) == Stock("META", PriceSnapshot({}))
    assert len({Stock("META", SNAP), Stock("META", PriceSnapshot({}))}) == 1
