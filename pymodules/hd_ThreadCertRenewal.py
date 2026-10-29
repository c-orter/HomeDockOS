"""
hd_ThreadCertRenewal.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import time
import threading

from datetime import datetime, timezone

from pymodules.hd_CertManager import renew_if_needed, renewal_status
from pymodules.hd_CertScheduler import record_failure, record_success, retry_delay, start_domain_change_listener

# HDOS00071
CHECK_INTERVAL = 12 * 60 * 60

INITIAL_DELAY = 120

_last = {"error": None, "checked_at": None}


def get_last_renewal_error():
    return _last["error"]


def _tick():
    _last["checked_at"] = datetime.now(timezone.utc).isoformat()

    try:
        result = renew_if_needed()
    except Exception as error:
        _last["error"] = str(error)
        delay = record_failure(error)
        print(f" ! THREAD: Certificate renewal failed, the current certificate keeps serving; next try in {delay // 60} minute(s): {error}")
        return

    _last["error"] = None
    record_success()

    if result:
        print(f" + THREAD: Certificate renewed for {result['domains'][0]}")


def start_cert_renewal_thread():
    status = renewal_status()

    if not status["managed"]:
        print(f" * Certificate renewal: not managed here ({status['reason']})")

    start_domain_change_listener()

    def loop():
        time.sleep(INITIAL_DELAY)

        while True:
            _tick()
            time.sleep(retry_delay(CHECK_INTERVAL))

    threading.Thread(target=loop, daemon=True, name="hdos-cert-renewal").start()
