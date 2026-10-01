"""Main Entrypoint for Cboe Macro Volatility & Quant Risk Analytics Actor."""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List
from apify import Actor

from src.data_engine import CboeDataEngine
from src.volatility_quant_engine import VolatilityQuantEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("cboe-macro-volatility-actor")


async def main() -> None:
    """Actor main routine."""
    async with Actor:
        actor_input = await Actor.get_input() or {}

        lookback_period = str(actor_input.get("lookbackPeriod", "1y")).strip().lower()
        corr_window = int(actor_input.get("correlationWindowDays", 21))
        include_corr_mat = bool(actor_input.get("includeCorrelationMatrix", True))
        include_hist_series = bool(actor_input.get("includeHistoricalSeries", True))

        logger.info("Starting Cboe Macro Volatility & Quant Risk Analytics Actor...")
        logger.info(f"Parameters: lookbackPeriod={lookback_period}, correlationWindow={corr_window} days")

        data_engine = CboeDataEngine()
        quant_engine = VolatilityQuantEngine()

        # 1. Fetch live volatility snapshots & historical time series
        live_indices = data_engine.fetch_live_volatility_snapshots()
        hist_df = data_engine.fetch_historical_dataset(period=lookback_period)

        if hist_df is None or hist_df.empty:
            logger.error("Failed to fetch historical cross-asset dataset. Aborting.")
            return

        # 2. SKEW Deep Dive Evaluation
        skew_val = live_indices.get("SKEW", {}).get("price")
        if skew_val is None or skew_val <= 0:
            if "^SKEW" in hist_df.columns and not hist_df["^SKEW"].dropna().empty:
                skew_val = float(hist_df["^SKEW"].dropna().iloc[-1])
            else:
                skew_val = 125.0

        skew_evaluation = quant_engine.evaluate_skew_regime(skew_val)

        # 3. VIX vs VVIX Dynamics
        vix_val = live_indices.get("VIX", {}).get("price", 15.0)
        vvix_val = live_indices.get("VVIX", {}).get("price", 85.0)
        vvix_vix_ratio = round(vvix_val / vix_val, 2) if vix_val > 0 else 5.5

        vix_vvix_dynamics = {
            "vix": vix_val,
            "vvix": vvix_val,
            "vvixVixRatio": vvix_vix_ratio,
            "volOfVolStressRegime": "High Stress / Vol Velocity Alert" if vvix_val > 110.0 else ("Normal Corridor" if vvix_val >= 80.0 else "Quiet Volatility Floor")
        }

        # 4. Exhibit 1: Global Volatilities & Realized Spread Matrix
        exhibit1_rows = quant_engine.compute_exhibit1_volatility_matrix(
            hist_df=hist_df,
            asset_map=CboeDataEngine.CROSS_ASSETS
        )

        # 5. Cross-Asset Correlation Matrix Heatmap
        corr_assets = [
            ('SPY', 'SPX (Equities)'),
            ('QQQ', 'QQQ (Tech)'),
            ('DIA', 'DIA (Dow Jones)'),
            ('IWM', 'IWM (Russell 2000)'),
            ('GLD', 'GLD (Gold)'),
            ('SLV', 'SLV (Silver)'),
            ('IBIT', 'IBIT (Bitcoin)'),
            ('ETHA', 'ETHA (Ethereum)'),
            ('FXE', 'FXE (Euro)'),
            ('FXB', 'FXB (GBP)'),
            ('UUP', 'UUP (US Dollar)'),
            ('USO', 'USOIL (Crude Oil)'),
            ('^TNX', '10Y Yield'),
            ('^TYX', '30Y Yield')
        ]

        correlation_data = quant_engine.compute_correlation_matrix(
            hist_df=hist_df,
            corr_assets=corr_assets,
            window_days=corr_window
        ) if include_corr_mat else {}

        # 6. Automated Executive Narrative
        narrative = quant_engine.generate_macro_quant_narrative(
            live_indices=live_indices,
            skew_eval=skew_evaluation,
            exhibit1_rows=exhibit1_rows
        )

        # 7. Push Dataset Records
        dataset_records = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for row in exhibit1_rows:
            dataset_records.append({
                **row,
                "updatedAt": now_iso
            })

        if dataset_records:
            logger.info(f"Pushing {len(dataset_records)} Exhibit 1 records to Apify dataset...")
            await Actor.push_data(dataset_records)

        # 8. Save Comprehensive Report to Key-Value Store (OUTPUT)
        output_payload = {
            "title": "Cboe Macro Volatility & Institutional Quant Risk Analytics Report",
            "timestamp": now_iso,
            "liveIndices": live_indices,
            "skewTailRiskModel": skew_evaluation,
            "vixVvixDynamics": vix_vvix_dynamics,
            "globalVolatilitiesExhibit1": exhibit1_rows,
            "crossAssetCorrelationMatrix": correlation_data,
            "automatedQuantNarrative": narrative
        }
        await Actor.set_value("OUTPUT", output_payload)

        logger.info(
            f"Actor completed successfully! SKEW: {skew_val:.2f} ({skew_evaluation['status']}), "
            f"VIX: {vix_val:.2f}, VVIX: {vvix_val:.2f}, Processed {len(exhibit1_rows)} cross-asset volatility spreads."
        )


if __name__ == "__main__":
    asyncio.run(main())
