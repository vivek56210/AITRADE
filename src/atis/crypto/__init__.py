"""Automated BTC/ETH trend-following on Delta Exchange India perpetuals.

Selected by the study in src/docs/12-CRYPTO-STRATEGY.md: a 20/60/120-day time-series momentum
blend, long/short, each coin sized to 20% annualised volatility, rebalanced once a day. The same
signal code runs the backtest and the live bot. Paper trading is the default; live orders need
an explicit flag, API keys and a confirmation variable.
"""
