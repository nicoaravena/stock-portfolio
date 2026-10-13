from decimal import Decimal

import typer
from rich import print

from ._model import Holding, Portfolio, Stock

cli = typer.Typer()


@cli.command("run")
def run(
    cash: float,
):
    portfolio = Portfolio(
        holdings={
            "META": Holding(stock=Stock(symbol="META", last_price="500"), quantity=10),
            "AAPL": Holding(stock=Stock(symbol="AAPL", last_price="200"), quantity=20),
        },
        allocation={"META": "40", "AAPL": "60"},
    )

    plan = portfolio.rebalance()
    print(f"Rebalance self-funded portfolio (initial): ${plan.total_value}")
    for t in plan.trades:
        print(
            f"  {t.action.value:<4} {t.quantity:>3} {t.symbol} @ {t.price} = {t.amount}"
        )
    print(f"  cash leftover: {plan.cash_leftover}\n")

    plan = portfolio.rebalance(cash)
    print(f"Adding cash value: {plan.total_value}")
    for t in plan.trades:
        print(
            f"  {t.action.value:<4} {t.quantity:>3} {t.symbol} @ {t.price} = {t.amount}"
        )
    print(f"  cash leftover: {plan.cash_leftover}")
