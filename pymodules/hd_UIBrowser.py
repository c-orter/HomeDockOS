"""
hd_UIBrowser.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import asyncio
import re
import secrets
import threading
import time

from flask import jsonify, request
from flask_login import current_user, login_required

from pymodules import hd_BrowserAllowlist as allowlist
from pymodules import hd_BrowserRuntime as runtime
from pymodules import hd_BrowserSettings as settings
from pymodules import hd_BrowserTransfer as transfer
from pymodules import hd_SubdomainRouter as router
from pymodules.hd_SubdomainRouter import HOP_BY_HOP_HEADERS, _get_session, _get_uncapped_session, _pump_backend_to_client, _pump_client_to_backend, _send_simple_response, _stream_request_body

ROUTE_PREFIX = "/browser/"

# A ticket lives while the open window keeps renewing it. A window that closes stops renewing, so the ticket dies within this many seconds.
TICKET_TTL = 120
TICKET_WATCH_INTERVAL = 2

_ROUTE_RE = re.compile(r"^/browser/([A-Za-z0-9_-]{20,64})(/.*)?$")

# The client runs in an iframe without allow-same-origin. The same sandbox goes on every relayed response, so the page stays opaque even when its address is opened on its own.
SANDBOX_POLICY = "sandbox allow-scripts allow-forms allow-pointer-lock allow-downloads allow-popups"

# Without allow-same-origin the page cannot touch localStorage or sessionStorage, and Selkies' client throws while starting. These in-memory stand-ins go in ahead of its scripts, so nothing is stored and nothing of HomeDock's is reachable.
_STORAGE_SHIM = b"(function(){function s(){var d={};return{get length(){return Object.keys(d).length},key:function(i){var k=Object.keys(d)[i];return k===undefined?null:k},getItem:function(k){return Object.prototype.hasOwnProperty.call(d,k)?d[k]:null},setItem:function(k,v){d[String(k)]=String(v)},removeItem:function(k){delete d[k]},clear:function(){d={}}}}[\"localStorage\",\"sessionStorage\"].forEach(function(n){try{Object.defineProperty(window,n,{value:s(),configurable:true})}catch(e){}})})()"
# Audio starts muted. Every Web Audio node that reaches the speakers goes through one master gain, and media elements are muted the same way, so the window's mute button (a message from the parent page, never from the stream) is the only switch. The first unmute is the user's click in the window, which also lets the page's audio start.
_AUDIO_SHIM = b"""(function(){var muted=true,masters=[],contexts=[];var proto=window.AudioNode&&AudioNode.prototype;if(proto){var connect=proto.connect;var byContext=typeof WeakMap==="function"?new WeakMap():null;function masterFor(ctx){var m=byContext&&byContext.get(ctx);if(!m){m=ctx.createGain();m.gain.value=muted?0:1;connect.call(m,ctx.destination);if(byContext)byContext.set(ctx,m);masters.push(m);contexts.push(ctx)}return m}proto.connect=function(dest){if(dest&&dest.context&&dest===dest.context.destination&&byContext&&this!==byContext.get(this.context)){var rest=[].slice.call(arguments,1);connect.apply(this,[masterFor(this.context)].concat(rest));return dest}return connect.apply(this,arguments)}}function media(){var els=document.querySelectorAll("audio,video");for(var i=0;i<els.length;i++)els[i].muted=muted}addEventListener("play",function(e){if(e.target&&e.target.muted!==undefined&&muted)e.target.muted=true},true);addEventListener("message",function(e){var d=e.data;if(e.source!==parent||!d||d.type!=="hd-audio")return;muted=!!d.muted;masters.forEach(function(g){g.gain.value=muted?0:1});media();if(!muted)contexts.forEach(function(c){try{c.resume()}catch(x){}})})})()"""
_SHIM_TAG = b"<script>" + _STORAGE_SHIM + b";" + _AUDIO_SHIM + b"</script>"
_HEAD_OPEN_RE = re.compile(rb"<head\b[^>]*>", re.IGNORECASE)
_MAX_DOCUMENT = 1024 * 1024

_STRIPPED_REQUEST_HEADERS = HOP_BY_HOP_HEADERS | {"host", "cookie", "authorization", "origin", "referer", "content-length", "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol"}
_STRIPPED_RESPONSE_HEADERS = HOP_BY_HOP_HEADERS | {"set-cookie", "content-length", "content-security-policy", "x-frame-options", "cross-origin-resource-policy", "cross-origin-opener-policy", "cross-origin-embedder-policy"} | {"access-control-allow-origin", "access-control-allow-credentials", "access-control-allow-methods", "access-control-allow-headers", "access-control-expose-headers"}

_tickets = {}
_tickets_lock = threading.Lock()


def _prune(now):
    for key in [key for key, entry in _tickets.items() if entry["expires"] < now]:
        _tickets.pop(key, None)


def issue_ticket(operator, ip):
    """Mints a ticket. Only one stream is live at a time, so every older ticket is displaced: it keeps counting as an open window but no longer carries the stream."""

    ticket = secrets.token_urlsafe(32)
    now = time.monotonic()

    with _tickets_lock:
        _prune(now)

        for entry in _tickets.values():
            entry["displaced"] = True

        _tickets[ticket] = {"expires": now + TICKET_TTL, "operator": operator, "ip": ip, "displaced": False}

    return ticket


def release_ticket(ticket):
    with _tickets_lock:
        return _tickets.pop(ticket, None) is not None


def ticket_live(ticket):
    """Alive and not displaced: the one ticket allowed to carry the stream."""

    with _tickets_lock:
        entry = _tickets.get(ticket)

        return entry is not None and entry["expires"] >= time.monotonic() and not entry["displaced"]


def open_sessions():
    """How many windows are attached, displaced ones included."""

    with _tickets_lock:
        _prune(time.monotonic())

        return len(_tickets)


def renew_ticket(ticket):
    """Extends a live ticket and returns its entry, or None when it is unknown or expired."""

    if not ticket:
        return None

    now = time.monotonic()

    with _tickets_lock:
        entry = _tickets.get(ticket)

        if entry is None or entry["expires"] < now:
            _tickets.pop(ticket, None)
            return None

        entry["expires"] = now + TICKET_TTL

        return entry


def ticket_alive(ticket):
    with _tickets_lock:
        entry = _tickets.get(ticket)

        return entry is not None and entry["expires"] >= time.monotonic()


def revoke_tickets():
    with _tickets_lock:
        _tickets.clear()


IDLE_CHECK_INTERVAL = 15
TRANSFER_INTERVAL = 3

_idle = {"since": None, "thread": None}
_idle_lock = threading.Lock()


def idle_timeout_seconds():
    """Read on every check, so a changed setting applies without a restart."""

    return settings.load()["idle_minutes"] * 60


def idle_tick(now=None):
    """One look at the browser. Stops it once it has had no open window for the idle timeout, and never while a download is running. Returns True when it stopped it."""

    now = time.monotonic() if now is None else now

    if runtime.status()["phase"] != "running" or open_sessions() > 0:
        _idle["since"] = None
        return False

    if _idle["since"] is None:
        _idle["since"] = now
        return False

    if now - _idle["since"] < idle_timeout_seconds():
        return False

    if runtime.downloading():
        return False

    runtime.stop()
    revoke_tickets()
    _idle["since"] = None

    return True


def transfer_tick():
    """Moves finished downloads into the dropzone. Returns how many moved."""

    container = runtime.running_container()

    if container is None:
        transfer.reset_previous()
        return 0

    from pymodules.hd_FunctionsConfig import read_config

    username = str(read_config().get("user_name", "")).lower()

    return transfer.sync_downloads(container, runtime.engine().download_dir, username) if username else 0


def _idle_loop():
    ticks = 0

    while True:
        time.sleep(TRANSFER_INTERVAL)
        ticks += 1

        try:
            transfer_tick()
        except Exception as e:
            print(f" ! Browser download sync failed: {type(e).__name__}: {e}")

        if ticks % (IDLE_CHECK_INTERVAL // TRANSFER_INTERVAL) == 0:
            try:
                idle_tick()
            except Exception as e:
                print(f" ! Browser idle check failed: {type(e).__name__}: {e}")


def start_idle_monitor():
    with _idle_lock:
        if _idle["thread"] is not None:
            return

        _idle["thread"] = threading.Thread(target=_idle_loop, name="hd-browser-idle", daemon=True)
        _idle["thread"].start()


@login_required
def api_browser_status():
    return jsonify({**runtime.status(), "success": True})


@login_required
def api_browser_start():
    if not runtime.docker_available():
        return jsonify({**runtime.status(), "success": False}), 503

    runtime.start()

    return jsonify({**runtime.status(), "success": True})


@login_required
def api_browser_stop():
    runtime.stop()
    revoke_tickets()

    return jsonify({**runtime.status(), "success": True})


@login_required
def api_browser_session():
    state = runtime.status()

    if state["phase"] != "running":
        return jsonify({**state, "success": False, "code": "not_running"}), 409

    ticket = issue_ticket(current_user.get_id(), request.remote_addr)

    if _username():
        threading.Thread(target=_push_uploads_quietly, args=(_username(),), name="hd-browser-uploads", daemon=True).start()

    return jsonify({"success": True, "ticket": ticket, "path": f"{ROUTE_PREFIX}{ticket}/", "ttl": TICKET_TTL})


def _username():
    return str(current_user.get_id() or "").lower()


def _push_uploads_quietly(username):
    try:
        container = runtime.running_container()

        if container is not None:
            transfer.push_uploads(container, username)
    except Exception as e:
        print(f" ! Browser upload folder failed: {type(e).__name__}: {e}")


@login_required
def api_browser_files_refresh():
    """Makes the files now in the dropzone's Browser folder available to the browser's file dialog."""

    container = runtime.running_container()

    if container is None:
        return jsonify({"success": False, "code": "not_running"}), 409

    try:
        count = transfer.push_uploads(container, _username())
    except Exception as e:
        return jsonify({"success": False, "code": "upload_failed", "detail": str(e)}), 500

    return jsonify({"success": True, "count": count, "notices": transfer.notices_after(0)})


def _image_status():
    engine = runtime.engine()

    try:
        present = engine.has_image(runtime._client())
    except Exception:
        present = False

    return {"reference": engine.image_reference(), "base": engine.base_reference(), "present": present}


def _requires_2fa():
    from pymodules.hd_FunctionsConfig import read_config

    try:
        return bool(read_config().get("2fa_enabled"))
    except Exception:
        return False


def _settings_payload():
    return {
        "success": True,
        "requires_2fa": _requires_2fa(),
        "settings": settings.load(),
        "defaults": settings.DEFAULTS,
        "ranges": {field: list(bounds) for field, bounds in settings.RANGES.items()},
        "allowlist": allowlist.entries(),
        "image": _image_status(),
        "running": runtime.running_container() is not None,
    }


@login_required
def api_browser_settings():
    return jsonify(_settings_payload())


@login_required
def api_browser_settings_save():
    """Applies on the next start of the browser, except the idle timeout, which is read as it counts down."""

    try:
        values = settings.save(request.get_json(silent=True))
    except settings.SettingsError as e:
        return jsonify({"success": False, "field": e.field, "error": e.message}), 400

    return jsonify({**_settings_payload(), "settings": values})


def _fresh_auth(payload):
    """The same bar as the host shell: the password again, and a 2FA code when 2FA is on. Returns an error response, or None when it passed."""

    from pymodules import hd_HostShell as host_shell

    try:
        host_shell.authorize(request.remote_addr, payload.get("password"), payload.get("code"))
    except host_shell.HostShellError as e:
        return jsonify({"success": False, "code": e.code}), e.status

    return None


def _json_object():
    payload = request.get_json(silent=True)

    return payload if isinstance(payload, dict) else {}


def _refresh_proxy_quietly():
    try:
        runtime.refresh_proxy()
    except Exception as e:
        print(f" ! Browser proxy refresh failed: {type(e).__name__}: {e}")


@login_required
def api_browser_allowlist_add():
    payload = _json_object()
    failure = _fresh_auth(payload)

    if failure is not None:
        return failure

    try:
        entry = allowlist.add(payload.get("entry"))
    except allowlist.AllowlistError as e:
        return jsonify({"success": False, "code": "invalid_entry", "error": e.message}), e.status

    allowlist.audit("allow-add", request.remote_addr, current_user.get_id(), allowlist.describe(entry))
    _refresh_proxy_quietly()

    return jsonify({"success": True, "entry": entry, "allowlist": allowlist.entries()})


@login_required
def api_browser_allowlist_remove():
    entry = allowlist.remove(str(_json_object().get("id", "")))

    if entry is None:
        return jsonify({"success": False, "code": "not_found"}), 404

    allowlist.audit("allow-remove", request.remote_addr, current_user.get_id(), allowlist.describe(entry))
    _refresh_proxy_quietly()

    return jsonify({"success": True, "allowlist": allowlist.entries()})


@login_required
def api_browser_allowlist_apps():
    """Installed apps for the picker: every container except HomeDock's own and the browser's."""

    try:
        names = sorted(c.name for c in runtime._client().containers.list(all=True) if runtime.BROWSER_LABEL not in (c.labels or {}) and c.name != "homedock-os")
    except Exception:
        names = []

    return jsonify({"success": True, "apps": names})


@login_required
def api_browser_reset():
    """Deletes the profile (logins, cookies, history). Needs the password again, and stops the browser first."""

    payload = _json_object()
    failure = _fresh_auth(payload)

    if failure is not None:
        return failure

    runtime.stop()
    revoke_tickets()

    try:
        runtime.reset_profile()
    except runtime.BrowserError as e:
        return jsonify({"success": False, "code": e.code, "error": e.detail}), 409
    except Exception as e:
        return jsonify({"success": False, "code": "reset_failed", "error": str(e)}), 500

    allowlist.audit("profile-reset", request.remote_addr, current_user.get_id(), "profile")

    return jsonify({**runtime.status(), "success": True})


@login_required
def api_browser_transfers():
    try:
        after = int(request.args.get("after", 0))
    except ValueError:
        after = 0

    return jsonify({"success": True, "notices": transfer.notices_after(after)})


def _ticket_from_body():
    payload = request.get_json(silent=True)
    ticket = payload.get("ticket") if isinstance(payload, dict) else None

    return ticket if isinstance(ticket, str) else None


@login_required
def api_browser_session_renew():
    entry = renew_ticket(_ticket_from_body())

    if entry is None:
        return jsonify({"success": False, "code": "expired"}), 404

    if entry["displaced"]:
        return jsonify({"success": False, "code": "displaced"}), 409

    return jsonify({"success": True, "ttl": TICKET_TTL})


@login_required
def api_browser_session_close():
    """Closing the window ends only its session; the browser keeps running until it has been idle long enough."""

    release_ticket(_ticket_from_body())

    return jsonify({"success": True})


def _header(scope, name):
    wanted = name.encode("latin-1")

    for key, value in scope["headers"]:
        if key == wanted:
            return value.decode("latin-1")

    return None


def _origin_allowed(scope):
    """The sandboxed client reaches the relay with Origin: null. Another site's page is refused, even with a good ticket."""

    origin = _header(scope, "origin")

    if origin is None or origin == "null":
        return True

    host = _header(scope, "host")

    return bool(host) and re.sub(r"^https?://", "", origin) == host


def _cors_headers(scope):
    origin = _header(scope, "origin")

    if origin is None or not _origin_allowed(scope):
        return []

    return [(b"access-control-allow-origin", origin.encode("latin-1")), (b"access-control-allow-credentials", b"true"), (b"vary", b"Origin")]


def _is_document(rest):
    return rest == "/" or rest.endswith(".html")


def _inject_shim(body):
    match = _HEAD_OPEN_RE.search(body)

    return body[: match.end()] + _SHIM_TAG + body[match.end() :] if match else _SHIM_TAG + body


def _plain(status, text, extra=()):
    body = text.encode("utf-8")

    return status, [(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode("latin-1")), (b"cache-control", b"no-store"), *extra], body


def _backend_url(scheme, target, rest, query):
    url = f"{scheme}://{target[0]}:{target[1]}{rest}"

    if query:
        url += f"?{query}"

    return router.yarl_url(url, encoded=True)


async def _serve_http(scope, receive, send, ticket, rest):
    cors = _cors_headers(scope)

    if not _origin_allowed(scope):
        await _send_simple_response(send, *_plain(403, "Forbidden."))
        return

    if scope["method"] == "OPTIONS":
        if not ticket_alive(ticket):
            await _send_simple_response(send, *_plain(403, "Forbidden."))
            return

        requested = _header(scope, "access-control-request-headers")
        extra = [(b"access-control-allow-methods", b"GET, POST, PUT, DELETE, OPTIONS"), (b"access-control-max-age", b"600")]

        if requested:
            extra.append((b"access-control-allow-headers", requested.encode("latin-1")))

        await _send_simple_response(send, 204, [*cors, *extra, (b"content-length", b"0")], b"")
        return

    entry = renew_ticket(ticket)

    if entry is None:
        await _send_simple_response(send, *_plain(403, "This browser session has expired."))
        return

    if entry["displaced"]:
        await _send_simple_response(send, *_plain(409, "This browser session was taken over by another window."))
        return

    # aiohttp is an optional dependency, loaded on first use by the router that already depends on it
    if not router._load_aiohttp():
        await _send_simple_response(send, *_plain(503, "The browser relay needs aiohttp, which is not installed."))
        return

    target = await asyncio.to_thread(runtime.upstream)

    if target is None:
        await _send_simple_response(send, *_plain(503, "The browser is not running."))
        return

    headers = {key.decode("latin-1"): value.decode("latin-1") for key, value in scope["headers"] if key.decode("latin-1").lower() not in _STRIPPED_REQUEST_HEADERS}
    headers["Host"] = f"{target[0]}:{target[1]}"
    document = _is_document(rest)

    if document:
        headers["Accept-Encoding"] = "identity"

    query = scope.get("query_string", b"").decode("latin-1")
    has_body = scope["method"] not in ("GET", "HEAD", "OPTIONS")
    session = await _get_session()

    try:
        async with session.request(scope["method"], _backend_url("http", target, rest, query), headers=headers, data=_stream_request_body(receive) if has_body else None, allow_redirects=False, skip_auto_headers=("Accept-Encoding",)) as response:
            out = [(b"content-security-policy", SANDBOX_POLICY.encode("latin-1")), (b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"), *cors]

            for key, value in response.headers.items():
                if key.lower() not in _STRIPPED_RESPONSE_HEADERS:
                    out.append((key.lower().encode("latin-1"), value.encode("latin-1")))

            if document and "text/html" in response.headers.get("content-type", "") and not response.headers.get("content-encoding"):
                body = await response.content.read(_MAX_DOCUMENT)
                body = _inject_shim(body)

                await send({"type": "http.response.start", "status": response.status, "headers": [*out, (b"content-length", str(len(body)).encode("latin-1"))]})
                await send({"type": "http.response.body", "body": body, "more_body": False})
                return

            await send({"type": "http.response.start", "status": response.status, "headers": out})

            async for chunk in response.content.iter_chunked(65536):
                await send({"type": "http.response.body", "body": chunk, "more_body": True})

            await send({"type": "http.response.body", "body": b"", "more_body": False})

    except asyncio.CancelledError:
        raise

    except Exception as e:
        print(f" ! Browser relay error {scope['method']} {rest}: {type(e).__name__}: {e}")

        try:
            await _send_simple_response(send, *_plain(502, "The browser did not answer."))
        except Exception:
            pass


async def _watch_ticket(ticket):
    while ticket_live(ticket):
        await asyncio.sleep(TICKET_WATCH_INTERVAL)


async def _serve_websocket(scope, receive, send, ticket, rest):
    message = await receive()

    if message["type"] != "websocket.connect":
        return

    entry = renew_ticket(ticket) if _origin_allowed(scope) else None

    if entry is None:
        await send({"type": "websocket.close", "code": 4403})
        return

    if entry["displaced"]:
        await send({"type": "websocket.close", "code": 4409})
        return

    if not router._load_aiohttp():
        await send({"type": "websocket.close", "code": 1011})
        return

    target = await asyncio.to_thread(runtime.upstream)

    if target is None:
        await send({"type": "websocket.close", "code": 1013})
        return

    query = scope.get("query_string", b"").decode("latin-1")
    session = await _get_uncapped_session()

    try:
        async with session.ws_connect(_backend_url("ws", target, rest, query), protocols=scope.get("subprotocols") or [], heartbeat=30, autoping=True, max_msg_size=0) as ws:
            await send({"type": "websocket.accept", "subprotocol": ws.protocol})

            tasks = {asyncio.ensure_future(_pump_client_to_backend(receive, ws)), asyncio.ensure_future(_pump_backend_to_client(ws, send)), asyncio.ensure_future(_watch_ticket(ticket))}

            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task.cancel()

            for task in done:
                exception = task.exception()

                if exception and not isinstance(exception, asyncio.CancelledError):
                    raise exception

    except asyncio.CancelledError:
        raise

    except Exception as e:
        print(f" ! Browser relay websocket error: {type(e).__name__}: {e}")

    try:
        await send({"type": "websocket.close", "code": 1000})
    except Exception:
        pass


async def _serve_browser(scope, receive, send):
    match = _ROUTE_RE.match(scope.get("path", ""))

    if match is None:
        if scope["type"] == "websocket":
            await receive()
            await send({"type": "websocket.close", "code": 4404})
        else:
            await _send_simple_response(send, *_plain(404, "Not found."))

        return

    ticket, rest = match.group(1), match.group(2)

    # Without the trailing slash the client's relative addresses would resolve outside the ticket path.
    if rest is None and scope["type"] == "http":
        await _send_simple_response(send, 308, [(b"location", f"{ROUTE_PREFIX}{ticket}/".encode("latin-1")), (b"content-length", b"0")], b"")
        return

    if scope["type"] == "websocket":
        await _serve_websocket(scope, receive, send, ticket, rest or "/")
    else:
        await _serve_http(scope, receive, send, ticket, rest)


def wrap_asgi_with_browser(downstream):
    start_idle_monitor()

    async def browser_router(scope, receive, send):
        if scope["type"] in ("http", "websocket") and scope.get("path", "").startswith(ROUTE_PREFIX):
            await _serve_browser(scope, receive, send)
            return

        await downstream(scope, receive, send)

    return browser_router
