"""
End-to-end test of the AI trading decision pipeline.

Tests:
1. Simple LLM call (ping)
2. Kimi K2.5 reasoning mode
3. Full LangGraph trading decision workflow
4. Trading loop with paper broker (50 synthetic ticks + AI optimization)

Run: source .venv/bin/activate && python tests/test_ai_agent.py
"""

import asyncio
import json
import logging
import os
import sys
import time

# Ensure the src directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Load .env before importing anything else
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_ai")


# ── Color helpers ──────────────────────────────────────────────────────────────

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def pass_msg(msg: str) -> None:
    print(f"{GREEN}✓ PASS{RESET} — {msg}")


def fail_msg(msg: str) -> None:
    print(f"{RED}✗ FAIL{RESET} — {msg}")


def info_msg(msg: str) -> None:
    print(f"{CYAN}→{RESET} {msg}")


def header(msg: str) -> None:
    print(f"\n{BOLD}{'═' * 60}{RESET}")
    print(f"{BOLD}  {msg}{RESET}")
    print(f"{BOLD}{'═' * 60}{RESET}\n")


# ── Test 1: Simple LLM Ping ───────────────────────────────────────────────────

async def test_llm_ping() -> bool:
    """Test that we can reach OpenRouter and get a response."""
    header("Test 1: LLM Ping (Simple Chat)")

    from quantioa.llm.client import chat_simple
    from quantioa.config import settings

    info_msg(f"Model: {settings.ai_model}")
    info_msg(f"API Base: {settings.openrouter_base_url}")
    info_msg(f"API Key: ...{settings.openrouter_api_key[-8:]}")

    t0 = time.time()
    try:
        response = await chat_simple(
            prompt="What is 2+2? Reply in exactly one word.",
            system_prompt="You are a helpful assistant. Be very concise.",
            temperature=0.1,
        )
        elapsed = time.time() - t0

        info_msg(f"Response: {response.strip()}")
        info_msg(f"Latency: {elapsed:.1f}s")

        if response and len(response.strip()) > 0:
            pass_msg(f"LLM responded in {elapsed:.1f}s")
            return True
        else:
            fail_msg("Empty response from LLM")
            return False
    except Exception as e:
        fail_msg(f"LLM call failed: {e}")
        return False


# ── Test 2: Kimi K2.5 Reasoning Mode ──────────────────────────────────────────

async def test_reasoning_mode() -> bool:
    """Test Kimi K2.5's chain-of-thought reasoning."""
    header("Test 2: Kimi K2.5 Reasoning Mode")

    from quantioa.llm.client import chat_with_reasoning

    t0 = time.time()
    try:
        result = await chat_with_reasoning(
            messages=[
                {"role": "system", "content": "You are an expert trader."},
                {
                    "role": "user",
                    "content": (
                        "NIFTY50 RSI is 72, MACD histogram is negative, "
                        "and ATR is expanding. What's the likely direction? "
                        "Reply in 2-3 sentences."
                    ),
                },
            ],
            enable_reasoning=True,
            temperature=0.5,
        )
        elapsed = time.time() - t0

        content = result["content"]
        reasoning = result.get("reasoning_details")
        usage = result.get("usage", {})

        info_msg(f"Content: {content[:200]}...")
        if reasoning:
            info_msg(f"Reasoning details: present ({type(reasoning).__name__})")
        else:
            info_msg("Reasoning details: not returned (model may not support it)")
        info_msg(f"Tokens: {usage.get('prompt_tokens', '?')}→{usage.get('completion_tokens', '?')}")
        info_msg(f"Latency: {elapsed:.1f}s")

        if content and len(content.strip()) > 10:
            pass_msg(f"Reasoning mode works ({elapsed:.1f}s)")
            return True
        else:
            fail_msg("Response too short or empty")
            return False
    except Exception as e:
        fail_msg(f"Reasoning call failed: {e}")
        return False


# ── Test 3: LangGraph Workflow ─────────────────────────────────────────────────

async def test_langgraph_workflow() -> bool:
    """Run the full 5-node LangGraph trading decision pipeline."""
    header("Test 3: LangGraph Trading Decision Pipeline")

    from quantioa.llm.workflows import build_trading_decision_graph

    initial_state = {
        "symbol": "NIFTY50",
        "indicators": {
            "rsi": 68.5,
            "macd_hist": -0.002,
            "macd_line": 0.015,
            "macd_signal": 0.017,
            "atr": 157.3,
            "ema_9": 22100.0,
            "ema_21": 22050.0,
            "sma_20": 22080.0,
            "sma_50": 21950.0,
        },
        "current_params": {
            "stop_loss_pct": 2.0,
            "kelly_fraction": 0.25,
            "min_confidence": 0.6,
            "atr_multiplier": 2.0,
        },
        "recent_performance": {
            "win_rate": 0.58,
            "sharpe_ratio": 1.2,
            "max_drawdown": 0.04,
            "avg_win_loss_ratio": 1.6,
            "total_trades": 47,
        },
        "retry_count": 0,
    }

    info_msg("Running 5-node pipeline: analyze → optimize → sentiment → validate → signal")
    info_msg(f"Input: RSI={initial_state['indicators']['rsi']}, "
             f"MACD hist={initial_state['indicators']['macd_hist']}, "
             f"Win rate={initial_state['recent_performance']['win_rate']:.0%}")

    t0 = time.time()
    try:
        graph = build_trading_decision_graph()
        result = await graph.ainvoke(initial_state)
        elapsed = time.time() - t0

        signal = result.get("final_signal", "???")
        confidence = result.get("confidence", 0.0)
        reasoning = result.get("reasoning", "")
        error = result.get("error")

        info_msg(f"Signal: {BOLD}{signal}{RESET}")
        info_msg(f"Confidence: {confidence:.0%}")
        info_msg(f"Sentiment Score: {result.get('sentiment_score', 'N/A')}")

        if error:
            info_msg(f"{YELLOW}Warning:{RESET} {error}")

        print(f"\n{CYAN}AI Reasoning:{RESET}")
        for line in reasoning.split("\n")[:6]:
            print(f"  {line}")
        if len(reasoning.split("\n")) > 6:
            print(f"  ... ({len(reasoning)} chars total)")

        info_msg(f"Total pipeline time: {elapsed:.1f}s")

        if signal in ("BUY", "SELL", "HOLD"):
            pass_msg(f"Pipeline completed → {signal} ({confidence:.0%}) in {elapsed:.1f}s")
            return True
        else:
            fail_msg(f"Unexpected signal: {signal}")
            return False
    except Exception as e:
        fail_msg(f"LangGraph pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# ── Test 4: Trading Loop with Paper Broker ─────────────────────────────────────

async def test_trading_loop() -> bool:
    """Run the trading loop on synthetic tick data with paper broker."""
    header("Test 4: Trading Loop (Paper Broker + 50 Ticks)")

    from quantioa.broker.paper_adapter import PaperTradingAdapter
    from quantioa.data.sample_data import generate_ticks
    from quantioa.engine.trading_loop import TradingLoop

    broker = PaperTradingAdapter(initial_capital=100_000)
    await broker.connect()

    loop = TradingLoop(
        broker=broker,
        capital=100_000,
        symbol="NIFTY50",
        trade_quantity=1,
        min_confidence=0.45,
    )

    ticks = generate_ticks(symbol="NIFTY50", start_price=22150.0, n=50)
    info_msg(f"Processing {len(ticks)} synthetic ticks...")

    entries, exits, stops = 0, 0, 0
    t0 = time.time()

    for i, tick in enumerate(ticks):
        result = await loop.process_tick(tick)
        action = result.get("action", "HOLD")
        if action == "ENTRY":
            entries += 1
        elif action == "EXIT":
            exits += 1
        elif action == "STOPPED":
            stops += 1

    elapsed = time.time() - t0

    print(f"\n{loop.summary()}\n")
    balance = await broker.get_account_balance()
    info_msg(f"Final balance: ₹{balance:,.2f}")
    info_msg(f"Elapsed: {elapsed:.2f}s")

    if loop.stats.ticks_processed == 50:
        pass_msg(f"Trading loop completed: {entries} entries, {exits} exits, {stops} stops")
        return True
    else:
        fail_msg(f"Only processed {loop.stats.ticks_processed}/50 ticks")
        return False


# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║   Quantioa AI Trading Agent — End-to-End Test Suite      ║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════╝{RESET}")

    results = {}

    # Test 1: Basic connectivity
    results["LLM Ping"] = await test_llm_ping()

    # Test 2: Reasoning mode
    if results["LLM Ping"]:
        results["Reasoning Mode"] = await test_reasoning_mode()
    else:
        info_msg("Skipping Test 2 (LLM ping failed)")
        results["Reasoning Mode"] = False

    # Test 3: Full LangGraph pipeline
    if results["LLM Ping"]:
        results["LangGraph Pipeline"] = await test_langgraph_workflow()
    else:
        info_msg("Skipping Test 3 (LLM ping failed)")
        results["LangGraph Pipeline"] = False

    # Test 4: Trading loop (doesn't need LLM)
    results["Trading Loop"] = await test_trading_loop()

    # Summary
    header("Results")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        status = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  {status}  {name}")

    print(f"\n  {BOLD}{passed}/{total} tests passed{RESET}\n")

    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
