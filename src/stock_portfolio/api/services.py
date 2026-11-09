"""Application services: map ORM rows to the domain and persist the results.

The rebalance rules live in `stock_portfolio.domain.Portfolio.rebalance`; this
module only translates between the database / API shapes and the domain.
"""

from decimal import Decimal

from django.db import transaction

from stock_portfolio import domain
from stock_portfolio.api import models
from stock_portfolio.api.schemas import HUNDRED, PortfolioIn, RebalancePlan, Trade


def _holdings(portfolio: models.Portfolio) -> list[models.Holding]:
    """All holdings with their stock, in one query, oldest first."""
    return list(portfolio.holdings.select_related("stock").order_by("id"))


def _to_domain(
    portfolio: models.Portfolio, holdings: list[models.Holding]
) -> domain.Portfolio:
    prices = domain.PriceSnapshot(
        {h.stock.symbol: h.stock.last_price for h in holdings}
    )
    stocks = {h.id: domain.Stock(h.stock.symbol, prices) for h in holdings}
    return domain.Portfolio(
        holdings={stocks[h.id]: h.quantity for h in holdings},
        # The API stores integer percents; the domain works with fractions.
        allocation={stocks[h.id]: Decimal(h.allocation) / HUNDRED for h in holdings},
        cash=portfolio.cash_leftover,
    )


def to_domain(portfolio: models.Portfolio) -> domain.Portfolio:
    """Build the domain Portfolio, with prices frozen as loaded from the DB."""
    return _to_domain(portfolio, _holdings(portfolio))


def rebalance(portfolio: models.Portfolio, cash: Decimal = Decimal(0)) -> RebalancePlan:
    """Plan the trades for `portfolio`, adding (cash > 0) or removing (cash < 0) cash."""
    holdings = _holdings(portfolio)
    plan = _to_domain(portfolio, holdings).rebalance(Decimal(cash))
    # A stock appears once per portfolio (unique_portfolio_stock).
    holding_ids = {h.stock.symbol: h.id for h in holdings}
    return RebalancePlan(
        total_value=plan.total_value,
        trades=[
            Trade(
                holding_id=holding_ids[t.symbol],
                symbol=t.symbol,
                action=t.action,
                quantity=t.quantity,
                price=t.price,
            )
            for t in plan.trades
        ],
        cash_leftover=plan.cash_leftover,
    )


class PendingPlanError(Exception):
    """The portfolio already has a rebalance plan waiting to be executed."""


class NoPendingPlanError(Exception):
    """The portfolio has no rebalance plan waiting to be executed."""


@transaction.atomic
def plan_rebalance(
    portfolio: models.Portfolio, cash: Decimal = Decimal(0)
) -> RebalancePlan:
    """Plan a rebalance and store it as the portfolio's pending plan.

    Only one plan can be pending. The plan is stored only if none is pending
    yet (compare-and-set on `pending_plan IS NULL`), so of two concurrent
    requests one stores its plan and the other gets PendingPlanError.
    """
    # Lock the row so holdings can't be replaced while the plan is computed.
    portfolio = models.Portfolio.objects.select_for_update().get(pk=portfolio.pk)
    if portfolio.pending_plan is not None:
        raise PendingPlanError("Portfolio has a pending rebalance plan")
    plan = rebalance(portfolio, cash)
    stored = models.Portfolio.objects.filter(
        pk=portfolio.pk, pending_plan__isnull=True
    ).update(pending_plan=plan.model_dump(mode="json"))
    if not stored:
        raise PendingPlanError("Portfolio has a pending rebalance plan")
    return plan


@transaction.atomic
def execute_pending_plan(portfolio: models.Portfolio) -> None:
    """Execute the portfolio's pending plan exactly once.

    The plan is read, checked and cleared in the same transaction as the trades,
    with the portfolio row locked. A concurrent request waits for the lock and
    then finds no plan, instead of applying the same trades a second time.
    """
    # Re-read under the lock: the caller's copy may hold a plan that another
    # request has executed since.
    portfolio = models.Portfolio.objects.select_for_update().get(pk=portfolio.pk)
    if portfolio.pending_plan is None:
        raise NoPendingPlanError("Portfolio has no pending rebalance plan")
    plan = RebalancePlan.model_validate(portfolio.pending_plan)
    # Claim the plan before touching any holding.
    portfolio.pending_plan = None
    portfolio.save(update_fields=["pending_plan"])
    execute_trade_plan(portfolio, plan)


@transaction.atomic
def execute_trade_plan(portfolio: models.Portfolio, plan: RebalancePlan) -> None:
    """Apply the plan's trades to the portfolio holdings and clear the plan."""
    for trade in plan.trades:
        holding = models.Holding.objects.filter(
            id=trade.holding_id, portfolio=portfolio
        ).first()
        if holding is None:
            raise domain.HoldingNotFoundError(
                f"Holding {trade.holding_id} not found in portfolio {portfolio.pk}"
            )
        if trade.action is domain.Action.SELL:
            new_quantity = holding.quantity - trade.quantity
        else:
            new_quantity = holding.quantity + trade.quantity
        if new_quantity < 0:
            raise domain.OversellError(
                f"Can't execute trade {trade}, final holding quantity must not "
                "be negative."
            )
        holding.quantity = new_quantity
        holding.save(update_fields=["quantity"])

    portfolio.cash_leftover = plan.cash_leftover
    portfolio.pending_plan = None
    portfolio.save(update_fields=["cash_leftover", "pending_plan"])


@transaction.atomic
def write_portfolio(portfolio: models.Portfolio, payload: PortfolioIn) -> None:
    """Create or fully replace a portfolio. Discards any pending rebalance plan."""
    portfolio.name = payload.name
    portfolio.cash_leftover = payload.cash_leftover
    portfolio.pending_plan = None
    portfolio.save()

    portfolio.holdings.all().delete()
    for h in payload.holdings:
        stock = models.Stock.objects.filter(symbol=h.symbol).first()
        if stock is None:
            raise domain.StockNotFoundError(f"Stock {h.symbol} not found")
        models.Holding.objects.create(
            portfolio=portfolio,
            stock=stock,
            quantity=h.quantity,
            allocation=h.allocation,
        )
