"""Data Ingestion Engine for Cboe Volatility Indices & Multi-Asset Underlying Time Series."""

import logging
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import numpy as np
import yfinance as yf

logger = logging.getLogger(__name__)

class CboeDataEngine:
    """Fetches real-time snapshots and historical daily closes for volatility indices and cross-assets."""

    VOL_INDICES = {
        'VIX': '^VIX',
        'VVIX': '^VVIX',
        'SKEW': '^SKEW',
        'VXN': '^VXN',
        'RVX': '^RVX',
        'GVZ': '^GVZ',
        'OVX': '^OVX'
    }

    CROSS_ASSETS = [
        ('S&P 500 (SPX)', 'SPY', '^VIX'),
        ('Nasdaq-100 (NDX)', 'QQQ', '^VXN'),
        ('Dow Jones (DIA)', 'DIA', '^VIX'),
        ('Russell 2000 (IWM)', 'IWM', '^RVX'),
        ('Gold (GLD)', 'GLD', '^GVZ'),
        ('Silver (SLV)', 'SLV', '^GVZ'),
        ('Bitcoin (IBIT)', 'IBIT', '^VIX'),
        ('Ethereum (ETHA)', 'ETHA', '^VIX'),
        ('Euro (FXE)', 'FXE', '^VIX'),
        ('British Pound (FXB)', 'FXB', '^VIX'),
        ('US Dollar (UUP)', 'UUP', '^VIX'),
        ('Crude Oil (USO)', 'USO', '^OVX'),
        ('10Y Treasury Yield (^TNX)', '^TNX', '^VIX'),
        ('30Y Treasury Yield (^TYX)', '^TYX', '^VIX')
    ]

    FALLBACK_MAP = {
        'IBIT': 'BTC-USD',
        'ETHA': 'ETH-USD',
        '^RVX': '^VIX',
        'QQQ': 'QQQ'
    }

    def fetch_live_volatility_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """Fetch live/most-recent price, previous close, and change for Cboe volatility indices."""
        results = {}
        for key, sym in self.VOL_INDICES.items():
            try:
                ticker_obj = yf.Ticker(sym)
                price = None
                prev = None

                # Fast info check
                try:
                    fast = getattr(ticker_obj, 'fast_info', None)
                    if fast:
                        price = getattr(fast, 'last_price', None) or fast.get('lastPrice')
                        prev = getattr(fast, 'previous_close', None) or fast.get('previousClose')
                except Exception:
                    pass

                # Fallback to history
                if price is None or prev is None or price <= 0:
                    hist = ticker_obj.history(period='5d')
                    if not hist.empty:
                        price = float(hist['Close'].iloc[-1])
                        prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else price

                # If still none and fallback exists
                if (price is None or price <= 0) and sym in self.FALLBACK_MAP:
                    fb_sym = self.FALLBACK_MAP[sym]
                    if fb_sym != sym:
                        fb_obj = yf.Ticker(fb_sym)
                        hist = fb_obj.history(period='5d')
                        if not hist.empty:
                            price = float(hist['Close'].iloc[-1])
                            prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else price

                if price is not None and price > 0:
                    chg = price - prev if prev else 0.0
                    chg_pct = (chg / prev * 100.0) if prev and prev > 0 else 0.0
                    results[key] = {
                        "symbol": sym,
                        "price": round(float(price), 2),
                        "previousClose": round(float(prev), 2) if prev else round(float(price), 2),
                        "change": round(float(chg), 2),
                        "changePercent": round(float(chg_pct), 2)
                    }
            except Exception as ex:
                logger.warning(f"Failed to fetch live snapshot for {sym}: {ex}")

        return results

    def fetch_historical_dataset(self, period: str = "1y") -> Optional[pd.DataFrame]:
        """Fetch historical daily close series for all volatility indices and cross-assets."""
        all_tickers = list(self.VOL_INDICES.values())
        for _, asset_ticker, vol_t in self.CROSS_ASSETS:
            if asset_ticker not in all_tickers:
                all_tickers.append(asset_ticker)
            if vol_t not in all_tickers:
                all_tickers.append(vol_t)

        for fb in self.FALLBACK_MAP.values():
            if fb not in all_tickers:
                all_tickers.append(fb)

        logger.info(f"Downloading historical data for {len(all_tickers)} tickers over period={period}...")

        try:
            raw = yf.download(all_tickers, period=period, interval="1d", progress=False, auto_adjust=False)
            if isinstance(raw.columns, pd.MultiIndex):
                if 'Close' in raw.columns.levels[0]:
                    df = raw['Close'].copy()
                elif 'Adj Close' in raw.columns.levels[0]:
                    df = raw['Adj Close'].copy()
                else:
                    df = raw.xs(raw.columns.levels[0][0], axis=1, level=0)
            else:
                df = raw.get('Close', raw).copy()

            # Check individual tickers if missing
            for t in all_tickers:
                if t not in df.columns or df[t].dropna().empty:
                    try:
                        logger.info(f"Retrying single ticker {t}...")
                        single_data = yf.download(t, period=period, interval="1d", progress=False, auto_adjust=False)
                        if not single_data.empty:
                            col = single_data['Close'] if 'Close' in single_data else single_data.iloc[:, 0]
                            df[t] = col
                    except Exception:
                        pass

            df = df.ffill().bfill()

            # Map fallback columns if primary crypto/index columns are missing
            for orig, fb in self.FALLBACK_MAP.items():
                if orig not in df.columns or df[orig].dropna().empty:
                    if fb in df.columns and not df[fb].dropna().empty:
                        df[orig] = df[fb]

            logger.info(f"Retrieved {len(df)} daily trading bars across {len(df.columns)} assets.")
            return df

        except Exception as e:
            logger.error(f"Error downloading macro analytics data: {e}", exc_info=True)
            return None
