# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

中国股票量化自动交易系统 - A modular A-share quantitative trading platform supporting strategy development, backtesting, paper trading, and real-time monitoring.

**Key Technologies**: Python 3.10+, pandas, numpy, tushare, backtrader, APScheduler, FastAPI, Streamlit

## Common Commands

### Development Setup
```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
# Or with extras
pip install -e ".[dev,web,viz]"
```

### Database & Data
```bash
# Initialize database
python -m src.utils.database

# Update market data
python main.py update-data
python main.py update-data --extended-pool

# Fetch long-term historical data
python scripts/fetch_historical_data.py
python scripts/fetch_3year_data.py
```

### Testing & Quality
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_strategy.py
pytest tests/test_backtest.py
pytest tests/test_data.py

# Code formatting
black . --line-length 100

# Type checking
mypy src/

# Linting
flake8 src/
```

### Running the System
```bash
# Start paper trading
python run_paper_trading.py
python start_paper_conservative.py

# Start scheduler
python start_services.py scheduler

# Web monitoring interface
python web_server.py        # Flask-based (port 8801)
streamlit run streamlit_monitor/app.py  # Streamlit (port 8501)
```

### Backtesting
```bash
# Basic backtest
python main.py backtest --strategy optimal

# With date range
python main.py backtest --strategy optimal --start-date 20240324 --end-date 20260323

# Cross-cycle validation
python main.py cross-cycle --strategy optimal --years 3

# Strategy comparison
python scripts/strategy_v5_backtest.py
```

## High-Level Architecture

### Module Structure

```
src/
├── data_collector/      # Data acquisition layer
│   ├── tushare_client.py    # Primary data source (Tushare API)
│   ├── baostock_client.py   # Alternative source (historical)
│   ├── sina_client.py       # Real-time quotes via Sina
│   ├── sohu_client.py       # Backup real-time (Tencent format)
│   └── data_manager.py      # Data orchestration & caching
├── data_pipeline/       # Real-time data processing
│   ├── daily_updater.py     # EOD data updates
│   └── realtime_feed.py     # Live market data feed
├── strategy/            # Trading strategies
│   ├── base_strategy.py     # Abstract base class
│   ├── optimal_strategy.py  # Main production strategy (v5.0)
│   ├── technical.py         # Technical indicator strategies
│   ├── trend_follow.py      # Trend following strategies
│   ├── mean_reversion.py    # Mean reversion strategies
│   ├── multi_strategy_portfolio.py  # Portfolio allocation
│   ├── sharpe_optimizer.py  # Sharpe ratio enhancement
│   ├── win_rate_optimizer.py # Win rate optimization
│   ├── fundamental_factors.py # Fundamental scoring
│   └── market_filter.py     # Market regime detection
├── strategy_engine/     # Signal generation & scheduling
│   ├── signal.py            # Signal data model
│   └── signal_scheduler.py  # Signal timing management
├── backtest/            # Backtesting framework
│   ├── engine.py            # Backtest engine (wrapper around backtrader)
│   └── performance.py       # Performance metrics calculation
├── trader/              # Execution layer
│   ├── broker_api.py        # Paper trading broker
│   ├── easytrader_broker.py # Real broker integration
│   ├── risk_control.py      # Risk management rules
│   ├── scheduler.py         # Trading bot & task scheduler
│   ├── order_manager.py     # Order lifecycle management
│   ├── realtime_monitor.py  # Position/price monitoring
│   └── emergency_handler.py # Circuit breakers & stops
├── utils/               # Shared utilities
│   ├── database.py          # SQLite abstraction layer
│   ├── helpers.py           # Common functions (formatting, validation)
│   └── dingtalk_notifier.py # Alert notifications
└── performance/         # Performance tracking
    └── metrics.py           # Return/Sharpe/max-drawdown calculations

streamlit_monitor/     # Streamlit dashboard (v2.0)
├── app.py               # Main entry point
├── config.py            # Dashboard configuration
├── components/          # Reusable UI components
│   ├── charts.py        # Price/volume/return charts
│   ├── status_cards.py  # Metric display cards
│   └── log_viewer.py    # Log tailing & filtering
├── pages/               # Dashboard pages
│   ├── monitor.py       # System overview
│   ├── portfolio.py     # Holdings & positions
│   ├── signals.py       # Trading signals
│   ├── performance.py   # Return analytics
│   └── admin.py         # System controls
└── utils/               # Dashboard utilities
    ├── data_fetcher.py  # Cached data access
    ├── log_parser.py    # Log parsing & analysis
    └── system_info.py   # Process status & resources
```

### Data Flow Architecture

1. **Data Collection**: Tushare (primary) → Baostock (historical backup) → Sina/Tencent (real-time)
2. **Data Storage**: SQLite database (`data/quant_trading.db`) with tables for prices, fundamentals, trades, signals
3. **Strategy Processing**: Multi-factor scoring → Signal generation → Order creation
4. **Execution**: Paper broker (simulation) → Easytrader (real trading)
5. **Monitoring**: Real-time position tracking → Alerts → Streamlit dashboard

### Key Design Patterns

**Strategy Pattern**: All strategies inherit from `BaseStrategy` and implement:
- `on_bar(data) -> Signal` - Main signal generation logic
- `get_parameters() -> Dict` - Strategy configuration

**Data Access Pattern**: Database access through `Database` class context managers:
```python
from src.utils.database import Database
db = Database()
with db.get_connection() as conn:
    df = pd.read_sql("SELECT * FROM daily_quotes", conn)
```

**Risk Control Chain**: All orders pass through `RiskController.validate_order()` which checks:
- Position limits (`MAX_POSITION_RATIO`, `MAX_STOCK_POSITION_RATIO`)
- Price anomalies
- Daily loss limits (`MAX_DAILY_LOSS`)

### Configuration Hierarchy

1. **Environment variables** (`.env` file) - API keys, secrets, mode switches
2. **config/settings.py** - Trading parameters, thresholds, schedules
3. **config/broker_config.json** - Broker-specific credentials (gitignored)
4. **streamlit_monitor/config.py** - Dashboard UI configuration

Critical env vars:
- `TUSHARE_TOKEN` - Required for data collection
- `PAPER_TRADING=true/false` - Simulation mode
- `REAL_TRADING_MODE=true/false` - Live trading (DANGER)
- `DATABASE_URL` - SQLite path (default: `sqlite:///data/quant_trading.db`)

### Database Schema

Key tables:
- `daily_quotes` - OHLCV price data
- `fundamentals` - Financial metrics (ROE, PE, etc.)
- `trades` - Executed trades log
- `signals` - Generated trading signals
- `account` - Portfolio value history
- `positions` - Current holdings

### Testing Conventions

- Tests in `tests/` directory
- Naming: `test_*.py` for files, `test_*` for functions
- Run with: `pytest tests/test_strategy.py -v`
- Coverage: `pytest --cov=src tests/`

### Code Style

- Black formatter: 100 character line length
- Imports: stdlib → third-party → local (src.config, src.utils, etc.)
- Type hints encouraged but not strictly enforced
- Docstrings in Chinese for business logic, English for technical utilities
