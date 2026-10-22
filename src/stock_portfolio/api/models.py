from django.db import models


class Stock(models.Model):
    symbol = models.CharField(max_length=16, primary_key=True)
    last_price = models.DecimalField(max_digits=20, decimal_places=6)

    def save(self, *args, **kwargs):
        self.symbol = self.symbol.strip().upper()  # ty: ignore[unresolved-attribute]
        super().save(*args, **kwargs)


class Portfolio(models.Model):
    name = models.CharField(max_length=100, unique=True)
    cash_leftover = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    pending_plan = models.JSONField(null=True, blank=True)  # latest RebalancePlan


class Holding(models.Model):
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
