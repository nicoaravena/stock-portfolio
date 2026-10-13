import typer
from rich.console import Console

from ._model import Holding, Portfolio, RebalancePlan, Stock

cli = typer.Typer()
console = Console()

def _plan_output(plan: RebalancePlan):
    console.print(f"Adding cash value: {plan.total_value}")
    for t in plan.trades:
        console.print(
            f"  {t.action.value:<4} {t.quantity:>3} {t.symbol} @ {t.price} = {t.amount}"
        )
    console.print(f"  Cash leftover: {plan.cash_leftover}")


def _portfolio_output(portfolio: Portfolio):
    console.print("Portfolio:")
    for sym in portfolio.holdings:
        h = portfolio.holdings[sym]
        console.print(
            f"  {h.symbol:<4} [{portfolio.allocation[sym]}%] {h.quantity:>3} x {h.stock.last_price} = {h.quantity*h.stock.last_price}"
        )
    console.print(f"  Cash leftover: {portfolio.cash_leftover}")


@cli.command("run")
def run(
    cash: float,
    cash_leftover: float = 0,
):
    portfolio = Portfolio(
        holdings={
            "META": Holding(stock=Stock(symbol="META", last_price="500"), quantity=10),
            "AAPL": Holding(stock=Stock(symbol="AAPL", last_price="200"), quantity=20),
        },
        allocation={"META": "40", "AAPL": "60"},
        cash_leftover=cash_leftover,
    )
    _portfolio_output(portfolio)
    console.rule(style="dim grey")

    plan = portfolio.rebalance()
    _plan_output(plan)
    console.print("> Executing trades...")
    portfolio.execute_trade_plan(plan)
    _portfolio_output(portfolio)
    console.rule(style="dim grey")

    plan = portfolio.rebalance(cash)
    _plan_output(plan)
    portfolio.execute_trade_plan(plan)
    console.print("> Executing trades...")
    _portfolio_output(portfolio)
