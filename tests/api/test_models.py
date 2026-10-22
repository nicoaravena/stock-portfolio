from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from stock_portfolio.api.models import Holding, Portfolio, Stock

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [("META", "META"), ("meta", "META"), ("  MeTa  ", "META"), ("\tbrk.b\n", "BRK.B")],
)
def test_stock_save_normalizes_symbol(symbol: str, expected: str):
    Stock.objects.create(symbol=symbol, last_price=Decimal(1))
    assert Stock.objects.get().symbol == expected


@pytest.mark.parametrize("price", ["1", "0.000001", "98765.432109"])
def test_stock_price_round_trip(price: str):
    Stock.objects.create(symbol="A", last_price=Decimal(price))
    assert Stock.objects.get().last_price == Decimal(price)


def test_portfolio_defaults():
    portfolio = Portfolio.objects.create(name="p")
    portfolio.refresh_from_db()
    assert portfolio.cash_leftover == 0
    assert portfolio.pending_plan is None


@pytest.mark.parametrize(
    "plan",
    [
        None,
        {"total_value": "10", "trades": [], "cash_leftover": "0"},
    ],
)
def test_portfolio_pending_plan_round_trip(plan):
    Portfolio.objects.create(name="p", pending_plan=plan)
    assert Portfolio.objects.get().pending_plan == plan


def test_portfolio_name_unique():
    Portfolio.objects.create(name="p")
    with pytest.raises(IntegrityError):
        Portfolio.objects.create(name="p")


def test_holding_defaults():
    stock = Stock.objects.create(symbol="A", last_price=Decimal(1))
    portfolio = Portfolio.objects.create(name="p")
    holding = Holding.objects.create(portfolio=portfolio, stock=stock)
    holding.refresh_from_db()
    assert (holding.quantity, holding.allocation) == (0, 0)


def test_holding_unique_per_portfolio_and_stock():
    stock = Stock.objects.create(symbol="A", last_price=Decimal(1))
    p, q = Portfolio.objects.create(name="p"), Portfolio.objects.create(name="q")
    Holding.objects.create(portfolio=p, stock=stock)
    Holding.objects.create(portfolio=q, stock=stock)  # same stock, other portfolio
    with pytest.raises(IntegrityError):
        Holding.objects.create(portfolio=p, stock=stock)


@pytest.mark.parametrize("field", ["quantity", "allocation"])
def test_holding_rejects_negative_values(field: str):
    stock = Stock.objects.create(symbol="A", last_price=Decimal(1))
    portfolio = Portfolio.objects.create(name="p")
    with pytest.raises(IntegrityError):
        Holding.objects.create(portfolio=portfolio, stock=stock, **{field: -1})


def test_deleting_portfolio_cascades_to_holdings():
    stock = Stock.objects.create(symbol="A", last_price=Decimal(1))
    portfolio = Portfolio.objects.create(name="p")
    Holding.objects.create(portfolio=portfolio, stock=stock)
    portfolio.delete()
    assert not Holding.objects.exists()
    assert Stock.objects.filter(symbol="A").exists()


def test_deleting_held_stock_is_protected():
    stock = Stock.objects.create(symbol="A", last_price=Decimal(1))
    Holding.objects.create(portfolio=Portfolio.objects.create(name="p"), stock=stock)
    with pytest.raises(ProtectedError):
        stock.delete()
