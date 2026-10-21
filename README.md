# PoC Stock Portfolio

This is just a PoC to solve this 3 points:

- You’re building a portfolio management module, part of a personal investments and trading app
- Construct a simple Portfolio class that has a collection of Stocks. Assume each Stock has a “Current Price” method that receives the last available price. Also, the Portfolio class has a collection of “allocated” Stocks that represents the distribution of the Stocks the Portfolio is aiming (i.e. 40% META, 60% APPL)
- Provide a portfolio rebalance method to know which Stocks should be sold and which ones should be bought to have a balanced Portfolio based on the portfolio’s allocation.


## Assumptions

- Portfolio rebalancing logic implemented in `Portfolio.rebalance()` method
- The price of the stocks are manually updated.
- The price of a holding to be traded (sell/buy) is saved in the Trade model to be used in the execution of the rebalance.
- Portfolio plan execution logic implemented in `Portfolio.execute_trade_plan()` method
- The execution of the rebalance plan does not check if the stock price differ with the one saved for trade.
- Only whole shares are traded (rounds down to nearest whole share).
- A rebalance could add or remove cash to the portfolio to be computed in the process.
