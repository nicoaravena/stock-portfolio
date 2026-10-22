from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from ninja import Router, Status

from stock_portfolio.api import models, services
from stock_portfolio.api.schemas import (
    ErrorOut,
    PortfolioIn,
    PortfolioOut,
    RebalanceIn,
    RebalancePlan,
)

from ._exceptions import Conflict

router = Router(tags=["portfolio"])


def _load(portfolio_id: int) -> models.Portfolio:
    return get_object_or_404(
        models.Portfolio.objects.prefetch_related("holdings__stock"),  # ty: ignore[unresolved-attribute]
        id=portfolio_id,
    )


@router.get("", response=list[PortfolioOut])
def list_portfolios(request):
    return models.Portfolio.objects.prefetch_related("holdings__stock").order_by("id")  # ty: ignore[unresolved-attribute]


@router.get("/{portfolio_id}", response=PortfolioOut)
def get_portfolio(request, portfolio_id: int):
    return _load(portfolio_id)


@router.post("", response={201: PortfolioOut, 409: ErrorOut})
def create_portfolio(request, payload: PortfolioIn):
    try:
        with transaction.atomic():
            portfolio = models.Portfolio()
            services.write_portfolio(portfolio, payload)
    except IntegrityError:
        raise Conflict(f"Portfolio {payload.name} already exists")
    return Status(201, _load(portfolio.id))


@router.put("/{portfolio_id}", response={200: PortfolioOut, 409: ErrorOut})
def update_portfolio(request, portfolio_id: int, payload: PortfolioIn):
    portfolio = get_object_or_404(models.Portfolio, id=portfolio_id)
    try:
        with transaction.atomic():
            services.write_portfolio(portfolio, payload)
    except IntegrityError:
        raise Conflict(f"Portfolio {payload.name} already exists")
    return _load(portfolio_id)


@router.delete("/{portfolio_id}", response={204: None})
def delete_portfolio(request, portfolio_id: int):
    get_object_or_404(models.Portfolio, id=portfolio_id).delete()
    return Status(204, None)


@router.post("/{portfolio_id}/rebalance", response={200: RebalancePlan, 409: ErrorOut})
def rebalance_portfolio(request, portfolio_id: int, payload: RebalanceIn):
    portfolio = _load(portfolio_id)
    if portfolio.pending_plan:
        raise Conflict("Portfolio has a pending rebalance plan")
    plan = services.rebalance(PortfolioOut.from_orm(portfolio), payload.cash)
    portfolio.pending_plan = plan.model_dump(mode="json")
    portfolio.save(update_fields=["pending_plan"])
    return plan


@router.post(
    "/{portfolio_id}/execute-trades",
    response={200: PortfolioOut, 409: ErrorOut},
)
def execute_trades(request, portfolio_id: int):
    portfolio = get_object_or_404(models.Portfolio, id=portfolio_id)
    if portfolio.pending_plan is None:
        raise Conflict("Portfolio has no pending rebalance plan")
    plan = RebalancePlan.model_validate(portfolio.pending_plan)
    services.execute_trade_plan(portfolio, plan)
    return _load(portfolio_id)
