from decimal import Decimal

import pytest
from django.http import Http404

from stock_portfolio.api import models, services
from stock_portfolio.api.schemas import (
    Action,
    PortfolioIn,
    PortfolioOut,
    RebalancePlan,
    Trade,
)

PRICES = {"A": "1", "B": "2.5", "C": "3"}


def _portfolio_out(
    positions: list[tuple[str, int, int]], cash_leftover: str = "0"
) -> PortfolioOut:
    """Build a PortfolioOut from (symbol, quantity, allocation) positions."""
    return PortfolioOut.model_validate(
        {
            "id": 1,
            "name": "p",
            "cash_leftover": cash_leftover,
            "pending_plan": None,
            "holdings": [
                {
                    "id": i,
                    "stock": {"symbol": symbol, "last_price": PRICES[symbol]},
                    "quantity": quantity,
                    "allocation": allocation,
                }
                for i, (symbol, quantity, allocation) in enumerate(positions, 1)
            ],
        }
    )


@pytest.mark.parametrize(
    ("positions", "portfolio_cash", "cash", "total", "trades", "leftover"),
    [
        pytest.param(
            [("A", 5, 50), ("B", 2, 50)], "0", "0", "10", [], "0", id="balanced"
        ),
        pytest.param(
            [("A", 3, 60), ("B", 2, 40)],
            "0",
            "5",
            "13",
            [("A", Action.BUY, 4)],
            "1",
            id="fresh-cash-rounds-down",
        ),
        pytest.param(
            [("A", 10, 100)],
            "0",
            "-4",
            "6",
            [("A", Action.SELL, 4)],
            "0",
            id="cash-removed",
        ),
        pytest.param(
            [("A", 3, 50), ("B", 2, 50)],
            "0",
            "-8",
            "0",
            [("A", Action.SELL, 3), ("B", Action.SELL, 2)],
            "0",
            id="all-cash-removed",
        ),
        pytest.param(
            [("A", 0, 100)],
            "3",
            "0",
            "3",
            [("A", Action.BUY, 3)],
            "0",
            id="existing-leftover-is-invested",
        ),
        pytest.param(
            [("C", 0, 100)],
            "0",
            "10",
            "10",
            [("C", Action.BUY, 3)],
            "1",
            id="whole-shares-only",
        ),
        pytest.param(
            [("A", 5, 100), ("B", 2, 0)],
            "0",
            "0",
            "10",
            [("B", Action.SELL, 2), ("A", Action.BUY, 5)],
            "0",
            id="zero-allocation-sold-fully",
        ),
        pytest.param(
            [("A", 0, 50), ("B", 4, 25), ("C", 4, 25)],
            "0",
            "0",
            "22",
            [("B", Action.SELL, 2), ("C", Action.SELL, 3), ("A", Action.BUY, 11)],
            "3",
            id="sells-before-buys",
        ),
    ],
)
def test_rebalance(positions, portfolio_cash, cash, total, trades, leftover):
    plan = services.rebalance(_portfolio_out(positions, portfolio_cash), Decimal(cash))

    assert plan.total_value == Decimal(total)
    assert [(t.symbol, t.action, t.quantity) for t in plan.trades] == trades
    assert plan.cash_leftover == Decimal(leftover)
    for trade in plan.trades:
        assert trade.price == Decimal(PRICES[trade.symbol])


def test_rebalance_default_cash_is_zero():
    portfolio = _portfolio_out([("A", 3, 60), ("B", 2, 40)])
    assert services.rebalance(portfolio) == services.rebalance(portfolio, Decimal(0))


@pytest.mark.parametrize(
    ("positions", "portfolio_cash", "cash"),
    [
        ([("A", 0, 100)], "0", "-0.01"),
        ([("A", 5, 100)], "0", "-5.000001"),
        ([("A", 5, 100)], "2", "-7.5"),
    ],
)
def test_rebalance_rejects_removing_too_much_cash(positions, portfolio_cash, cash):
    with pytest.raises(ValueError, match="cash must not be greater"):
        services.rebalance(_portfolio_out(positions, portfolio_cash), Decimal(cash))


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
    with pytest.raises(ValueError, match="must not be negative"):
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
    with pytest.raises(Http404):
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
    with pytest.raises(Http404):
        services.write_portfolio(portfolio, payload)

    portfolio.refresh_from_db()
    assert portfolio.name == "p"
    assert portfolio.pending_plan is not None
    assert _quantities(portfolio) == {"A": 3, "B": 2}
