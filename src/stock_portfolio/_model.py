"""Portfolio rebalancing proof of concept (plain input data only)."""

from decimal import ROUND_FLOOR, Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HUNDRED = Decimal(value="100.0")


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Stock(BaseModel):
    """A tradable stock with its last available price."""

    model_config = ConfigDict(validate_assignment=True, str_strip_whitespace=True)

    symbol: str = Field(min_length=1)
    last_price: Decimal = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.upper()

    @property
    def current_price(self) -> Decimal:
        """Getter: last available price."""
        return self.last_price

    def update_price(self, price: Decimal) -> None:
        """Setter: update the last available price (validated on assignment)."""
        self.last_price = price


class Holding(BaseModel):
    """A stock plus the number of whole shares currently owned (0 is allowed)."""

    stock: Stock
    quantity: int = Field(default=0, ge=0)

    @property
    def market_value(self) -> Decimal:
        return self.stock.current_price * self.quantity

    @property
    def symbol(self) -> str:
        return self.stock.symbol


class Trade(BaseModel):
    symbol: str
    action: Action
    quantity: int = Field(gt=0)
    price: Decimal

    @property
    def amount(self) -> Decimal:
        return self.price * self.quantity


class RebalancePlan(BaseModel):
    total_value: Decimal  # portfolio market value + fresh cash
    trades: list[Trade]  # sells first, then buys
    cash_leftover: Decimal  # unspent cash caused by whole-share rounding

    @property
    def sells(self) -> list[Trade]:
        return [t for t in self.trades if t.action is Action.SELL]

    @property
    def buys(self) -> list[Trade]:
        return [t for t in self.trades if t.action is Action.BUY]


class Portfolio(BaseModel):
    """Portfolio is where the a group of holdings are distributed by a
    specific allocation.

    holdings: A key-value dict, where the key is the symbol of the holding.
    allocation: A key-value dict, where the key is the symbol of a holding and the value is the % to distribute the quantity of the holding.
    cash_leftover: Is the amount of cash left from a rebalance."""

    holdings: dict[str, Holding]
    allocation: dict[str, Decimal]
    cash_leftover: Decimal

    @field_validator("allocation")
    @classmethod
    def _validate_allocation(cls, v: dict[str, Decimal]) -> dict[str, Decimal]:
        normalized = {k.strip().upper(): w for k, w in v.items()}
        if len(normalized) != len(v):
            raise ValueError("Duplicate symbols in allocation")
        if any(not (0 < w <= HUNDRED) for w in normalized.values()):
            raise ValueError("Each allocation weight must be in (0, 100]")
        if sum(normalized.values()) != HUNDRED:
            raise ValueError("Allocation weights must sum to 100")
        return normalized

    @model_validator(mode="after")
    def _validate_consistency(self) -> "Portfolio":
        mismatch = []
        for h in self.holdings:
            if h != self.holdings[h].symbol:
                mismatch.append((h, self.holdings[h]))
        if mismatch:
            raise ValueError(f"Holdings mismatch with some symbols: {mismatch}")
        missing = set(self.allocation) - self.holdings.keys()
        if missing:
            raise ValueError(
                f"Allocated symbols missing from holdings: {sorted(missing)} "
                "(add them with quantity=0 so their price is known)"
            )
        return self

    @property
    def market_value(self) -> Decimal:
        return sum((h.market_value for h in self.holdings.values()), Decimal(0))

    def rebalance(self, cash: Decimal = Decimal(0)) -> RebalancePlan:
        """Return the trades needed to reach the target allocation.

        - cash=0 (default): self-funded, sells pay for buys.
        - cash>0: fresh cash is added to the pool before computing targets.
        - Whole shares only: target quantities are rounded DOWN so buys never
          exceed available funds; the remainder is reported as `cash_leftover`.
        - Held symbols absent from the allocation have a 0% target (sold fully).
        """
        _cash = Decimal(cash) + self.cash_leftover
        if _cash < 0:
            raise ValueError("cash must be >= 0")

        total = self.market_value + _cash
        trades: list[Trade] = []
        invested = Decimal(0)

        for holding in self.holdings.values():
            symbol = holding.stock.symbol
            weight = self.allocation.get(symbol, Decimal(0))

            target_value = total * weight / HUNDRED
            target_qty = int(
                (target_value / holding.stock.current_price).to_integral_value(rounding=ROUND_FLOOR)
            )
            invested += holding.stock.current_price * target_qty

            delta = target_qty - holding.quantity
            if delta != 0:
                trades.append(
                    Trade(
                        symbol=symbol,
                        action=Action.BUY if delta > 0 else Action.SELL,
                        quantity=abs(delta),
                        price=holding.stock.current_price,
                    )
                )

        trades.sort(key=lambda t: t.action is Action.BUY)  # sells first
        return RebalancePlan(
            total_value=total, trades=trades, cash_leftover=total - invested
        )

    def execute_trade_plan(self, plan: RebalancePlan):
        for trade in plan.trades:
            if trade.action == Action.SELL:
                new_quantity = self.holdings[trade.symbol].quantity - trade.quantity
            elif trade.action == Action.BUY:
                new_quantity = self.holdings[trade.symbol].quantity + trade.quantity
            if new_quantity < 0:
                raise ValueError(
                    "Can't execute trade, final holding quantity must not be negative.",
                    self.holdings[trade.symbol],
                    trade,
                )
            self.holdings[trade.symbol].quantity = new_quantity

        self.cash_leftover = plan.cash_leftover
