"""
hd_BrowserEngine.py
Copyright © 2023-2026 Banshee, All Rights Reserved
See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
https://www.banshee.pro
"""

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


class SelkiesChromiumEngine:
    name = "selkies-chromium"
    internal_port = 3000
    health_path = "/"
    config_mount = "/config"
    capabilities = {"clipboard": True, "audio": True}

    def base_reference(self):
        return f"{SELKIES_BASE_REPOSITORY}@{SELKIES_BASE_DIGEST}"

    def image_reference(self):
        return f"{DERIVED_REPOSITORY}:{SELKIES_BASE_DIGEST.split(':')[1][:12]}"

    def environment(self):
        return {"TITLE": "HomeDock OS Browser"}

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

    def ensure_image(self, client, progress=None):
        """Pulls the pinned base image and builds the derived one on this machine. Nothing third-party is shipped with HomeDock."""

        if self.has_image(client):
            return

        if progress:
            progress("pulling")

        client.images.pull(self.base_reference())

        if progress:
            progress("building")

        client.images.build(fileobj=self._build_context(), custom_context=True, tag=self.image_reference(), rm=True, forcerm=True)
