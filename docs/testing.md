# Testing

## Python (pytest)

```
python3 -m venv venv
./venv/bin/pip install -r requirements.txt -r requirements-dev.txt
./venv/bin/pytest
```

Tests live in `tests/`. `conftest.py` puts the repo root on `sys.path`, so tests import `pymodules.*` directly.

### Pebble (ACME test server)

The `pebble` fixture in `tests/conftest.py` starts the official Pebble image (`ghcr.io/letsencrypt/pebble`) with podman or docker, waits for its directory, and removes the container at the end of the session. It yields `directory`, `management` and `ca` (path to the CA bundle to pass as `verify=`). Tests using it carry `@pytest.mark.pebble`; without a container runtime they skip. Set `PEBBLE_IMAGE` to use a different image. Run only these with `pytest -m pebble`, skip them with `pytest -m "not pebble"`.

### Real-container tests

`tests/test_proxy_smoke.py` (marker `container`) starts an nginx container and sends requests through the subdomain router with a `Host` header. It skips without podman or docker; its "stopped app" case cannot tell a stopped container from an unreachable Docker API, because both answer "App not running.".

## Frontend (vitest)

```
npm install
npm test
```

Composable tests sit in `__tests__/` next to the composable they cover, as `*.test.ts`.
