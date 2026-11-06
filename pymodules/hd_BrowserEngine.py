"""
hd_BrowserEngine.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

import hashlib
import io
import tarfile

import docker

# The engine is one small adapter, so a WebRTC mode or another streaming stack can replace Selkies without touching
# the runtime, the relay or the window. Only the Selkies WebSocket engine exists today.

SELKIES_BASE_REPOSITORY = "lscr.io/linuxserver/chromium"

# Pinned by digest, never a tag. A HomeDock release bumps this. The digest is the multi-arch index of 1aca5d17-ls61.
SELKIES_BASE_DIGEST = "sha256:b147169cc5ff21c62df977f314598537eecf566591c13ad0726b1e5cbd0d01ca"

DERIVED_REPOSITORY = "homedock/browser"

# The image starts as root under s6 to set up its services, then runs Chromium as an unprivileged user with no
# capabilities. Dropping every capability or mounting the root filesystem read-only stops that start-up (tested on
# the pinned image), so these five are the smallest set that works.
INIT_CAPABILITIES = ("CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE", "FOWNER")

# The image's Chromium launcher hard-codes --no-sandbox. The derived image deletes that one line and fails the build
# if it is still there, so the browser can never run unsandboxed.
_DERIVED_DOCKERFILE = """FROM {base}
RUN sed -i '/--no-sandbox/d' /usr/bin/chromium-browser /usr/bin/wrapped-chromium \\
 && ! grep -q -- --no-sandbox /usr/bin/chromium-browser /usr/bin/wrapped-chromium
"""

# Chromium runs as the image's own unprivileged user. The sandbox probe uses it so it sees what Chromium sees.
CHROMIUM_USER = "911:911"

# The namespaces Chromium's sandbox creates.
SANDBOX_PROBE = ["unshare", "--user", "--pid", "--net", "--fork", "true"]


class ImageUnavailable(Exception):
    """The pinned image could not be fetched and no earlier one is on this machine."""

    def __init__(self, code, detail=""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _has_image(client, reference):
    try:
        client.images.get(reference)
    except docker.errors.ImageNotFound:
        return False

    return True


def pull_pinned(client, reference, on_percent=None):
    """Pulls an image by digest and reports how much of the layers has arrived."""

    layers = {}

    for event in client.api.pull(reference, stream=True, decode=True):
        if event.get("error"):
            raise docker.errors.APIError(event["error"])

        detail = event.get("progressDetail") or {}

        if event.get("id") and detail.get("total"):
            layers[event["id"]] = (detail.get("current", 0), detail["total"])

            if on_percent:
                total = sum(t for _, t in layers.values())
                on_percent(int(100 * sum(c for c, _ in layers.values()) / total))


def newest_local(client, repository):
    """The most recently built derived image on this machine, as a reference, or None."""

    images = sorted(client.images.list(name=repository), key=lambda i: i.attrs.get("Created", ""), reverse=True)

    for image in images:
        if image.tags:
            return image.tags[0]

    return None


def ensure_derived_image(client, base, derived, repository, build_context, progress=None, on_percent=None):
    """The reference to run. The pinned image is used when it is here, built from the pinned base otherwise. If the base cannot be pulled (offline, registry down) the newest earlier build on this machine is used; with none, ImageUnavailable says what failed. Nothing but the digest decides what is pulled."""

    if _has_image(client, derived):
        return derived

    if not _has_image(client, base):
        if progress:
            progress("pulling")

        try:
            pull_pinned(client, base, on_percent)
        except (docker.errors.DockerException, OSError) as e:
            older = newest_local(client, repository)

            if older:
                return older

            raise ImageUnavailable("pull_failed", f"The browser image could not be downloaded, and there is no earlier copy to use. Check the server's internet connection and try again. ({e})")

    if progress:
        progress("building")

    try:
        client.images.build(fileobj=build_context(), custom_context=True, tag=derived, rm=True, forcerm=True)
    except (docker.errors.DockerException, OSError) as e:
        raise ImageUnavailable("build_failed", f"The browser image could not be prepared. ({e})")

    return derived


# The egress proxy is HomeDock's own small program (hd_BrowserEgressProxy.py) on the same Python base image the
# HomeDock container uses, pinned by digest (the multi-arch index of python:3.12-alpine). It is built on this machine
# like the browser image, and the image tag carries a hash of the script so a changed script rebuilds it.
PROXY_BASE_REPOSITORY = "python"
PROXY_BASE_DIGEST = "sha256:5789aa194f757888f41fa3d48e14b6feaa1b57c0af0b56fcb1372d6474d3bff0"
PROXY_REPOSITORY = "homedock/browser-egress"
PROXY_PORT = 3128
PROXY_USER = "65534:65534"

_PROXY_DOCKERFILE = """FROM {base}
COPY proxy.py /proxy.py
USER {user}
EXPOSE {port}
ENTRYPOINT ["python", "-I", "/proxy.py"]
"""


class EgressProxyImage:
    def __init__(self, script_path):
        self.script_path = script_path

    def _script(self):
        with open(self.script_path, "rb") as f:
            return f.read()

    def base_reference(self):
        return f"{PROXY_BASE_REPOSITORY}@{PROXY_BASE_DIGEST}"

    def image_reference(self):
        return f"{PROXY_REPOSITORY}:{hashlib.sha256(self._script() + PROXY_BASE_DIGEST.encode()).hexdigest()[:12]}"

    def _build_context(self):
        buffer = io.BytesIO()

        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for name, data in (
                ("Dockerfile", _PROXY_DOCKERFILE.format(base=self.base_reference(), user=PROXY_USER, port=PROXY_PORT).encode("utf-8")),
                ("proxy.py", self._script()),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))

        buffer.seek(0)

        return buffer

    def ensure_image(self, client, progress=None, on_percent=None):
        return ensure_derived_image(client, self.base_reference(), self.image_reference(), PROXY_REPOSITORY, self._build_context, progress, on_percent)


class SelkiesChromiumEngine:
    name = "selkies-chromium"
    internal_port = 3000
    health_path = "/"
    config_mount = "/config"
    # Where Chromium saves downloads in this image.
    download_dir = "/config/Downloads"
    capabilities = {"clipboard": True, "audio": True}

    def base_reference(self):
        return f"{SELKIES_BASE_REPOSITORY}@{SELKIES_BASE_DIGEST}"

    def image_reference(self):
        return f"{DERIVED_REPOSITORY}:{SELKIES_BASE_DIGEST.split(':')[1][:12]}"

    def environment(self, proxy=None):
        env = {"TITLE": "HomeDock OS Browser"}

        if proxy:
            env["CHROME_CLI"] = " ".join(self.proxy_flags(proxy))

        return env

    def proxy_flags(self, proxy):
        """Chromium is told to send everything through the egress proxy, loopback included. QUIC is off because UDP cannot go through it, and WebRTC may not use UDP outside it."""

        return [
            f"--proxy-server=http://{proxy}",
            "--proxy-bypass-list=<-loopback>",
            "--disable-quic",
            "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            # A browser that was stopped or replaced should open fresh, not on a prompt about the last session.
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
        ]

    def tmpfs(self):
        return {"/tmp": "rw,nosuid,size=256m"}

    def _build_context(self):
        data = _DERIVED_DOCKERFILE.format(base=self.base_reference()).encode("utf-8")
        buffer = io.BytesIO()

        with tarfile.open(fileobj=buffer, mode="w") as archive:
            info = tarfile.TarInfo("Dockerfile")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))

        buffer.seek(0)

        return buffer

    def has_image(self, client):
        try:
            client.images.get(self.image_reference())
        except docker.errors.ImageNotFound:
            return False

        return True

    def ensure_image(self, client, progress=None, on_percent=None):
        """The reference to run: the pinned image, built on this machine from the pinned base. Nothing third-party is shipped with HomeDock."""

        return ensure_derived_image(client, self.base_reference(), self.image_reference(), DERIVED_REPOSITORY, self._build_context, progress, on_percent)
