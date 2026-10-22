"""Portfolio rebalancing and persistence on top of the ORM models."""

from decimal import ROUND_FLOOR, Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404

from stock_portfolio.api import models
from stock_portfolio.api.schemas import (
    HUNDRED,
    Action,
    PortfolioIn,
    PortfolioOut,
    RebalancePlan,
    Trade,
)


def rebalance(portfolio: PortfolioOut, cash: Decimal = Decimal(0)) -> RebalancePlan:
    """Return the trades needed to reach the target allocation.

    - cash=0 (default): no cash added or retired.
    - cash>0: fresh cash is added to the pool before computing targets.
    - cash<0: cash is being removed from the portfolio before computing targets.
    - Whole shares only: target quantities are rounded DOWN so buys never
        exceed available funds; the remainder is reported as `cash_leftover`.
    - Holdings with a 0% allocation are sold fully.
    """
    total = portfolio.market_value + Decimal(cash) + portfolio.cash_leftover
    if total < 0:
        raise ValueError("cash must not be greater than market_value + cash_leftover")
    trades: list[Trade] = []
    invested = Decimal(0)

    for holding in portfolio.holdings:
        price = holding.stock.last_price
        target_value = total * holding.allocation / HUNDRED
        target_qty = int((target_value / price).to_integral_value(rounding=ROUND_FLOOR))
        invested += price * target_qty

        delta = target_qty - holding.quantity
        if delta != 0:
            trades.append(
                Trade(
                    holding_id=holding.id,
                    symbol=holding.stock.symbol,
                    action=Action.BUY if delta > 0 else Action.SELL,
                    quantity=abs(delta),
                    price=price,
                )
            )

    trades.sort(key=lambda t: t.action is Action.BUY)  # sells first
    return RebalancePlan(
        total_value=total, trades=trades, cash_leftover=total - invested
    )


@transaction.atomic
def execute_trade_plan(portfolio: models.Portfolio, plan: RebalancePlan) -> None:
    """Apply the plan's trades to the portfolio holdings and clear the plan."""
    for trade in plan.trades:
        holding = get_object_or_404(
            models.Holding, id=trade.holding_id, portfolio=portfolio
        )
        if trade.action is Action.SELL:
            new_quantity = holding.quantity - trade.quantity
        else:
            new_quantity = holding.quantity + trade.quantity
        if new_quantity < 0:
            raise ValueError(
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

    portfolio.holdings.all().delete()  # ty: ignore[unresolved-attribute]
    for h in payload.holdings:
        models.Holding.objects.create(  # ty: ignore[unresolved-attribute]
            portfolio=portfolio,
            stock=get_object_or_404(models.Stock, symbol=h.symbol),
            quantity=h.quantity,
            allocation=h.allocation,
        )
