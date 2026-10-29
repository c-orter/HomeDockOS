import asyncio

import pytest

from pymodules import hd_AcmeChallenges as challenges
from pymodules.hd_HTTPRedirector import start_http_redirect_server
from pymodules.hd_SubdomainRouter import wrap_asgi_with_subdomain_router

TOKEN = "abcdefghijklmnopqrstuvwxyz012345"


@pytest.fixture(autouse=True)
def clean():
    challenges._answers.clear()
    yield
    challenges._answers.clear()


def test_only_published_well_formed_tokens_are_served():
    challenges.publish(TOKEN, "answer")

    assert challenges.lookup(challenges.PREFIX + TOKEN) == "answer"
    assert challenges.lookup(challenges.PREFIX + "other-token-not-published-0000") is None
    assert challenges.lookup(challenges.PREFIX + "../etc/passwd") is None
    assert challenges.lookup("/other/" + TOKEN) is None

    challenges.withdraw(TOKEN)
    assert challenges.lookup(challenges.PREFIX + TOKEN) is None


def test_port_80_answers_challenges_and_still_redirects_everything_else():
    client = start_http_redirect_server()[0].wsgi_app.app.test_client()
    challenges.publish(TOKEN, "answer")

    served = client.get(challenges.PREFIX + TOKEN, headers={"Host": "app.example.com"})
    assert (served.status_code, served.get_data(as_text=True)) == (200, "answer")

    assert client.get(challenges.PREFIX + "unknown-token-0000000000", headers={"Host": "localhost"}).status_code == 404

    redirected = client.get("/some/page", headers={"Host": "localhost"})
    assert redirected.status_code == 301
    assert redirected.headers["Location"] == "https://localhost/some/page"


def test_router_answers_challenges_before_any_app_route():
    challenges.publish(TOKEN, "answer")
    sent = []
    reached = []

    async def downstream(scope, receive, send):
        reached.append(scope["path"])

    async def send(message):
        sent.append(message)

    router = wrap_asgi_with_subdomain_router(downstream)
    asyncio.run(router({"type": "http", "path": challenges.PREFIX + TOKEN, "headers": [(b"host", b"app.example.com")]}, None, send))

    assert sent[0]["status"] == 200
    assert sent[1]["body"] == b"answer"
    assert reached == []

    asyncio.run(router({"type": "http", "path": "/", "headers": [(b"host", b"localhost")]}, None, send))
    assert reached == ["/"]
