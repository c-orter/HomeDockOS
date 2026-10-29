"""
hd_AcmeChallenges.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import re
import threading

PREFIX = "/.well-known/acme-challenge/"

_TOKEN = re.compile(r"[A-Za-z0-9_-]{16,128}")

_lock = threading.Lock()
_answers = {}


def publish(token, key_authorization):
    with _lock:
        _answers[token] = key_authorization


def withdraw(token):
    with _lock:
        _answers.pop(token, None)


def lookup(path):
    """The key authorization to serve for a request path, or None when it is not a pending challenge."""

    if not path.startswith(PREFIX):
        return None

    token = path[len(PREFIX):]

    if not _TOKEN.fullmatch(token):
        return None

    with _lock:
        return _answers.get(token)
