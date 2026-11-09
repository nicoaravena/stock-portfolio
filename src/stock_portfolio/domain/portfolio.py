from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import Enum
from types import MappingProxyType

from .errors import (
    InsufficientFundsError,
    InvalidAllocationError,
    InvalidPortfolioError,
)
from .stock import Stock


class Action(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Trade:
    """Buy or sell `quantity` whole shares of `symbol` at `price`."""

    symbol: str
    action: Action
    quantity: int
    price: Decimal


@dataclass(frozen=True)
class RebalancePlan:
    """The trades that move a portfolio to its target allocation."""

    total_value: Decimal  # market value + cash + cash added/removed
    trades: tuple[Trade, ...]  # sells first, then buys
    cash_leftover: Decimal  # unspent cash caused by whole-share rounding

    @property
    def sells(self) -> tuple[Trade, ...]:
        return tuple(t for t in self.trades if t.action is Action.SELL)

    @property
    def buys(self) -> tuple[Trade, ...]:
        return tuple(t for t in self.trades if t.action is Action.BUY)


@dataclass(frozen=True)
class Portfolio:
    """A set of stocks owned and the distribution the owner is aiming for.

    Two separate collections, as an investor thinks about them:
    - `holdings`: what is owned now, in whole shares per stock.
    - `allocation`: what the portfolio should look like, as target weights
      (fractions of the total value, e.g. META 0.4 / AAPL 0.6) summing to 1.

    A stock may appear in only one of them: held but not allocated means
    "get rid of it" (weight 0); allocated but not held means "start buying it".
    `cash` is money in the portfolio that is not invested (e.g. rounding
    leftovers from a previous rebalance).
    """

    holdings: Mapping[Stock, int]
    allocation: Mapping[Stock, Decimal]
    cash: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        # Frozen + read-only copies: the checks below hold for the object's lifetime.
        object.__setattr__(self, "holdings", MappingProxyType(dict(self.holdings)))
        object.__setattr__(self, "allocation", MappingProxyType(dict(self.allocation)))
        if any(quantity < 0 for quantity in self.holdings.values()):
            raise InvalidPortfolioError("Holding quantities must not be negative")
        if self.cash < 0:
            raise InvalidPortfolioError("Cash must not be negative")
        if any(not 0 <= weight <= 1 for weight in self.allocation.values()):
            raise InvalidAllocationError("Allocation weights must be between 0 and 1")
        # Exact Decimal comparison on purpose: 3 x 0.3333 is not a full portfolio.
        if sum(self.allocation.values(), Decimal(0)) != 1:
            raise InvalidAllocationError("Allocation weights must sum to 1")

    def market_value(self) -> Decimal:
        """Value of the shares held, at their current prices."""
        return self._value_at({stock: stock.current_price() for stock in self.holdings})

    def _value_at(self, prices: Mapping[Stock, Decimal]) -> Decimal:
        """Value of the shares held, at the given prices."""
        return sum(
            (prices[stock] * qty for stock, qty in self.holdings.items()), Decimal(0)
        )

    def rebalance(self, cash_delta: Decimal = Decimal(0)) -> RebalancePlan:
        """Return the trades that bring the portfolio to its target allocation.

        1. Pool everything: total = market value + cash + cash_delta, where a
           positive `cash_delta` adds fresh money and a negative one withdraws.
           Withdrawing more than the total is an error.
        2. For each stock, the target is `floor(total * weight / price)` whole
           shares. Rounding down guarantees the buys never cost more than the
           money available; what is left is reported as `cash_leftover` and is
           not reinvested.
        3. The difference between target and held shares is a BUY or a SELL.
        4. Sells come before buys: when executed, sells free the cash the buys
           need.

        Each price is read once, so the whole plan uses one consistent set of
        prices and every trade records the price it was planned with.
        """
        stocks = [
            *self.holdings,
            *(s for s in self.allocation if s not in self.holdings),
        ]
        prices = {stock: stock.current_price() for stock in stocks}

        # Value the holdings with the snapshot above, not market_value(): asking
        # the provider again could return a newer price, and the total would no
        # longer match the prices the trades are planned with.
        total = self._value_at(prices) + self.cash + cash_delta
        if total < 0:
            raise InsufficientFundsError(
                f"Cannot withdraw {-cash_delta}: the portfolio is worth {total - cash_delta}"
            )

        trades: list[Trade] = []
        invested = Decimal(0)
        for stock in stocks:
            price = prices[stock]
            target_value = total * self.allocation.get(stock, Decimal(0))
            target_qty = int(
                (target_value / price).to_integral_value(rounding=ROUND_FLOOR)
            )
            invested += price * target_qty

            delta = target_qty - self.holdings.get(stock, 0)
            if delta != 0:
                action = Action.BUY if delta > 0 else Action.SELL
                trades.append(Trade(stock.symbol, action, abs(delta), price))

        trades.sort(key=lambda t: t.action is Action.BUY)  # stable: sells first
        return RebalancePlan(
            total_value=total, trades=tuple(trades), cash_leftover=total - invested
        )
