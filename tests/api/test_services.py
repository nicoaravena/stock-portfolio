from decimal import Decimal

import pytest

from stock_portfolio.api import models, services
from stock_portfolio.api.schemas import (
    Action,
    PortfolioIn,
    RebalancePlan,
    Trade,
)
from stock_portfolio.domain import (
    HoldingNotFoundError,
    OversellError,
    StockNotFoundError,
)

# The rebalance algorithm itself is tested in tests/domain/test_portfolio.py;
# these tests cover the ORM <-> domain mapping and plan execution.

PRICES = {"A": "1", "B": "2.5", "C": "3"}


@pytest.fixture
def portfolio(db) -> models.Portfolio:
    portfolio = models.Portfolio.objects.create(
        name="p", pending_plan={"total_value": "0", "trades": [], "cash_leftover": "0"}
    )
    for symbol, quantity in (("A", 3), ("B", 2)):
        stock = models.Stock.objects.create(symbol=symbol, last_price=PRICES[symbol])
        models.Holding.objects.create(
            portfolio=portfolio, stock=stock, quantity=quantity, allocation=50
        )
    return portfolio


def _plan(portfolio: models.Portfolio, trades, leftover: str = "0") -> RebalancePlan:
    holdings = {h.stock.symbol: h for h in portfolio.holdings.select_related("stock")}
    return RebalancePlan(
        total_value=Decimal(0),
        trades=[
            Trade(
                holding_id=holdings[symbol].id,
                symbol=symbol,
                action=action,
                quantity=quantity,
                price=holdings[symbol].stock.last_price,
            )
            for symbol, action, quantity in trades
        ],
        cash_leftover=Decimal(leftover),
    )


def _quantities(portfolio: models.Portfolio) -> dict[str, int]:
    return {h.stock.symbol: h.quantity for h in portfolio.holdings.all()}


def test_to_domain(portfolio):
    domain = services.to_domain(portfolio)

    assert {s.symbol: q for s, q in domain.holdings.items()} == {"A": 3, "B": 2}
    assert {s.symbol: w for s, w in domain.allocation.items()} == {
        "A": Decimal("0.5"),
        "B": Decimal("0.5"),
    }
    assert domain.cash == 0
    stock_a = next(s for s in domain.holdings if s.symbol == "A")
    assert stock_a.current_price() == Decimal(1)


def test_rebalance_maps_holding_ids(portfolio):
    plan = services.rebalance(portfolio, Decimal(5))

    ids = {h.stock.symbol: h.id for h in portfolio.holdings.select_related("stock")}
    assert isinstance(plan, RebalancePlan)
    assert plan.trades
    assert all(trade.holding_id == ids[trade.symbol] for trade in plan.trades)


@pytest.mark.parametrize(
    ("trades", "leftover", "expected"),
    [
        ([], "0", {"A": 3, "B": 2}),
        ([("A", Action.BUY, 4)], "1", {"A": 7, "B": 2}),
        ([("B", Action.SELL, 1)], "2.5", {"A": 3, "B": 1}),
        ([("A", Action.SELL, 3), ("B", Action.BUY, 1)], "0.5", {"A": 0, "B": 3}),
        ([("A", Action.BUY, 1), ("A", Action.BUY, 2)], "0", {"A": 6, "B": 2}),
    ],
)
def test_execute_trade_plan(portfolio, trades, leftover, expected):
    services.execute_trade_plan(portfolio, _plan(portfolio, trades, leftover))

    portfolio.refresh_from_db()
    assert _quantities(portfolio) == expected
    assert portfolio.cash_leftover == Decimal(leftover)
    assert portfolio.pending_plan is None


@pytest.mark.parametrize(
    "trades",
    [
        [("A", Action.SELL, 4)],
        [("A", Action.BUY, 1), ("B", Action.SELL, 3)],  # earlier buy is rolled back
    ],
)
def test_execute_trade_plan_rejects_oversell(portfolio, trades):
    plan = _plan(portfolio, trades, "9")
    with pytest.raises(OversellError, match="must not be negative"):
        services.execute_trade_plan(portfolio, plan)

    portfolio.refresh_from_db()
    assert _quantities(portfolio) == {"A": 3, "B": 2}
    assert portfolio.cash_leftover == 0
    assert portfolio.pending_plan is not None


@pytest.mark.parametrize("foreign", [True, False])
def test_execute_trade_plan_unknown_holding(portfolio, foreign: bool):
    if foreign:
        other = models.Portfolio.objects.create(name="other")
        holding_id = models.Holding.objects.create(
            portfolio=other, stock_id="A", quantity=10
        ).id
    else:
        holding_id = 999
    plan = RebalancePlan(
        total_value=Decimal(0),
        trades=[
            Trade(
                holding_id=holding_id,
                symbol="A",
                action=Action.SELL,
                quantity=1,
                price=Decimal(1),
            )
        ],
        cash_leftover=Decimal(0),
    )
    with pytest.raises(HoldingNotFoundError):
        services.execute_trade_plan(portfolio, plan)


@pytest.mark.parametrize(
    ("holdings", "cash_leftover"),
    [
        ([{"symbol": "A", "allocation": 100}], "0"),
        ([{"symbol": "a", "quantity": 4, "allocation": 100}], "1.5"),
        (
            [
                {"symbol": "B", "quantity": 1, "allocation": 30},
                {"symbol": "C", "quantity": 2, "allocation": 70},
            ],
            "0",
        ),
    ],
)
def test_write_portfolio_replaces_everything(portfolio, holdings, cash_leftover):
    models.Stock.objects.create(symbol="C", last_price=PRICES["C"])
    payload = PortfolioIn(name="q", holdings=holdings, cash_leftover=cash_leftover)

    services.write_portfolio(portfolio, payload)

    portfolio.refresh_from_db()
    assert portfolio.name == "q"
    assert portfolio.cash_leftover == Decimal(cash_leftover)
    assert portfolio.pending_plan is None
    assert {
        h.stock.symbol: (h.quantity, h.allocation) for h in portfolio.holdings.all()
    } == {h.symbol: (h.quantity, h.allocation) for h in payload.holdings}


@pytest.mark.django_db
def test_write_portfolio_creates_new():
    models.Stock.objects.create(symbol="A", last_price=PRICES["A"])
    payload = PortfolioIn(
        name="new", holdings=[{"symbol": "A", "quantity": 2, "allocation": 100}]
    )

    services.write_portfolio(models.Portfolio(), payload)

    portfolio = models.Portfolio.objects.get(name="new")
    assert _quantities(portfolio) == {"A": 2}


@pytest.mark.parametrize(
    "holdings",
    [
        [{"symbol": "Z", "allocation": 100}],
        [{"symbol": "A", "allocation": 50}, {"symbol": "Z", "allocation": 50}],
    ],
)
def test_write_portfolio_unknown_stock_rolls_back(portfolio, holdings):
    payload = PortfolioIn(name="q", holdings=holdings)
    with pytest.raises(StockNotFoundError, match="Z"):
        services.write_portfolio(portfolio, payload)

    portfolio.refresh_from_db()
    assert portfolio.name == "p"
    assert portfolio.pending_plan is not None
    assert _quantities(portfolio) == {"A": 3, "B": 2}
