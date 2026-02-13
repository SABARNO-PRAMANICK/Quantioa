"""
Sentiment analysis prompts — used by Perplexity Sonar Deep Research.

Model: perplexity/sonar-deep-research

This model is called ONLY by the standalone Sentiment Service every 6 hours.
The trading agent never calls this model — it reads cached results only.

The prompts are designed to produce a deep, structured financial research
report with strict JSON output.
"""

from __future__ import annotations

# ─── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM = """\
You are a senior financial research analyst at an institutional trading desk \
specializing in the Indian equity markets (NSE/BSE). Your role is to produce \
a comprehensive sentiment research report that will inform algorithmic \
trading decisions.

IMPORTANT RULES:
1. You MUST return your entire response as a single valid JSON object — no \
   markdown, no code fences, no prose before or after the JSON.
2. Base your analysis ONLY on verifiable recent information — never speculate \
   or fabricate data points.
3. Distinguish clearly between facts and your analytical interpretation.
4. Score sentiment on a continuous scale from -1.0 (extremely bearish) to \
   +1.0 (extremely bullish), with 0.0 being perfectly neutral.
5. Your confidence score (0.0 to 1.0) should reflect the quantity and \
   quality of information available — lower confidence when data is sparse \
   or contradictory.

RESPONSE JSON SCHEMA:
{
    "score": <float, -1.0 to +1.0>,
    "confidence": <float, 0.0 to 1.0>,
    "summary": "<string, 2-3 sentence executive summary>",
    "detailed_analysis": "<string, comprehensive multi-paragraph analysis>",
    "headlines": ["<string, key headline 1>", "<string, key headline 2>", ...],
    "factors": {
        "domestic_macro": {
            "score": <float>,
            "details": "<string>"
        },
        "global_cues": {
            "score": <float>,
            "details": "<string>"
        },
        "sector_specific": {
            "score": <float>,
            "details": "<string>"
        },
        "institutional_flows": {
            "score": <float>,
            "details": "<string>"
        },
        "technical_context": {
            "score": <float>,
            "details": "<string>"
        }
    },
    "risks": ["<string, key risk 1>", "<string, key risk 2>", ...],
    "catalysts": ["<string, upcoming catalyst 1>", "<string, catalyst 2>", ...]
}
"""

SYSTEM_SHORT = """\
You are a financial sentiment analyst for Indian equity markets. \
Return your response as a single valid JSON object with keys: \
"score" (float, -1.0 to +1.0), "confidence" (float), "summary" (string), \
"headlines" (list of strings). No markdown, no code fences — only JSON.\
"""


# ─── User Prompt Builders ─────────────────────────────────────────────────────


def user_prompt(symbol: str) -> str:
    """Build the full deep-research prompt for the Sentiment Service.

    This prompt is designed for perplexity/sonar-deep-research and
    instructs it to conduct a thorough multi-dimensional analysis.
    """
    return f"""\
Conduct an in-depth sentiment and market intelligence report for \
**{symbol}** in the Indian stock market (NSE/BSE). Your research must \
cover the following dimensions thoroughly:

1. **DOMESTIC MACROECONOMIC ENVIRONMENT**
   - RBI monetary policy stance, recent rate decisions, and forward guidance
   - Latest CPI/WPI inflation data and trajectory
   - GDP growth estimates and industrial production (IIP) data
   - Government fiscal policy, budget announcements, or policy reforms
   - INR/USD exchange rate movements and forex reserves

2. **GLOBAL MARKET CUES**
   - US Federal Reserve policy and US Treasury yield movements
   - Performance of major global indices (S&P 500, Nasdaq, FTSE, Nikkei, \
     Hang Seng) in the last 24-48 hours
   - Crude oil (Brent) price movements and OPEC decisions
   - Geopolitical developments affecting emerging markets
   - US-China trade relations and global supply chain disruptions

3. **SECTOR-SPECIFIC INTELLIGENCE FOR {symbol}**
   - Recent corporate earnings results and guidance from major constituents
   - Sector rotation trends — is money flowing into or out of this sector?
   - Regulatory changes affecting the sector (SEBI directives, government \
     regulations, licensing changes)
   - Competitor performance and market share shifts

4. **INSTITUTIONAL FLOW ANALYSIS**
   - FII (Foreign Institutional Investor) activity — net buying or selling \
     in the last 1-5 trading sessions
   - DII (Domestic Institutional Investor) activity and mutual fund flows
   - Promoter buying/selling patterns in key constituent stocks
   - Bulk deals and block deals in the last week

5. **MARKET TECHNICAL CONTEXT**
   - Where is {symbol} relative to its 52-week high/low?
   - Key support and resistance levels being tested
   - Overall market breadth (advance-decline ratio on NSE)
   - India VIX levels and implied volatility trends
   - Put-call ratio trends for relevant derivatives

6. **UPCOMING CATALYSTS AND EVENT RISKS**
   - Scheduled economic data releases in the next 1-2 weeks
   - Earning season timeline — which major companies report soon?
   - RBI policy meetings, FOMC meetings, or other central bank events
   - Options expiry dates and their potential impact
   - Any upcoming elections, court verdicts, or policy announcements

Synthesize all of the above into a single JSON response following the \
schema specified in the system prompt. Your "score" should reflect the \
NET sentiment after weighing all factors. Be precise — do not default to \
neutral unless the evidence genuinely points both ways equally.

Remember: Return ONLY the JSON object. No surrounding text.\
"""


def user_prompt_short(symbol: str) -> str:
    """Shorter prompt for the /sentiment/refresh admin endpoint."""
    return (
        f"Analyze the current market sentiment for {symbol} on the Indian "
        f"stock market. Cover news, institutional flows (FII/DII), global "
        f"cues, sector trends, and upcoming catalysts. "
        f"Return your response as a single valid JSON object with keys: "
        f'"score" (float, -1.0 to +1.0), "confidence" (float, 0.0 to 1.0), '
        f'"summary" (string, 2-3 sentences), "headlines" (list of strings), '
        f'"risks" (list of strings), "catalysts" (list of strings). '
        f"No markdown, no code fences — return ONLY the JSON."
    )
