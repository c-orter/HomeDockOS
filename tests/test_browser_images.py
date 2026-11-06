from types import SimpleNamespace

import docker
import pytest

from pymodules import hd_BrowserEngine as engine_module
from pymodules import hd_BrowserRuntime as runtime

BASE = "lscr.io/linuxserver/chromium@sha256:abc"
DERIVED = "homedock/browser:new"
OLDER = "homedock/browser:old"


class FakeImages:
    def __init__(self, present=(), pull_events=None, pull_error=None, build_error=None, older=()):
        self.present = set(present)
        self.pull_events = pull_events if pull_events is not None else []
        self.pull_error = pull_error
        self.build_error = build_error
        self.older = list(older)
        self.pulled = []
        self.built = []

    def get(self, reference):
        if reference not in self.present:
            raise docker.errors.ImageNotFound("no such image")

        return object()

    def list(self, name=None):
        return [SimpleNamespace(tags=[tag], attrs={"Created": created}) for tag, created in self.older]

    def build(self, **kwargs):
        if self.build_error:
            raise self.build_error

        self.built.append(kwargs["tag"])
        self.present.add(kwargs["tag"])


def client_with(images):
    def pull(reference, stream=False, decode=False):
        images.pulled.append(reference)

        if images.pull_error:
            raise images.pull_error

        return iter(images.pull_events)

    return SimpleNamespace(images=images, api=SimpleNamespace(pull=pull))


def ensure(images, phases=None, percents=None):
    return engine_module.ensure_derived_image(
        client_with(images), BASE, DERIVED, "homedock/browser", lambda: b"ctx",
        progress=phases.append if phases is not None else None,
        on_percent=percents.append if percents is not None else None,
    )


def test_an_image_already_built_is_used_without_touching_the_network():
    images = FakeImages(present={DERIVED})

    assert ensure(images) == DERIVED
    assert images.pulled == [] and images.built == []


def test_a_pulled_base_is_built_without_pulling_again():
    images = FakeImages(present={BASE})

    assert ensure(images) == DERIVED
    assert images.pulled == [] and images.built == [DERIVED]


def test_a_new_pin_is_pulled_by_digest_then_built_with_progress():
    events = [{"id": "a", "progressDetail": {"current": 50, "total": 100}}, {"id": "b", "progressDetail": {"current": 0, "total": 100}}, {"id": "a", "progressDetail": {"current": 100, "total": 100}}, {"status": "Pull complete"}]
    images = FakeImages(pull_events=events)
    phases, percents = [], []

    assert ensure(images, phases, percents) == DERIVED
    assert phases == ["pulling", "building"]
    assert percents == [50, 25, 50]
    assert images.pulled == [BASE] and "@sha256:" in images.pulled[0]
    assert images.built == [DERIVED]


def test_the_pull_is_never_a_tag():
    engine = engine_module.SelkiesChromiumEngine()

    assert "@sha256:" in engine.base_reference() and "latest" not in engine.base_reference()
    assert "@sha256:" in engine_module.EgressProxyImage(__file__).base_reference()


def test_an_offline_pull_falls_back_to_the_newest_earlier_build():
    images = FakeImages(pull_error=docker.errors.APIError("dial tcp: no route to host"), older=[("homedock/browser:older", "2026-01-01"), (OLDER, "2026-06-01")])

    assert ensure(images) == OLDER
    assert images.built == []


def test_an_offline_pull_with_nothing_earlier_is_a_clear_error():
    images = FakeImages(pull_error=OSError("network is unreachable"))

    with pytest.raises(engine_module.ImageUnavailable) as failed:
        ensure(images)

    assert failed.value.code == "pull_failed"
    assert "internet connection" in failed.value.detail


def test_a_registry_error_in_the_stream_counts_as_a_failed_pull():
    images = FakeImages(pull_events=[{"error": "manifest unknown"}])

    with pytest.raises(engine_module.ImageUnavailable) as failed:
        ensure(images)

    assert failed.value.code == "pull_failed"


def test_a_failed_build_is_never_papered_over_with_an_older_image():
    images = FakeImages(present={BASE}, build_error=docker.errors.BuildError("--no-sandbox still present", iter([])), older=[(OLDER, "2026-06-01")])

    with pytest.raises(engine_module.ImageUnavailable) as failed:
        ensure(images)

    assert failed.value.code == "build_failed"


def test_runtime_turns_a_failed_pull_into_an_error_the_window_can_show():
    images = FakeImages(pull_error=OSError("offline"))
    runtime._pull_failed_at["at"] = None

    with pytest.raises(runtime.BrowserError) as failed:
        runtime._ensure_image(runtime.engine(), client_with(images))

    assert failed.value.code == "pull_failed"
    assert runtime._pull_failed_at["at"] is not None


def test_runtime_remembers_when_it_ran_an_older_image_instead():
    images = FakeImages(pull_error=OSError("offline"), older=[(OLDER, "2026-06-01")])
    runtime._pull_failed_at["at"] = None

    assert runtime._ensure_image(runtime.engine(), client_with(images)) == OLDER
    assert runtime._pull_failed_at["at"] is not None


def running(image):
    return SimpleNamespace(status="running", attrs={"Config": {"Image": image}})


def test_a_browser_on_the_pinned_image_is_left_alone(monkeypatch):
    assert runtime.needs_replacing(running(runtime.engine().image_reference())) is False


def test_an_outdated_browser_is_replaced_once_the_new_image_is_here(monkeypatch):
    monkeypatch.setattr(runtime, "_client", lambda: SimpleNamespace(images=FakeImages(present={runtime.engine().image_reference()})))

    assert runtime.needs_replacing(running("homedock/browser:old")) is True


def test_an_outdated_browser_is_kept_for_a_while_after_a_failed_pull(monkeypatch):
    monkeypatch.setattr(runtime, "_client", lambda: SimpleNamespace(images=FakeImages()))
    runtime._pull_failed_at["at"] = runtime.time.monotonic()

    assert runtime.needs_replacing(running("homedock/browser:old")) is False

    runtime._pull_failed_at["at"] = runtime.time.monotonic() - runtime.PULL_RETRY_SECONDS - 1

    assert runtime.needs_replacing(running("homedock/browser:old")) is True


def test_opening_the_window_joins_a_current_browser_instead_of_restarting_it(monkeypatch):
    started = []
    monkeypatch.setattr(runtime, "running_container", lambda: running(runtime.engine().image_reference()))
    monkeypatch.setattr(runtime.threading, "Thread", lambda **kw: started.append(kw) or SimpleNamespace(start=lambda: None))
    runtime._state.update(phase="stopped", code="", detail="", progress=None)

    runtime.start()

    assert started == []
    assert runtime._state["phase"] == "running"


def test_opening_the_window_after_an_update_starts_the_replacement(monkeypatch):
    started = []
    monkeypatch.setattr(runtime, "running_container", lambda: running("homedock/browser:old"))
    monkeypatch.setattr(runtime, "needs_replacing", lambda c: True)
    monkeypatch.setattr(runtime.threading, "Thread", lambda **kw: started.append(kw) or SimpleNamespace(start=lambda: None))
    runtime._state.update(phase="stopped", code="", detail="", progress=None)

    runtime.start()

    assert len(started) == 1
    assert runtime._state["phase"] == "starting"


def test_pull_progress_is_reported_and_cleared_between_phases():
    runtime._state.update(phase="pulling", progress=None)
    runtime._set_progress(40)

    assert runtime._state["progress"] == 40

    runtime._set_phase("building")

    assert runtime._state["progress"] is None
