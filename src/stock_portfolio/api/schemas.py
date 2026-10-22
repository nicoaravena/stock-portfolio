from decimal import Decimal
from enum import Enum

from ninja import ModelSchema, Schema
from pydantic import Field, field_validator

from .models import Holding, Portfolio, Stock

HUNDRED = Decimal(value="100.0")


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class StockPriceIn(Schema):
    last_price: Decimal = Field(gt=0)


class StockIn(StockPriceIn):
    symbol: str = Field(min_length=1, max_length=16)

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.strip().upper()


class StockOut(ModelSchema):
    symbol: str
    last_price: Decimal

    class Meta:
        model = Stock
        fields = ["symbol", "last_price"]  # noqa: RUF012


class HoldingIn(Schema):
    """A stock to hold, its owned whole shares and its target allocation (%).
    A 0% allocation means the holding is sold fully on rebalance."""

    symbol: str = Field(min_length=1, max_length=16)
    quantity: int = Field(default=0, ge=0)
    allocation: int = Field(default=0, ge=0, le=100)

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.strip().upper()


class HoldingOut(ModelSchema):
    id: int
    stock: StockOut
    quantity: int
    allocation: int

    class Meta:
        model = Holding
        fields = ["id", "stock", "quantity", "allocation"]  # noqa: RUF012

    @property
    def market_value(self) -> Decimal:
        return self.stock.last_price * self.quantity


class Trade(Schema):
    holding_id: int
    symbol: str
    action: Action
    quantity: int = Field(gt=0)
    price: Decimal

    @property
    def amount(self) -> Decimal:
        return self.price * self.quantity


class RebalanceIn(Schema):
    cash: Decimal = Decimal(0)


class RebalancePlan(Schema):
    total_value: Decimal  # portfolio market value + fresh cash
    trades: list[Trade]  # sells first, then buys
    cash_leftover: Decimal  # unspent cash caused by whole-share rounding

    @property
    def sells(self) -> list[Trade]:
        return [t for t in self.trades if t.action is Action.SELL]

    @property
    def buys(self) -> list[Trade]:
        return [t for t in self.trades if t.action is Action.BUY]


class PortfolioIn(Schema):
    name: str = Field(min_length=1, max_length=100)
    holdings: list[HoldingIn]
    cash_leftover: Decimal = Field(default=Decimal(0), ge=0)

    @field_validator("holdings")
    @classmethod
    def _validate_allocation(cls, v: list[HoldingIn]) -> list[HoldingIn]:
        if len({h.symbol for h in v}) != len(v):
            raise ValueError("Duplicate symbols in holdings")
        if sum(h.allocation for h in v) != HUNDRED:
            raise ValueError("Allocation weights must sum to 100")
        return v


class PortfolioOut(ModelSchema):
    id: int
    name: str
    cash_leftover: Decimal
    holdings: list[HoldingOut]
    pending_plan: RebalancePlan | None

    class Meta:
        model = Portfolio
        fields = ["id", "name", "cash_leftover", "pending_plan"]  # noqa: RUF012

    @property
    def market_value(self) -> Decimal:
        return sum((h.market_value for h in self.holdings), Decimal(0))


class ErrorOut(Schema):
    detail: str
