from decimal import Decimal

import typer

from ._model import Holding, Portfolio, Stock

cli = typer.Typer()


@cli.command("run")
def run(
    fund: Decimal | int | str = 0,
    cash: Decimal | int | str = 1000,
):
    portfolio = Portfolio(
        holdings=[
            Holding(stock=Stock(symbol="META", last_price="500"), quantity=10),
            Holding(stock=Stock(symbol="AAPL", last_price="200"), quantity=20),
        ],
        allocation={"META": "40", "AAPL": "60"},
    )

    plan = portfolio.rebalance(fund)
    print(f"Starting with self-funded: ${plan.total_value}")
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
