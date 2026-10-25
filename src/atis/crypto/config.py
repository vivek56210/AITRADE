"""Parameters for the crypto trend bot. Every default is the value the study tested (no tuning)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Market:
    symbol: str  # Delta Exchange India perpetual
    binance: str  # Binance symbol used for the long backtest history
    contract_value: float  # coins per contract


MARKETS = {
    "BTCUSD": Market("BTCUSD", "BTCUSDT", 0.001),
    "ETHUSD": Market("ETHUSD", "ETHUSDT", 0.01),
}


@dataclass(frozen=True)
class TrendParams:
    lookbacks: tuple[int, ...] = (20, 60, 120)  # days; the signal is the mean sign of these returns
    vol_window: int = 30  # days of daily log returns for realised volatility
    target_vol: float = 0.20  # annualised volatility each coin is sized to
    max_exposure: float = 1.0  # notional / equity cap per coin (history never exceeded 0.91)
    band: float = 0.25  # skip a rebalance smaller than this fraction of the current position
    long_only: bool = False


@dataclass(frozen=True)
class RiskLimits:
    """Disaster brakes, set outside anything the strategy did in 2018-2026."""

    max_gross_exposure: float = 1.5  # sum of |notional| / equity across coins
    daily_loss_halt: float = 0.08  # worst historical day -5.65%
    drawdown_halt: float = 0.30  # worst historical drawdown -20%
    max_price_deviation: float = 0.02  # signal price vs live mark price
    max_data_age_hours: float = 30.0  # newest completed daily candle must be this fresh
    exchange_leverage: int = 2  # isolated-margin leverage set on each product (liquidation ~50% away)


@dataclass(frozen=True)
class Costs:
    taker: float = 0.0005 * 1.18  # Delta India taker fee incl. 18% GST, per side
    slippage: float = 0.0002  # per side
    default_funding: float = 0.0001  # per 8 hours, when no funding history exists (longs pay)

    @property
    def per_side(self) -> float:
        return self.taker + self.slippage


@dataclass(frozen=True)
class BotConfig:
    markets: tuple[str, ...] = ("BTCUSD", "ETHUSD")
    weights: dict[str, float] = field(default_factory=lambda: {"BTCUSD": 0.5, "ETHUSD": 0.5})
    trend: TrendParams = TrendParams()
    risk: RiskLimits = RiskLimits()
    costs: Costs = Costs()
