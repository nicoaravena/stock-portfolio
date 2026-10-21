from collections.abc import Iterable
from decimal import Decimal

import pytest

from stock_portfolio._model import (
    Action,
    Holding,
    Portfolio,
    RebalancePlan,
    Stock,
    Trade,
)


def _init_portfolio(holdings: Iterable[Holding], allocation: list, cash_leftover="0") -> Portfolio:
    return Portfolio(
        holdings={h.symbol: h for h in holdings},
        allocation={h.symbol: allocation[idx] for idx, h in enumerate(holdings)},
        cash_leftover=cash_leftover,
    )


@pytest.mark.parametrize(
    "stock,expected_symbol,expected_value",
    [
        pytest.param(Stock(symbol="A", last_price="1.0"), "A", Decimal("1.0")),
        pytest.param(Stock(symbol="B", last_price=2), "B", Decimal("2.0")),
    ],
)
def test_stock(stock: Stock, expected_symbol: str, expected_value: Decimal):
    assert stock.symbol == expected_symbol
    assert stock.current_price == expected_value


@pytest.mark.parametrize(
    "stock,holding_quantity",
    [
        pytest.param(Stock(symbol="A", last_price="1.0"), 1),
        pytest.param(Stock(symbol="B", last_price=2), 2),
    ],
)
def test_holding(stock: Stock, holding_quantity: int):
    new_holding = Holding(stock=stock, quantity=holding_quantity)

    assert new_holding.stock == stock
    assert new_holding.symbol == stock.symbol
    assert new_holding.market_value == stock.current_price * holding_quantity


@pytest.mark.parametrize(
    "holdings,allocation",
    [
        pytest.param(
            [
                Holding(stock=Stock(symbol="A", last_price="1.0"), quantity=3),
                Holding(stock=Stock(symbol="B", last_price="2.5"), quantity=2),
            ],
            [60, 40],
        ),
    ],
)
def test_portfolio_init(holdings: list[Holding], allocation: list):
    portfolio = _init_portfolio(holdings, allocation)

    assert portfolio.market_value == sum(h.market_value for h in holdings)


@pytest.mark.parametrize(
    "holdings,allocation,rebalance_cash,expected_plan",
    [
        pytest.param(
            [
                Holding(stock=Stock(symbol="A", last_price="1.0"), quantity=3),
                Holding(stock=Stock(symbol="B", last_price="2.5"), quantity=2),
            ],
            [60, 40],
            Decimal("5.0"),
            RebalancePlan(
                total_value=Decimal("13.0"),
                trades=[
                    Trade(
                        symbol="A", action=Action.BUY, quantity=4, price=Decimal("1.0")
                    )
                ],
                cash_leftover=Decimal("1.0"),
            ),
        ),
    ],
)
def test_portfolio_rebalance(
    holdings: list[Holding],
    allocation: list,
    rebalance_cash: Decimal,
    expected_plan: RebalancePlan,
):
    portfolio = _init_portfolio(holdings, allocation)

    plan = portfolio.rebalance(rebalance_cash)
    assert plan.total_value == expected_plan.total_value
    assert len(plan.trades) == len(expected_plan.trades)
    assert plan.cash_leftover == expected_plan.cash_leftover


@pytest.mark.parametrize(
    "holdings,allocation,expected_portfolio",
    [
        pytest.param(
            [
                Holding(stock=Stock(symbol="A", last_price="1.0"), quantity=3),
                Holding(stock=Stock(symbol="B", last_price="2.5"), quantity=2),
            ],
            [60, 40],
            _init_portfolio(
                holdings=[Holding(stock=Stock(symbol='A', last_price=Decimal('1.0')), quantity=7),Holding(stock=Stock(symbol='B', last_price=Decimal('2.5')), quantity=2)],
                allocation=[60, 40],
                cash_leftover=Decimal('1.0')
            )
        ),
    ],
)
def test_portfolio_executed_trade_plan(
    holdings: list[Holding],
    allocation: list,
    expected_portfolio: Portfolio,
):
    rebalance_cash = Decimal("5.0")
    portfolio = _init_portfolio(holdings, allocation)

    plan = portfolio.rebalance(rebalance_cash)
    portfolio.execute_trade_plan(plan)
    assert portfolio.market_value == expected_portfolio.market_value
    assert portfolio.cash_leftover == expected_portfolio.cash_leftover
    for symbol in portfolio.holdings:
        assert portfolio.holdings[symbol].quantity == expected_portfolio.holdings[symbol].quantity
