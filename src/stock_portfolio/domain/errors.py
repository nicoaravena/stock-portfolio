"""Domain exceptions. The delivery layer maps them to user-facing errors."""


class PortfolioError(Exception):
    """Base class: the request breaks a portfolio rule."""


class InvalidPriceError(PortfolioError):
    """A stock has no usable price (missing, zero or negative)."""


class InvalidPortfolioError(PortfolioError):
    """A portfolio is built with negative share quantities or cash."""


class InvalidAllocationError(InvalidPortfolioError):
    """Target weights are out of range or do not sum to exactly 1."""


class InsufficientFundsError(PortfolioError):
    """More cash is withdrawn than the portfolio is worth."""


class OversellError(PortfolioError):
    """A trade would leave a negative number of shares."""


class NotFoundError(PortfolioError):
    """A referenced entity does not exist."""


class StockNotFoundError(NotFoundError):
    """No stock with the given symbol."""


class HoldingNotFoundError(NotFoundError):
    """No holding with the given id in the portfolio."""
