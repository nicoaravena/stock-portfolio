from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from stock_portfolio.domain import (
    Action,
    InsufficientFundsError,
    InvalidAllocationError,
    InvalidPortfolioError,
    InvalidPriceError,
    Portfolio,
    PriceSnapshot,
    Stock,
)

BUY, SELL = Action.BUY, Action.SELL
PRICES = PriceSnapshot(
    {"A": Decimal(1), "B": Decimal("2.5"), "C": Decimal(3), "Z": Decimal(0)}
)


def _portfolio(
    holdings: dict[str, int], weights: dict[str, str], cash: str = "0"
) -> Portfolio:
    """Build a Portfolio from {symbol: shares} and {symbol: target weight}."""
    return Portfolio(
        holdings={Stock(s, PRICES): q for s, q in holdings.items()},
        allocation={Stock(s, PRICES): Decimal(w) for s, w in weights.items()},
        cash=Decimal(cash),
    )


@pytest.mark.parametrize(
    ("holdings", "weights", "cash", "cash_delta", "total", "trades", "leftover"),
    [
        pytest.param(
            {"A": 5, "B": 2}, {"A": "0.5", "B": "0.5"}, "0", "0", "10", [], "0",
            id="balanced",
        ),
        pytest.param(
            {"A": 3, "B": 2}, {"A": "0.6", "B": "0.4"}, "0", "5", "13",
            [("A", BUY, 4)], "1",
            id="fresh-cash-rounds-down",
        ),
        pytest.param(
            {"A": 10}, {"A": "1"}, "0", "-4", "6", [("A", SELL, 4)], "0",
            id="cash-removed",
        ),
        pytest.param(
            {"A": 3, "B": 2}, {"A": "0.5", "B": "0.5"}, "0", "-8", "0",
            [("A", SELL, 3), ("B", SELL, 2)], "0",
            id="all-cash-removed",
        ),
        pytest.param(
            {"A": 0}, {"A": "1"}, "3", "0", "3", [("A", BUY, 3)], "0",
            id="existing-leftover-is-invested",
        ),
        pytest.param(
            {"C": 0}, {"C": "1"}, "0", "10", "10", [("C", BUY, 3)], "1",
            id="whole-shares-only",
        ),
        pytest.param(
            {"A": 5, "B": 2}, {"A": "1", "B": "0"}, "0", "0", "10",
            [("B", SELL, 2), ("A", BUY, 5)], "0",
            id="zero-allocation-sold-fully",
        ),
        pytest.param(
            {"A": 0, "B": 4, "C": 4}, {"A": "0.5", "B": "0.25", "C": "0.25"},
            "0", "0", "22",
            [("B", SELL, 2), ("C", SELL, 3), ("A", BUY, 11)], "3",
            id="sells-before-buys",
        ),
        pytest.param(
            {"A": 5, "B": 2}, {"A": "1"}, "0", "0", "10",
            [("B", SELL, 2), ("A", BUY, 5)], "0",
            id="held-not-allocated",
        ),
        pytest.param(
            {}, {"A": "0.5", "C": "0.5"}, "10", "0", "10",
            [("A", BUY, 5), ("C", BUY, 1)], "2",
            id="allocated-not-held",
        ),
    ],
)  # fmt: skip
def test_rebalance(holdings, weights, cash, cash_delta, total, trades, leftover):
    plan = _portfolio(holdings, weights, cash).rebalance(Decimal(cash_delta))

    assert plan.total_value == Decimal(total)
    assert [(t.symbol, t.action, t.quantity) for t in plan.trades] == trades
    assert plan.cash_leftover == Decimal(leftover)
    for trade in plan.trades:
        assert trade.price == PRICES.last_price(trade.symbol)


def test_rebalance_worked_example():
    """40% META / 60% AAPL, adding 1000 cash (see README)."""
    prices = PriceSnapshot({"META": Decimal(510), "AAPL": Decimal(200)})
    meta, aapl = Stock("META", prices), Stock("AAPL", prices)
    portfolio = Portfolio(
        holdings={meta: 2, aapl: 0},
        allocation={meta: Decimal("0.4"), aapl: Decimal("0.6")},
    )

    assert portfolio.market_value() == 1020
    plan = portfolio.rebalance(Decimal(1000))

    assert plan.total_value == 2020
    assert [(t.symbol, t.action, t.quantity) for t in plan.trades] == [
        ("META", SELL, 1),
        ("AAPL", BUY, 6),
    ]
    assert plan.cash_leftover == 310


def test_rebalance_default_cash_delta_is_zero():
    portfolio = _portfolio({"A": 3, "B": 2}, {"A": "0.6", "B": "0.4"})
    assert portfolio.rebalance() == portfolio.rebalance(Decimal(0))


@pytest.mark.parametrize(
    ("holdings", "cash", "cash_delta"),
    [
        ({"A": 0}, "0", "-0.01"),
        ({"A": 5}, "0", "-5.000001"),
        ({"A": 5}, "2", "-7.5"),
    ],
)
def test_rebalance_rejects_removing_too_much_cash(holdings, cash, cash_delta):
    portfolio = _portfolio(holdings, {"A": "1"}, cash)
    with pytest.raises(InsufficientFundsError, match="cash must not be greater"):
        portfolio.rebalance(Decimal(cash_delta))


def test_rebalance_zero_price():
    with pytest.raises(InvalidPriceError, match="Z"):
        _portfolio({"Z": 1}, {"Z": "1"}).rebalance()


@pytest.mark.parametrize(
    "weights",
    [{"A": "0.5"}, {"A": "0.3333", "B": "0.3333", "C": "0.3333"}, {}],
)
def test_portfolio_rejects_weights_not_summing_to_one(weights):
    with pytest.raises(InvalidAllocationError, match="must sum to 1"):
        _portfolio({}, weights)


def test_portfolio_rejects_weight_out_of_range():
    with pytest.raises(InvalidAllocationError):
        _portfolio({}, {"A": "1.5", "B": "-0.5"})


@pytest.mark.parametrize(("holdings", "cash"), [({"A": -1}, "0"), ({"A": 1}, "-1")])
def test_portfolio_rejects_negative_quantity_or_cash(holdings, cash):
    with pytest.raises(InvalidPortfolioError):
        _portfolio(holdings, {"A": "1"}, cash)


def test_plan_sells_and_buys():
    plan = _portfolio(
        {"A": 0, "B": 4, "C": 4}, {"A": "0.5", "B": "0.25", "C": "0.25"}
    ).rebalance()

    assert [t.symbol for t in plan.sells] == ["B", "C"]
    assert [t.symbol for t in plan.buys] == ["A"]
    assert plan.sells + plan.buys == plan.trades


def test_portfolio_cannot_be_changed_after_validation():
    """Validation runs once, at construction, so the portfolio must stay as built."""
    weights = {"A": "0.5", "B": "0.5"}
    allocation = {Stock(s, PRICES): Decimal(w) for s, w in weights.items()}
    portfolio = Portfolio(holdings={}, allocation=allocation)

    with pytest.raises(FrozenInstanceError):
        portfolio.allocation = {Stock("A", PRICES): Decimal("0.5")}  # ty: ignore[invalid-assignment]
    allocation.pop(Stock("B", PRICES))  # the caller's dict is not shared

    assert sum(portfolio.allocation.values()) == 1
