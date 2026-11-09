from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import RelatedManager


class Stock(models.Model):
    symbol = models.CharField(max_length=16, primary_key=True)
    last_price = models.DecimalField(max_digits=20, decimal_places=6)

    def save(self, *args, **kwargs):
        self.symbol = self.symbol.strip().upper()
        super().save(*args, **kwargs)


class Portfolio(models.Model):
    if TYPE_CHECKING:  # created by Django at runtime; declared for type checkers
        id: int
        holdings: RelatedManager["Holding"]

    name = models.CharField(max_length=100, unique=True)
    cash_leftover = models.DecimalField(
        max_digits=20, decimal_places=6, default=Decimal(0)
    )
    pending_plan = models.JSONField(null=True, blank=True)  # latest RebalancePlan


class Holding(models.Model):
    if TYPE_CHECKING:  # implicit primary key, declared for type checkers
        id: int

    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="holdings"
    )
    stock = models.ForeignKey(Stock, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=0)
    allocation = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = (
            models.UniqueConstraint(
                fields=["portfolio", "stock"], name="unique_portfolio_stock"
            ),
        )
