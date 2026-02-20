"""
SEBI Compliance Infrastructure for Quantioa.

This package provides all regulatory compliance modules required
for operating an algorithmic trading platform under SEBI regulations.

Quick import::

    from quantioa.compliance import (
        audit_logger,
        algo_registry,
        rate_monitor,
        kill_switch,
        consent_manager,
        kyc_manager,
        report_generator,
    )
"""

from quantioa.compliance.algo_registry import algo_registry
from quantioa.compliance.audit_log import audit_logger
from quantioa.compliance.consent import consent_manager
from quantioa.compliance.kill_switch import kill_switch
from quantioa.compliance.kyc import kyc_manager
from quantioa.compliance.rate_monitor import rate_monitor
from quantioa.compliance.research_report import report_generator

__all__ = [
    "audit_logger",
    "algo_registry",
    "rate_monitor",
    "kill_switch",
    "consent_manager",
    "kyc_manager",
    "report_generator",
]
