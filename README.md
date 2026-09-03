# Multi-strategy-momentum-trading-bot

Algorithmic trading bot written in Python, connected to Interactive Brokers via the TWS API, that trades low-float small-cap U.S. equities with a long-only bias.

> ⚠️ **Project status**: Completed. The bot is currently not profitable in live trading — see [Status & limitations](#status--limitations) for an honest breakdown of why, and what's being fixed.

---

## Table of contents
- [Motivation](#motivation)
- [Strategies](#strategies)
- [Architecture](#architecture)
- [Risk management](#risk-management)
- [Backtesting](#backtesting)
- [Status & limitations](#status--limitations)
- [Next steps](#next-steps)
- [Tech stack](#tech-stack)
- [Installation / usage](#installation--usage)

---

## Motivation
The goal behind this project was to get started in the world of quantitative finance by building an algorithm capable of trading according to parameters I defined myself — regardless of whether the resulting strategy turned out to be profitable or not. The focus was on the engineering: connecting to a real broker, handling live market data, and automating the full decision-making pipeline end to end.

## Strategies
The bot runs **two strategies in parallel**, each with its own scanner and premarket volume filter:

| Strategy | Time window (ET) | Premarket vol. filter | Entry condition |
|---|---|---|---|
| `LONG10MIN` | 9:40 - 9:50 | ≤ 1M | `change_from_open > 0%` and session volume between 100k-500k |
| `LONG10MIN2` | 9:30 - 9:40 | ≤ 300k | `change_from_open > 2%` and session volume between 100k-500k |

**Universe filters (scanner)**: max market cap $200M, max float 20M shares (via `yfinance`), minimum gap per scanner config.

## Architecture
```
main.py                 → orchestrates everything: connection, scanners, signal loop
├── ohlc/Data.py         → IBConnection (EClient/EWrapper wrapper) + Ohlc class (one per symbol)
├── Scanner/
│   ├── ScannerClient.py     → a single IB scanner subscription
│   └── ScannerManager.py    → filters new symbols (premarket vol, float) and creates Ohlc instances
├── Strategy/Strategy.py → signal logic (Conditions + strategy classes)
└── PositionManager.py   → position limits, risk per trade, notifications
```

Flow: IB's scanner detects candidates → `ScannerManager` filters them (premarket volume, float) on separate threads so the connection thread never blocks → each symbol that passes gets its own `Ohlc` instance subscribed to historical/real-time data → the main loop evaluates entry conditions → on a signal, `PositionManager` checks available slots and liquidity, then executes the order.

## Risk management
- Max 5 simultaneous positions, $1,000 risk per trade
- Fixed TP/SL: +20% / -5%
- Liquidity check before entry (minimum average volume, max 1.5% spread)
- Hard GTC stop sent to the broker (protects against the bot going down)
- Recovers open positions on restart (`reqPositions`)
- Notifications (console + optional email) when a signal can't be executed

## Backtesting
The strategies were developed and iterated on using Flash Research as the backtesting simulator. However, survivorship bias, look-ahead bias, and overoptimization in that environment make these backtest results invalid as a basis for live trading — the numbers looked strong in simulation but don't reliably translate to real market conditions. This gap is the main reason the bot's live results diverge from what the backtests suggested.

## Status & limitations
- **Live vs. backtest discrepancy**: in simulation, the bot returned close to 20% in about two weeks. That performance did not carry over to live trading — most likely a combination of statistical variance (a short two-week sample isn't representative) and the strategy itself not being sufficiently well-designed or robust.
- **Scanner bug with ETF's**: the scanner occasionally generated entry signals on ETFs, which don't fit the small-cap/low-float thesis this bot targets. In practice, Interactive Brokers itself rejected these orders, so no bad trades were actually executed — but the underlying filter should be fixed so the bot doesn't attempt them in the first place.
- **Error handling**: the bot has not been hardened against every possible failure mode (network drops, unexpected API responses, edge-case market conditions, etc.) — some error handling is in place (see `IBConnection.error`), but it hasn't been stress-tested exhaustively.

## Next steps
The original goal of this project — building an algorithm that trades automatically according to parameters I define — has been achieved. There are no further planned steps at this time.

## Tech stack
- Python
- `ibapi` (Interactive Brokers TWS API)
- `yfinance` (float data)
- Flash Research (backtesting)
- Excel (trade log and performance dashboard)

## Installation / usage
```bash
git clone https://github.com/yourusername/long10min.git
cd long10min

# Create and activate a virtual environment (Python 3.9)
python3.9 -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```
Requires TWS or IB Gateway running locally with the API enabled (port configurable in `main.py`).

---

*Personal algorithmic trading project.*
