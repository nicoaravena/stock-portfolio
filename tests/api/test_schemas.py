from decimal import Decimal

import pytest
from pydantic import ValidationError

from stock_portfolio.api.models import Holding, Portfolio, Stock
from stock_portfolio.api.schemas import (
    Action,
    HoldingIn,
    PortfolioIn,
    PortfolioOut,
    RebalancePlan,
    StockIn,
    StockPriceIn,
    Trade,
)


def _trade(action: Action, quantity: int = 1, price: str = "1") -> Trade:
    return Trade(
        holding_id=1,
        symbol="A",
        action=action,
        quantity=quantity,
        price=Decimal(price),
    )


@pytest.mark.parametrize("price", ["0.000001", "1", "1e6"])
def test_stock_price_in_valid(price: str):
    assert StockPriceIn(last_price=price).last_price == Decimal(price)


@pytest.mark.parametrize("price", ["0", "-1", "not-a-number"])
def test_stock_price_in_invalid(price: str):
    with pytest.raises(ValidationError):
        StockPriceIn(last_price=price)


@pytest.mark.parametrize("schema", [StockIn, HoldingIn])
@pytest.mark.parametrize(
    ("symbol", "expected"),
    [("meta", "META"), ("  Meta ", "META"), ("X" * 16, "X" * 16)],
)
def test_symbol_is_normalized(schema, symbol: str, expected: str):
    assert schema(symbol=symbol, last_price=1).symbol == expected


@pytest.mark.parametrize("schema", [StockIn, HoldingIn])
@pytest.mark.parametrize("symbol", ["", "X" * 17])
def test_symbol_length_is_validated(schema, symbol: str):
    with pytest.raises(ValidationError):
        schema(symbol=symbol, last_price=1)


def test_holding_in_defaults():
    holding = HoldingIn(symbol="A")
    assert (holding.quantity, holding.allocation) == (0, 0)


@pytest.mark.parametrize(
    "fields",
    [{"quantity": -1}, {"allocation": -1}, {"allocation": 101}],
)
def test_holding_in_invalid(fields: dict):
    with pytest.raises(ValidationError):
        HoldingIn(symbol="A", **fields)


@pytest.mark.parametrize(
    ("quantity", "price", "amount"),
    [(1, "1", "1"), (3, "2.5", "7.5"), (7, "0.333333", "2.333331")],
)
def test_trade_amount(quantity: int, price: str, amount: str):
    assert _trade(Action.BUY, quantity, price).amount == Decimal(amount)


@pytest.mark.parametrize("quantity", [0, -1])
def test_trade_quantity_must_be_positive(quantity: int):
    with pytest.raises(ValidationError):
        _trade(Action.BUY, quantity)


@pytest.mark.parametrize("action", ["BUY", "SELL"])
def test_trade_action_from_string(action: str):
    assert _trade(action).action is Action(action)


def test_trade_invalid_action():
    with pytest.raises(ValidationError):
        _trade("HOLD")


@pytest.mark.parametrize(
    ("actions", "n_sells", "n_buys"),
    [
        ([], 0, 0),
        ([Action.SELL], 1, 0),
        ([Action.BUY, Action.BUY], 0, 2),
        ([Action.SELL, Action.BUY, Action.SELL], 2, 1),
    ],
)
def test_rebalance_plan_sells_and_buys(actions, n_sells: int, n_buys: int):
    plan = RebalancePlan(
        total_value=Decimal(0),
        trades=[_trade(a) for a in actions],
        cash_leftover=Decimal(0),
    )
    assert len(plan.sells) == n_sells
    assert all(t.action is Action.SELL for t in plan.sells)
    assert len(plan.buys) == n_buys
    assert all(t.action is Action.BUY for t in plan.buys)


@pytest.mark.parametrize(
    "holdings",
    [
        [{"symbol": "A", "allocation": 100}],
        [{"symbol": "A", "allocation": 60}, {"symbol": "B", "allocation": 40}],
        [{"symbol": "A", "allocation": 100}, {"symbol": "B", "quantity": 5}],
    ],
)
def test_portfolio_in_valid(holdings: list[dict]):
    portfolio = PortfolioIn(name="p", holdings=holdings)
    assert len(portfolio.holdings) == len(holdings)
    assert portfolio.cash_leftover == 0


@pytest.mark.parametrize(
    ("holdings", "message"),
    [
        ([], "sum to 100"),
        ([{"symbol": "A", "allocation": 99}], "sum to 100"),
        (
            [{"symbol": "A", "allocation": 60}, {"symbol": "B", "allocation": 60}],
            "sum to 100",
        ),
        (
            [{"symbol": "A", "allocation": 50}, {"symbol": "a ", "allocation": 50}],
            "Duplicate symbols",
        ),
    ],
)
def test_portfolio_in_invalid_holdings(holdings: list[dict], message: str):
    with pytest.raises(ValidationError, match=message):
        PortfolioIn(name="p", holdings=holdings)


@pytest.mark.parametrize(
    "fields",
    [{"name": ""}, {"name": "x" * 101}, {"cash_leftover": "-0.01"}],
)
def test_portfolio_in_invalid_fields(fields: dict):
    payload = {"name": "p", "holdings": [{"symbol": "A", "allocation": 100}]}
    with pytest.raises(ValidationError):
        PortfolioIn(**(payload | fields))


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("positions", "market_value"),
    [
        ([], "0"),
        ([("A", "1", 0)], "0"),
        ([("A", "1", 3), ("B", "2.5", 2)], "8"),
        ([("A", "0.333333", 3), ("B", "100", 1)], "100.999999"),
    ],
)
def test_portfolio_out_market_value(positions, market_value: str):
    portfolio = Portfolio.objects.create(name="p")
    for symbol, price, quantity in positions:
        stock = Stock.objects.create(symbol=symbol, last_price=Decimal(price))
        Holding.objects.create(portfolio=portfolio, stock=stock, quantity=quantity)

    out = PortfolioOut.from_orm(portfolio)
    assert out.market_value == Decimal(market_value)
    for holding, (symbol, price, quantity) in zip(out.holdings, positions, strict=True):
        assert holding.stock.symbol == symbol
        assert holding.market_value == Decimal(price) * quantity
