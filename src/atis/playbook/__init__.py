"""Market Profile / Volume Profile playbook for NIFTY and BANKNIFTY index options.

Implements src/docs/10-VOLUME-PROFILE-PLAYBOOK.md: profile levels from index futures, open/day-type
classification, setups A1-A5, B1-B4, C1-C3, D1, option-structure selection and risk sizing.
Recommendation mode only - it emits signals and never places orders.
"""

from .backtest import BacktestResult, backtest
from .config import BANKNIFTY, INSTRUMENTS, NIFTY, CostParams, InstrumentSpec, PlaybookParams, RiskParams, SessionTimes
from .data import load_csv, path_session, synthetic_sessions, to_sessions
from .engine import PlaybookEngine, PremarketPlan, SessionReport
from .models import Bar, Direction, Session, SetupSignal, Structure
from .profile import TPOProfile, ValueArea, VolumeProfile
from .state import DayContext
from .structure import SessionProfile, analyze_session

__all__ = [
    "BANKNIFTY", "INSTRUMENTS", "NIFTY", "BacktestResult", "Bar", "CostParams", "DayContext", "Direction",
    "InstrumentSpec", "PlaybookEngine", "PlaybookParams", "PremarketPlan", "RiskParams", "Session",
    "SessionProfile", "SessionReport", "SessionTimes", "SetupSignal", "Structure", "TPOProfile", "ValueArea",
    "VolumeProfile", "analyze_session", "backtest", "load_csv", "path_session", "synthetic_sessions",
    "to_sessions",
]
