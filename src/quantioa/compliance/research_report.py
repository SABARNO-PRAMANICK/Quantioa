"""
Research report auto-generator.

SEBI requires Research Analysts to maintain detailed reports for each
algorithmic trading strategy. This module generates structured reports
from algorithm configuration, performance data, and AI model information.

Output format is Markdown, suitable for regulatory submission and client
communication.

Usage::

    from quantioa.compliance.research_report import ReportGenerator

    gen = ReportGenerator()
    report = gen.generate_strategy_report(
        strategy_id="momentum_v1",
        strategy_name="AI Momentum Strategy",
        description="RSI + MACD with AI optimization",
        indicators=["RSI(14)", "MACD(12,26,9)", "ATR(14)"],
        ai_model="moonshotai/kimi-k2.5",
        risk_params={"stop_loss_pct": 2.0, "max_daily_loss_pct": 2.0},
        performance={"win_rate": 0.62, "sharpe_ratio": 1.4},
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from quantioa.config import settings

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates SEBI-compliant research reports for algo strategies."""

    def generate_strategy_report(
        self,
        *,
        strategy_id: str,
        strategy_name: str,
        description: str = "",
        indicators: list[str] | None = None,
        ai_model: str = "",
        algo_type: str = "HYBRID",
        risk_params: dict | None = None,
        performance: dict | None = None,
        universe: str = "NIFTY50",
        timeframe: str = "Intraday / Swing",
        author: str = "Quantioa Research",
    ) -> str:
        """Generate a Markdown research report for a strategy.

        Returns the full report as a string. Can be saved to file or
        rendered in the client dashboard.
        """
        now = datetime.now(timezone.utc)
        ai_model = ai_model or settings.ai_model
        indicators = indicators or []
        risk_params = risk_params or {}
        performance = performance or {}

        report_lines = [
            f"# Strategy Research Report: {strategy_name}",
            "",
            f"**Strategy ID:** `{strategy_id}`",
            f"**Report Date:** {now.strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Author:** {author}",
            f"**Classification:** {algo_type}",
            "",
            "---",
            "",
            "## 1. Strategy Overview",
            "",
            description or f"Algorithmic trading strategy `{strategy_id}`.",
            "",
            f"- **Universe:** {universe}",
            f"- **Timeframe:** {timeframe}",
            f"- **AI Model:** `{ai_model}`",
            "",
        ]

        # Indicators section
        if indicators:
            report_lines.extend([
                "## 2. Technical Indicators Used",
                "",
            ])
            for ind in indicators:
                report_lines.append(f"- {ind}")
            report_lines.append("")

        # AI component disclosure
        report_lines.extend([
            "## 3. AI / Machine Learning Disclosure",
            "",
            "This strategy uses AI-powered signal generation and parameter optimization.",
            "",
            f"- **AI Model:** `{ai_model}`",
            "- **AI Role:** Signal confidence scoring, parameter optimization,",
            "  sentiment analysis integration",
            "- **Determinism:** Non-deterministic — same inputs may produce different outputs",
            "- **Reasoning Logged:** Full chain-of-thought reasoning is logged for every",
            "  AI decision (SEBI 5-year retention)",
            "",
        ])

        # Risk parameters
        if risk_params:
            report_lines.extend([
                "## 4. Risk Parameters",
                "",
                "| Parameter | Value |",
                "|-----------|-------|",
            ])
            for key, value in risk_params.items():
                label = key.replace("_", " ").title()
                report_lines.append(f"| {label} | {value} |")
            report_lines.append("")

        # Performance (if available)
        if performance:
            report_lines.extend([
                "## 5. Historical Performance",
                "",
                "> **Disclaimer:** Past performance is not indicative of future results.",
                "",
                "| Metric | Value |",
                "|--------|-------|",
            ])
            for key, value in performance.items():
                label = key.replace("_", " ").title()
                if isinstance(value, float) and key.endswith("_rate"):
                    report_lines.append(f"| {label} | {value:.1%} |")
                elif isinstance(value, float):
                    report_lines.append(f"| {label} | {value:.2f} |")
                else:
                    report_lines.append(f"| {label} | {value} |")
            report_lines.append("")

        # Risk disclosure
        report_lines.extend([
            "## 6. Risk Disclosure",
            "",
            "- Trading in securities involves substantial risk of loss",
            "- AI-generated signals are not guaranteed to be profitable",
            "- The strategy may experience periods of significant drawdown",
            "- Maximum daily loss is capped via risk management framework",
            "- Kill switch capability exists for emergency halt",
            "",
            "## 7. Regulatory Compliance",
            "",
            "- **SEBI Circular:** SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013",
            "- **Algo Registration:** Exchange-assigned unique Algo ID per order",
            "- **Audit Trail:** All decisions and orders logged for 5-year retention",
            "- **AI Reasoning:** Full LLM chain-of-thought stored per signal",
            "- **Client Consent:** Mandatory AI disclosure acceptance before trading",
            "",
            "---",
            "",
            f"*Generated by Quantioa Compliance Engine on {now.strftime('%Y-%m-%d')}*",
        ])

        report = "\n".join(report_lines)
        logger.info(
            "Research report generated: strategy=%s length=%d chars",
            strategy_id,
            len(report),
        )
        return report


# Singleton
report_generator = ReportGenerator()
