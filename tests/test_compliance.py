"""
Tests for the SEBI compliance infrastructure.

Tests cover:
- Audit trail logger
- Algo ID registry + order tagging
- OPS rate monitor
- KYC workflow
- AI disclosure consent
- Kill switch (global/user/algo)
- Research report generator
"""

from __future__ import annotations

import time
import uuid

import pytest

# ── Pure-logic modules (no DB required) ──────────────────────────────────────

from quantioa.compliance.algo_registry import (
    AlgoRegistry,
    AlgoStatus,
    AlgoType,
)
from quantioa.compliance.kill_switch import KillSwitch
from quantioa.compliance.rate_monitor import RateMonitor
from quantioa.compliance.research_report import ReportGenerator


# ── Algo Registry Tests ──────────────────────────────────────────────────────


class TestAlgoRegistry:
    def setup_method(self):
        self.registry = AlgoRegistry()

    def test_register_algo(self):
        reg = self.registry.register_algo(
            strategy_id="momentum_v1",
            description="RSI + MACD momentum",
        )
        assert reg.strategy_id == "momentum_v1"
        assert reg.algo_id.startswith("QTA-")
        assert len(reg.algo_id) == 16  # QTA- + 12 hex chars
        assert reg.algo_type == AlgoType.HYBRID

    def test_deterministic_algo_id(self):
        """Same strategy+exchange+version should produce same algo_id."""
        r1 = self.registry.register_algo(strategy_id="strat_a", exchange="NSE")
        r2 = self.registry.register_algo(strategy_id="strat_a", exchange="NSE")
        assert r1.algo_id == r2.algo_id

    def test_different_versions_different_ids(self):
        r1 = self.registry.register_algo(strategy_id="strat_b", version="1.0")
        r2 = self.registry.register_algo(strategy_id="strat_b", version="2.0")
        # Different versions produce different registrations
        assert r1.algo_id != r2.algo_id

    def test_get_algo(self):
        self.registry.register_algo(strategy_id="test_strat")
        assert self.registry.get_algo("test_strat") is not None
        assert self.registry.get_algo("nonexistent") is None

    def test_get_algo_id(self):
        self.registry.register_algo(strategy_id="id_test")
        assert self.registry.get_algo_id("id_test").startswith("QTA-")
        assert self.registry.get_algo_id("nonexistent") == ""

    def test_tag_order(self):
        self.registry.register_algo(strategy_id="tag_test")
        order = {"symbol": "RELIANCE", "side": "BUY", "qty": 10}
        tagged = self.registry.tag_order(order, strategy_id="tag_test")
        assert "algo_id" in tagged
        assert tagged["algo_id"].startswith("QTA-")
        assert tagged["strategy_id"] == "tag_test"

    def test_tag_order_unregistered(self):
        order = {"symbol": "INFY", "side": "SELL"}
        tagged = self.registry.tag_order(order, strategy_id="unknown")
        assert tagged["algo_id"] == ""

    def test_suspend_resume(self):
        self.registry.register_algo(strategy_id="suspend_test")
        assert self.registry.is_algo_active("suspend_test") is True

        assert self.registry.suspend_algo("suspend_test") is True
        assert self.registry.is_algo_active("suspend_test") is False
        assert self.registry.get_algo("suspend_test").status == AlgoStatus.SUSPENDED

        assert self.registry.resume_algo("suspend_test") is True
        assert self.registry.is_algo_active("suspend_test") is True

    def test_suspend_nonexistent(self):
        assert self.registry.suspend_algo("nonexistent") is False

    def test_list_algos(self):
        self.registry.register_algo(strategy_id="list_a")
        self.registry.register_algo(strategy_id="list_b")
        algos = self.registry.list_algos()
        assert len(algos) == 2


# ── Kill Switch Tests ────────────────────────────────────────────────────────


class TestKillSwitch:
    def setup_method(self):
        self.ks = KillSwitch()

    def test_initially_not_halted(self):
        assert self.ks.is_trading_halted() is False
        assert self.ks.get_halt_reason() is None

    def test_global_halt(self):
        self.ks.activate_global(reason="Market crash")
        assert self.ks.is_trading_halted() is True
        assert "GLOBAL" in self.ks.get_halt_reason()
        assert "Market crash" in self.ks.get_halt_reason()

        self.ks.deactivate_global()
        assert self.ks.is_trading_halted() is False

    def test_user_halt(self):
        uid = str(uuid.uuid4())
        other_uid = str(uuid.uuid4())

        self.ks.activate_user(uid, reason="Loss limit breach")
        assert self.ks.is_trading_halted(user_id=uid) is True
        assert self.ks.is_trading_halted(user_id=other_uid) is False
        assert self.ks.is_trading_halted() is False  # Global is fine

        self.ks.deactivate_user(uid)
        assert self.ks.is_trading_halted(user_id=uid) is False

    def test_algo_halt(self):
        self.ks.activate_algo("momentum_v1", reason="Anomalous behavior")
        assert self.ks.is_trading_halted(strategy_id="momentum_v1") is True
        assert self.ks.is_trading_halted(strategy_id="other_strat") is False

        self.ks.deactivate_algo("momentum_v1")
        assert self.ks.is_trading_halted(strategy_id="momentum_v1") is False

    def test_global_overrides_all(self):
        """Global halt should affect all users and algos."""
        uid = str(uuid.uuid4())
        self.ks.activate_global(reason="Maintenance")
        assert self.ks.is_trading_halted(user_id=uid) is True
        assert self.ks.is_trading_halted(strategy_id="any_strat") is True

    def test_status_report(self):
        uid = str(uuid.uuid4())
        self.ks.activate_global(reason="Test")
        self.ks.activate_user(uid, reason="Breach")
        self.ks.activate_algo("strat1", reason="Bug")

        status = self.ks.status()
        assert status["global_halt"] is True
        assert status["total_halts"] == 3
        assert uid in status["user_halts"]
        assert "strat1" in status["algo_halts"]


# ── Rate Monitor Tests ───────────────────────────────────────────────────────


class TestRateMonitor:
    def setup_method(self):
        self.monitor = RateMonitor(max_ops=5)  # Low limit for testing

    def test_normal_rate(self):
        uid = str(uuid.uuid4())
        assert self.monitor.check_and_record(uid) is True

    def test_exceeds_limit(self):
        uid = str(uuid.uuid4())
        # Place 5 orders (at limit)
        for _ in range(5):
            self.monitor.check_and_record(uid)

        # 6th should exceed
        result = self.monitor.check_and_record(uid)
        assert result is False

    def test_per_user_isolation(self):
        uid1 = str(uuid.uuid4())
        uid2 = str(uuid.uuid4())

        for _ in range(5):
            self.monitor.check_and_record(uid1)

        # User 2 should still be fine
        assert self.monitor.check_and_record(uid2) is True

    def test_stats(self):
        uid = str(uuid.uuid4())
        for _ in range(3):
            self.monitor.check_and_record(uid, strategy_id="strat_a")

        stats = self.monitor.get_user_stats(uid)
        assert stats["total_orders"] == 3
        assert stats["violations"] == 0

    def test_strategy_stats(self):
        uid = str(uuid.uuid4())
        self.monitor.check_and_record(uid, strategy_id="strat_x")
        self.monitor.check_and_record(uid, strategy_id="strat_x")

        stats = self.monitor.get_strategy_stats(uid, "strat_x")
        assert stats["total_orders"] == 2

    def test_approaching_limit(self):
        uid = str(uuid.uuid4())
        # 80% of 5 = 4
        for _ in range(4):
            self.monitor.check_and_record(uid)
        assert self.monitor.approaching_limit(uid) is True

    def test_reset_user(self):
        uid = str(uuid.uuid4())
        for _ in range(3):
            self.monitor.check_and_record(uid, strategy_id="s1")
        self.monitor.reset_user(uid)
        stats = self.monitor.get_user_stats(uid)
        assert stats["total_orders"] == 0

    def test_violations_tracked(self):
        uid = str(uuid.uuid4())
        for _ in range(7):  # 5 okay, 2 violations
            self.monitor.check_and_record(uid)
        stats = self.monitor.get_user_stats(uid)
        assert stats["violations"] == 2


# ── Research Report Tests ────────────────────────────────────────────────────


class TestResearchReport:
    def setup_method(self):
        self.gen = ReportGenerator()

    def test_basic_report(self):
        report = self.gen.generate_strategy_report(
            strategy_id="test_strat",
            strategy_name="Test Strategy",
        )
        assert "# Strategy Research Report: Test Strategy" in report
        assert "`test_strat`" in report
        assert "AI / Machine Learning Disclosure" in report
        assert "Risk Disclosure" in report
        assert "Regulatory Compliance" in report

    def test_report_with_indicators(self):
        report = self.gen.generate_strategy_report(
            strategy_id="ind_strat",
            strategy_name="Indicator Strategy",
            indicators=["RSI(14)", "MACD(12,26,9)"],
        )
        assert "RSI(14)" in report
        assert "MACD(12,26,9)" in report

    def test_report_with_risk_params(self):
        report = self.gen.generate_strategy_report(
            strategy_id="risk_strat",
            strategy_name="Risk Strategy",
            risk_params={"stop_loss_pct": 2.0, "max_daily_loss_pct": 2.0},
        )
        assert "Stop Loss Pct" in report
        assert "2.0" in report

    def test_report_with_performance(self):
        report = self.gen.generate_strategy_report(
            strategy_id="perf_strat",
            strategy_name="Perf Strategy",
            performance={"win_rate": 0.62, "sharpe_ratio": 1.4},
        )
        assert "Historical Performance" in report
        assert "62.0%" in report
        assert "1.40" in report

    def test_report_sebi_references(self):
        report = self.gen.generate_strategy_report(
            strategy_id="sebi_strat",
            strategy_name="SEBI Strategy",
        )
        assert "SEBI/HO/MIRSD" in report
        assert "5-year retention" in report


# ── KYC Validation Tests (pure logic, no DB) ────────────────────────────────


class TestKYCValidation:
    def test_valid_pan(self):
        from quantioa.compliance.kyc import KYCManager

        mgr = KYCManager()
        assert mgr.validate_pan("ABCDE1234F") is True
        assert mgr.validate_pan("ZZZZZ9999Z") is True

    def test_invalid_pan(self):
        from quantioa.compliance.kyc import KYCManager

        mgr = KYCManager()
        assert mgr.validate_pan("12345") is False
        assert mgr.validate_pan("ABC") is False
        assert mgr.validate_pan("ABCDE12345") is False  # 5 digits
        assert mgr.validate_pan("abcde1234f") is True  # normalized to uppercase
        assert mgr.validate_pan("") is False

    def test_kyc_required(self):
        from quantioa.compliance.kyc import KYCManager

        mgr = KYCManager()
        assert mgr.is_kyc_required_for_trading() is True


# ── Consent Tests (pure logic, no DB) ────────────────────────────────────────


class TestConsentText:
    def test_disclosure_text(self):
        from quantioa.compliance.consent import ConsentManager

        mgr = ConsentManager()
        text = mgr.get_disclosure_text()
        assert "AI-POWERED SIGNALS" in text
        assert "NON-DETERMINISTIC" in text
        assert "KILL SWITCH" in text.upper() or "kill switch" in text.lower()
        assert "5-year retention" in text.lower()

    def test_consent_required(self):
        from quantioa.compliance.consent import ConsentManager

        mgr = ConsentManager()
        assert mgr.is_consent_required_for_trading() is True


# ── Audit Logger Action Constants ────────────────────────────────────────────


class TestAuditConstants:
    def test_action_constants_exist(self):
        from quantioa.compliance.audit_log import (
            ACTION_BROKER_CONNECTED,
            ACTION_KILL_SWITCH_ACTIVATED,
            ACTION_KYC_VERIFIED,
            ACTION_LOGIN,
            ACTION_REGISTER,
            ACTION_TRADE_PLACED,
        )

        assert ACTION_REGISTER == "REGISTER"
        assert ACTION_LOGIN == "LOGIN"
        assert ACTION_TRADE_PLACED == "TRADE_PLACED"
        assert ACTION_KYC_VERIFIED == "KYC_VERIFIED"
        assert ACTION_BROKER_CONNECTED == "BROKER_CONNECTED"
        assert ACTION_KILL_SWITCH_ACTIVATED == "KILL_SWITCH_ACTIVATED"


# ── Pre-Trade Compliance Gate Tests ──────────────────────────────────────────


class TestPreTradeCheck:
    def setup_method(self):
        """Fresh instances for each test."""
        from quantioa.compliance import pre_trade as pt

        # Reset singletons
        pt.kill_switch._global_halt = None
        pt.kill_switch._user_halts.clear()
        pt.kill_switch._algo_halts.clear()
        pt.rate_monitor._user_windows.clear()
        pt.rate_monitor._strategy_windows.clear()
        pt.algo_registry._registry.clear()

        self.uid = str(uuid.uuid4())
        self.strat = "test_strategy"

        # Register the algo so it passes registration check
        pt.algo_registry.register_algo(strategy_id=self.strat)

    def test_allowed_when_all_clear(self):
        from quantioa.compliance.pre_trade import pre_trade_check

        result = pre_trade_check(self.uid, strategy_id=self.strat)
        assert result.allowed is True
        assert result.algo_id.startswith("QTA-")

    def test_blocked_by_global_kill_switch(self):
        from quantioa.compliance.pre_trade import pre_trade_check
        from quantioa.compliance.kill_switch import kill_switch

        kill_switch.activate_global(reason="Market crash")
        result = pre_trade_check(self.uid, strategy_id=self.strat)
        assert result.allowed is False
        assert "Kill switch" in result.reason

    def test_blocked_by_user_kill_switch(self):
        from quantioa.compliance.pre_trade import pre_trade_check
        from quantioa.compliance.kill_switch import kill_switch

        kill_switch.activate_user(self.uid, reason="Loss limit")
        result = pre_trade_check(self.uid, strategy_id=self.strat)
        assert result.allowed is False
        assert "Kill switch" in result.reason

    def test_blocked_by_ops_limit(self):
        from quantioa.compliance.pre_trade import pre_trade_check
        from quantioa.compliance.rate_monitor import rate_monitor

        # Exhaust the limit
        for _ in range(rate_monitor.max_ops + 1):
            rate_monitor.check_and_record(self.uid)

        result = pre_trade_check(self.uid, strategy_id=self.strat)
        assert result.allowed is False
        assert "OPS limit" in result.reason

    def test_blocked_by_unregistered_algo(self):
        from quantioa.compliance.pre_trade import pre_trade_check

        result = pre_trade_check(self.uid, strategy_id="unregistered_strat")
        assert result.allowed is False
        assert "not registered" in result.reason

    def test_blocked_by_suspended_algo(self):
        from quantioa.compliance.pre_trade import pre_trade_check
        from quantioa.compliance.algo_registry import algo_registry

        algo_registry.suspend_algo(self.strat)
        result = pre_trade_check(self.uid, strategy_id=self.strat)
        assert result.allowed is False
        assert "suspended" in result.reason

    def test_no_strategy_skips_algo_check(self):
        from quantioa.compliance.pre_trade import pre_trade_check

        result = pre_trade_check(self.uid)
        assert result.allowed is True
        assert result.algo_id == ""


# ── Package Import Test ──────────────────────────────────────────────────────


class TestPackageImports:
    def test_convenience_imports(self):
        from quantioa.compliance import (
            algo_registry,
            audit_logger,
            consent_manager,
            kill_switch,
            kyc_manager,
            rate_monitor,
            report_generator,
        )

        assert audit_logger is not None
        assert algo_registry is not None
        assert rate_monitor is not None
        assert kill_switch is not None
        assert consent_manager is not None
        assert kyc_manager is not None
        assert report_generator is not None
