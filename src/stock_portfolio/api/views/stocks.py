from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from ninja import Router, Status

from stock_portfolio.api import models
from stock_portfolio.api.schemas import (
    ErrorOut,
    StockIn,
    StockOut,
    StockPriceIn,
)

from ._exceptions import Conflict

router = Router(tags=["stock"])


@router.get("", response=list[StockOut])
def list_stocks(request):
    return models.Stock.objects.order_by("symbol")  # ty: ignore[unresolved-attribute]


@router.get("/{symbol}", response=StockOut)
def get_stock(request, symbol: str):
    return get_object_or_404(models.Stock, symbol=symbol.upper())


@router.post("", response={201: StockOut, 409: ErrorOut})
def create_stock(request, payload: StockIn):
    try:
        with transaction.atomic():
            stock = models.Stock(**payload.dict())
            stock.save(force_insert=True)
    except IntegrityError:
        raise Conflict(f"Stock {payload.symbol.upper()} already exists")
    return Status(201, stock)


@router.put("/{symbol}", response=StockOut)
def update_stock(request, symbol: str, payload: StockPriceIn):
    stock = get_object_or_404(models.Stock, symbol=symbol.upper())
    stock.last_price = payload.last_price
    stock.save()
    return stock


@router.delete("/{symbol}", response={204: None, 409: ErrorOut})
def delete_stock(request, symbol: str):
    stock = get_object_or_404(models.Stock, symbol=symbol.upper())
    try:
        stock.delete()
    except ProtectedError:
        raise Conflict(f"Stock {stock.symbol} is held by a portfolio")
    return Status(204, None)
