"""Where stock prices come from. The domain only knows the PriceProvider port."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .errors import InvalidPriceError


class PriceProvider(Protocol):
    """Port for "the last available price" of a symbol (DB, market feed, ...)."""

    def last_price(self, symbol: str) -> Decimal: ...


@dataclass(frozen=True)
class PriceSnapshot:
    """In-memory PriceProvider: a fixed set of prices, e.g. loaded once per request
    so that one rebalance sees a consistent set of prices."""

    prices: Mapping[str, Decimal]

    def last_price(self, symbol: str) -> Decimal:
        try:
            return self.prices[symbol]
        except KeyError:
            raise InvalidPriceError(f"No price for {symbol}") from None
