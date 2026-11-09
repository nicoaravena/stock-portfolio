from dataclasses import dataclass, field
from decimal import Decimal

from .errors import InvalidPriceError
from .prices import PriceProvider


@dataclass(frozen=True)
class Stock:
    """A tradable stock, identified by its symbol.

    The price is not stored on the stock: `current_price()` asks the injected
    PriceProvider for the last available price, so the same Stock works with a
    database, a market-data feed or a fixed snapshot in tests.
    """

    symbol: str
    prices: PriceProvider = field(compare=False, repr=False)

    def current_price(self) -> Decimal:
        """Return the last available price; it must be positive to be tradable."""
        price = self.prices.last_price(self.symbol)
        if price <= 0:
            raise InvalidPriceError(
                f"{self.symbol} price must be positive, got {price}"
            )
        return price
