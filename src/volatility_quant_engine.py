"""Quantitative Risk Engine for Cboe Macro Volatility, SKEW Regimes, Exhibit 1 Spreads & Cross-Asset Correlation Matrix."""

import logging
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

class VolatilityQuantEngine:
    """Calculates cross-asset volatility spreads, SKEW tail-risk evaluations, and correlation matrices."""

    def evaluate_skew_regime(self, skew_val: float) -> Dict[str, Any]:
        """Evaluate Cboe SKEW index against institutional tail-risk benchmarks."""
        if skew_val >= 165.0:
            status = "Black Swan Crisis Spike (Rare Global Shock Level)"
            risk_tier = "CRITICAL_BLACK_SWAN"
            desc = (
                f"Cboe SKEW is at an extreme historical crisis spike ({skew_val:.2f}). "
                "Skew levels above 165-170 are exceptionally rare and historically occur only during "
                "major global black swan shocks (e.g. 2008 Financial Crisis, 2020 Pandemic shock)."
            )
            actionable_bias = "Max tail protection active; institutional market is pricing severe tail shock."
        elif skew_val >= 155.0:
            status = "Extreme Peak / Hedging Reversal Zone (155 - 160)"
            risk_tier = "EXTREME_REVERSAL"
            desc = (
                f"Cboe SKEW is trading in the Extreme Peak Zone ({skew_val:.2f}). Institutional demand for "
                "OTM Put protection has reached maximum satiation, rendering tail-risk hedges extremely expensive. "
                "Historically, this extreme band marks a reversal zone where hedging buying dries up."
            )
            actionable_bias = "Tail hedges are highly overpriced; consider selling rich out-of-the-money premium."
        elif skew_val >= 135.0:
            status = "High Tail Risk / Aggressive Put Buying"
            risk_tier = "ELEVATED_TAIL_RISK"
            desc = (
                f"Institutions are aggressively purchasing Out-of-The-Money (OTM) Put options to hedge against "
                f"a severe market crash. SKEW is elevated at {skew_val:.2f}."
            )
            actionable_bias = "Elevated downside protection demand; market participants are actively hedging."
        elif skew_val < 120.0:
            status = "Low Tail Risk / Benign Environment"
            risk_tier = "LOW_TAIL_RISK"
            desc = (
                f"Cboe SKEW is trading at {skew_val:.2f} (below 120), indicating low demand for tail-risk crash protection. "
                "OTM Puts are relatively cheap compared to historical levels."
            )
            actionable_bias = "Cost of tail-risk hedges is attractive; low hedging complacency."
        else:
            status = "Moderate Tail Risk / Balanced Hedging"
            risk_tier = "NORMAL_BALANCED"
            desc = (
                f"Cboe SKEW is at {skew_val:.2f}, within the normal historical corridor (120 - 135). "
                "Institutional hedging activity against extreme downside risk is balanced."
            )
            actionable_bias = "Hedging flow is in equilibrium."

        return {
            "skewValue": round(skew_val, 2),
            "status": status,
            "riskTier": risk_tier,
            "description": desc,
            "actionableBias": actionable_bias,
            "benchmarkThresholds": {
                "lowRiskFloor": "< 120",
                "normalHedging": "120 - 135",
                "highTailRisk": "135 - 155",
                "extremeReversalCeiling": "155 - 160",
                "blackSwanCrisis": "165 - 170+"
            }
        }

    def compute_exhibit1_volatility_matrix(
        self,
        hist_df: pd.DataFrame,
        asset_map: List[Tuple[str, str, str]]
    ) -> List[Dict[str, Any]]:
        """Compute Exhibit 1: 1M Implied Vol, 1M Realized Vol, IV-RV Spread, and 1Y Percentile across all assets."""
        rows = []
        if hist_df is None or hist_df.empty:
            return rows

        for label, asset_sym, vol_sym in asset_map:
            try:
                # 1M Realized Vol (21 trading days)
                if asset_sym in hist_df.columns and not hist_df[asset_sym].dropna().empty:
                    prices = hist_df[asset_sym].dropna()
                    if len(prices) >= 21:
                        ret_21 = prices.pct_change().dropna().tail(21)
                        rv_1m = float(ret_21.std() * np.sqrt(252) * 100.0)
                    else:
                        rv_1m = 15.0
                else:
                    rv_1m = 15.0

                # 1M Implied Vol & 1Y Percentile
                if vol_sym in hist_df.columns and not hist_df[vol_sym].dropna().empty:
                    vol_series = hist_df[vol_sym].dropna()
                    iv_1m = float(vol_series.iloc[-1])
                    percentile_1y = float((vol_series < iv_1m).mean() * 100.0)
                else:
                    iv_1m = rv_1m * 1.10
                    percentile_1y = 50.0

                spread_pts = iv_1m - rv_1m

                # Pricing condition
                if spread_pts > 4.0:
                    pricing_status = "Options Overpriced / Rich Premium (IV >> RV)"
                elif spread_pts < -2.0:
                    pricing_status = "Options Cheap / Discount (RV > IV)"
                else:
                    pricing_status = "Options Fairly Priced (IV ≈ RV)"

                rows.append({
                    "assetClass": label,
                    "ticker": asset_sym,
                    "volatilityTicker": vol_sym,
                    "impliedVolatility1M": round(iv_1m, 2),
                    "realizedVolatility1M": round(rv_1m, 2),
                    "ivRvSpreadPts": round(spread_pts, 2),
                    "historicalPercentile1Y": round(percentile_1y, 1),
                    "pricingCondition": pricing_status
                })

            except Exception as e:
                logger.warning(f"Error calculating Exhibit 1 row for {label}: {e}")

        return rows

    def compute_correlation_matrix(
        self,
        hist_df: pd.DataFrame,
        corr_assets: List[Tuple[str, str]],
        window_days: int = 21
    ) -> Dict[str, Any]:
        """Calculate pairwise correlation matrix across global asset classes over specified trading window."""
        avail_tuples = [(t, l) for t, l in corr_assets if t in hist_df.columns and not hist_df[t].dropna().empty]
        avail_tickers = [t for t, l in avail_tuples]
        avail_labels = [l for t, l in avail_tuples]

        if not avail_tickers or len(hist_df) < window_days:
            return {}

        sub_df = hist_df[avail_tickers].pct_change().dropna().tail(window_days)
        sub_df.columns = avail_labels
        corr_df = sub_df.corr().reindex(index=avail_labels, columns=avail_labels) * 100.0

        start_date = sub_df.index[0].strftime("%Y-%m-%d") if hasattr(sub_df.index[0], 'strftime') else str(sub_df.index[0])[:10]
        end_date = sub_df.index[-1].strftime("%Y-%m-%d") if hasattr(sub_df.index[-1], 'strftime') else str(sub_df.index[-1])[:10]

        matrix_dict = {}
        for r_label in avail_labels:
            matrix_dict[r_label] = {}
            for c_label in avail_labels:
                val = corr_df.loc[r_label, c_label]
                matrix_dict[r_label][c_label] = round(float(val), 1) if not np.isnan(val) else 0.0

        return {
            "windowTradingDays": len(sub_df),
            "startDate": start_date,
            "endDate": end_date,
            "assets": avail_labels,
            "matrix": matrix_dict
        }

    def generate_macro_quant_narrative(
        self,
        live_indices: Dict[str, Any],
        skew_eval: Dict[str, Any],
        exhibit1_rows: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate executive automated quantitative narrative."""
        narrative = []

        vix = live_indices.get('VIX', {}).get('price', 15.0)
        vvix = live_indices.get('VVIX', {}).get('price', 85.0)
        vvix_vix_ratio = (vvix / vix) if vix > 0 else 5.5

        # VIX & VVIX Commentary
        if vix < 15.0:
            vix_state = "Complacent / Low Volatility Regime"
        elif vix > 25.0:
            vix_state = "High Stress / Fear Regime"
        else:
            vix_state = "Normal Corridor Regime"

        narrative.append(
            f"• VIX is at {vix:.2f} ({vix_state}), with VVIX (Vol-of-Vol) at {vvix:.2f}. "
            f"VVIX/VIX Ratio is {vvix_vix_ratio:.2f}x."
        )

        # SKEW Commentary
        narrative.append(
            f"• Cboe SKEW Index is at {skew_eval['skewValue']:.2f} — {skew_eval['status']}. "
            f"{skew_eval['actionableBias']}"
        )

        # Variance Risk Premium Highlights
        rich_assets = [r['assetClass'] for r in exhibit1_rows if r['ivRvSpreadPts'] > 4.0]
        cheap_assets = [r['assetClass'] for r in exhibit1_rows if r['ivRvSpreadPts'] < -2.0]

        if rich_assets:
            narrative.append(f"• High Variance Risk Premium (Options Rich): {', '.join(rich_assets[:4])}.")
        if cheap_assets:
            narrative.append(f"• Realized Volatility Exceeding Implied (Options Cheap): {', '.join(cheap_assets[:4])}.")

        return narrative
