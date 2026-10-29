"""
hd_CertScheduler.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import threading

from datetime import datetime, timedelta, timezone

from pymodules.hd_FunctionsConfig import read_config
from pymodules.hd_FunctionsNativeSSL import get_cert_domains_and_type
from pymodules.hd_ACMEClient import ACMEError
from pymodules.hd_CertManager import renewal_status, issue_certificate, get_state
from pymodules.hd_CertPlan import plan_names
from pymodules.hd_DomainStore import on_names_changed

# edits made inside this window are folded into one order
REISSUE_DELAY = 60

# Let's Encrypt allows 5 failed validations per name per hour, so the first retry waits an hour
BACKOFF_BASE = 60 * 60
BACKOFF_CAP = 24 * 60 * 60

_lock = threading.Lock()

_state = {"timer": None, "failures": 0, "last_error": None, "next_attempt": None, "reissue_at": None}


def backoff_delay(failures):
    """Seconds to wait after this many failures in a row: 1h, 2h, 4h ... capped at a day."""

    if failures <= 0:
        return 0

    return min(BACKOFF_BASE * 2 ** (failures - 1), BACKOFF_CAP)


def record_success():
    with _lock:
        _state.update(failures=0, last_error=None, next_attempt=None)


def record_failure(error):
    """Counts a failure and returns how many seconds to wait before the next try."""

    with _lock:
        _state["failures"] += 1
        _state["last_error"] = str(error)

        delay = backoff_delay(_state["failures"])
        _state["next_attempt"] = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()

        return delay


def retry_delay(default):
    """How long the renewal loop sleeps: its normal interval, or the backoff while failing."""

    with _lock:
        failures = _state["failures"]

    return backoff_delay(failures) if failures else default


def get_schedule_state():
    with _lock:
        return {key: _state[key] for key in ("failures", "last_error", "next_attempt", "reissue_at")}


def schedule_reissue(delay=REISSUE_DELAY):
    """Plans one order for `delay` seconds from now; more edits before it fires join that same order."""

    with _lock:
        if _state["timer"] is not None:
            return False

        timer = threading.Timer(delay, _fire)
        timer.daemon = True
        _state["timer"] = timer
        _state["reissue_at"] = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()

    timer.start()

    return True


def _fire():
    with _lock:
        _state["timer"] = None
        _state["reissue_at"] = None

    run_reissue()


def run_reissue(log=print):
    """Re-orders the certificate when the wanted names differ from the ones on it. Returns what happened."""

    status = renewal_status()

    if not status["managed"]:
        return "skipped"

    if get_state()["running"]:
        schedule_reissue()
        return "busy"

    plan = plan_names(status["domain"])
    current = {name.strip().lower() for name in get_cert_domains_and_type().get("domains", [])}

    if set(plan["covered"]) == current:
        return "unchanged"

    log(f" * ACME: domain list changed, reissuing {status['domain']}")

    try:
        issue_certificate(status["domain"], plan=plan, log=log)
    except ACMEError as error:
        # the previous certificate keeps serving; it is only replaced after a whole order succeeds
        delay = record_failure(error)
        log(f" ! ACME: reissue failed, trying again in {delay // 60} minute(s): {error}")
        schedule_reissue(delay)
        return "failed"

    record_success()

    return "issued"


def start_domain_change_listener():
    on_names_changed(schedule_reissue)
