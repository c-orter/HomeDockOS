<!-- homedock-ui/vue3/static/js/__Apps__/AppBrowser.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div class="app-browser flex flex-col h-full overflow-hidden">
    <div class="flex items-center gap-2 px-2 py-1 border-b flex-shrink-0" :class="themeClasses.utilityToolbarBorder">
      <span class="flex items-center gap-1.5 text-xs min-w-0" :class="[themeClasses.windowText]" role="status">
        <Icon :icon="busy ? spinIcon : webIcon" class="w-3.5 h-3.5 flex-shrink-0" :class="{ 'animate-spin': busy }" />
        <span class="truncate">{{ statusLabel }}</span>
      </span>

      <div class="ml-auto flex items-center gap-1">
        <button v-if="running && audioAvailable" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded cursor-pointer" :title="muted ? $t('Unmute') : $t('Mute')" :aria-label="muted ? $t('Unmute') : $t('Mute')" :aria-pressed="!muted" @click="toggleMute">
          <Icon :icon="muted ? volumeOffIcon : volumeHighIcon" class="w-4 h-4" />
        </button>
        <button v-if="running" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded cursor-pointer" :title="$t('Send the files in your dropzone\'s Browser folder to the browser. They appear under Uploads in its file dialog.')" :aria-label="$t('Send files to the browser')" @click="sendFiles">
          <Icon :icon="uploadIcon" class="w-4 h-4" />
        </button>
        <button :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded cursor-pointer" :title="$t('Downloads')" :aria-label="$t('Downloads')" @click="openDownloads">
          <Icon :icon="downloadsIcon" class="w-4 h-4" />
        </button>
        <button v-if="running" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded cursor-pointer" :title="$t('Fullscreen')" :aria-label="$t('Fullscreen')" @click="toggleFullscreen">
          <Icon :icon="fullscreenIcon" class="w-4 h-4" />
        </button>
        <button v-if="running || busy" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded cursor-pointer" :title="$t('Stop the browser')" :aria-label="$t('Stop the browser')" @click="stopBrowser">
          <Icon :icon="stopIcon" class="w-4 h-4" />
        </button>
      </div>
    </div>

    <div v-if="notice" class="flex items-center gap-2 px-2 py-1 text-xs border-b flex-shrink-0" :class="[themeClasses.utilityToolbarBorder, themeClasses.windowText]" role="status">
      <span class="truncate min-w-0">{{ notice }}</span>
      <button class="ml-auto p-0.5 rounded cursor-pointer" :class="themeClasses.windowButtonBgHover" :aria-label="$t('Dismiss')" @click="notice = ''">
        <Icon :icon="closeIcon" class="w-3.5 h-3.5" />
      </button>
    </div>

    <div ref="stage" class="relative flex-1 min-h-0" :class="themeClasses.terminalSurface">
      <!-- No allow-same-origin: the page inside gets an opaque origin and cannot read HomeDock's cookies, storage or API. -->
      <iframe v-if="frameSrc" ref="frame" @load="sendAudioState" :src="frameSrc" class="absolute inset-0 w-full h-full border-0" sandbox="allow-scripts allow-forms allow-pointer-lock allow-downloads allow-popups" allow="fullscreen; clipboard-read; clipboard-write; autoplay" :title="$t('Browser')" referrerpolicy="no-referrer"></iframe>

      <div v-else class="absolute inset-0 overflow-auto p-4">
        <div class="max-w-md mx-auto">
          <template v-if="displaced">
            <h3 :class="[themeClasses.terminalStateTitle]" class="text-sm font-semibold mb-1">{{ $t("The browser is open in another window") }}</h3>
            <p :class="[themeClasses.terminalStateText]" class="text-xs leading-relaxed mb-3">{{ $t("Only one window can show the browser at a time. Taking it back moves the view here and pauses the other window.") }}</p>
            <button :class="[themeClasses.appPropsActionButtonPrimaryBg, themeClasses.appPropsActionButtonPrimaryBorder, themeClasses.appPropsActionButtonPrimaryText, themeClasses.appPropsActionButtonPrimaryBgHover]" class="px-3 py-1.5 text-xs font-medium rounded-lg cursor-pointer" @click="takeBack">{{ $t("Take it back") }}</button>
          </template>

          <template v-else-if="phase === 'unavailable'">
            <h3 :class="[themeClasses.terminalStateTitle]" class="text-sm font-semibold mb-1">{{ $t("The browser needs Docker") }}</h3>
            <p :class="[themeClasses.terminalStateText]" class="text-xs leading-relaxed">{{ $t("HomeDock OS could not reach the container engine, so there is nothing to run the browser in.") }}</p>
          </template>

          <template v-else-if="phase === 'error'">
            <h3 :class="[themeClasses.terminalStateTitle]" class="text-sm font-semibold mb-1">{{ errorTitle }}</h3>
            <p v-if="detail" :class="[themeClasses.terminalStateText]" class="text-xs leading-relaxed mb-3">{{ detail }}</p>
            <button :class="[themeClasses.appPropsActionButtonBg, themeClasses.appPropsActionButtonBorder, themeClasses.appPropsActionButtonText, themeClasses.appPropsActionButtonBgHover]" class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg cursor-pointer" @click="begin">
              <Icon :icon="reloadIcon" class="w-3.5 h-3.5" />{{ $t("Try Again") }}
            </button>
          </template>

          <template v-else-if="phase === 'stopped' && !busy">
            <h3 :class="[themeClasses.terminalStateTitle]" class="text-sm font-semibold mb-1">{{ $t("The browser is stopped") }}</h3>
            <p :class="[themeClasses.terminalStateText]" class="text-xs leading-relaxed mb-2">{{ $t("Your profile, with its logins and bookmarks, is kept for the next start.") }}</p>
            <p :class="[themeClasses.terminalStateText]" class="text-xs leading-relaxed mb-3">{{ $t("The browser reaches the internet through a filter that blocks your home network and this server. Because of that filter, sites that use QUIC fall back to regular connections, which can be a little slower.") }}</p>
            <button :class="[themeClasses.appPropsActionButtonPrimaryBg, themeClasses.appPropsActionButtonPrimaryBorder, themeClasses.appPropsActionButtonPrimaryText, themeClasses.appPropsActionButtonPrimaryBgHover]" class="px-3 py-1.5 text-xs font-medium rounded-lg cursor-pointer" @click="begin">{{ $t("Start the browser") }}</button>
          </template>

          <template v-else>
            <h3 :class="[themeClasses.terminalStateTitle]" class="text-sm font-semibold mb-1 flex items-center gap-2">
              <Icon :icon="spinIcon" class="w-4 h-4 animate-spin" />{{ statusLabel }}
            </h3>
            <p v-if="phase === 'pulling'" :class="[themeClasses.terminalStateText]" class="text-xs leading-relaxed">{{ $t("This download only happens the first time, or after an update.") }}</p>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import axios from "axios";

import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { useI18n } from "vue-i18n";

import { useTheme } from "../__Themes__/ThemeSelector";
import { useCsrfToken } from "../__Composables__/useCsrfToken";

import { Icon } from "@iconify/vue";
import webIcon from "@iconify-icons/mdi/web";
import spinIcon from "@iconify-icons/mdi/loading";
import reloadIcon from "@iconify-icons/mdi/reload";
import stopIcon from "@iconify-icons/mdi/stop";
import fullscreenIcon from "@iconify-icons/mdi/fullscreen";
import uploadIcon from "@iconify-icons/mdi/upload";
import downloadsIcon from "@iconify-icons/mdi/folder-download";
import closeIcon from "@iconify-icons/mdi/close";
import volumeOffIcon from "@iconify-icons/mdi/volume-off";
import volumeHighIcon from "@iconify-icons/mdi/volume-high";
import { useWindowStore } from "../__Stores__/windowStore";

interface BrowserStatus {
  available: boolean;
  phase: string;
  code: string;
  detail: string;
  progress?: number | null;
  capabilities?: { audio?: boolean; clipboard?: boolean };
}

const POLL_MS = 1000;
const RENEW_MS = 5000;

const { t } = useI18n();
const { themeClasses } = useTheme();
const csrfToken = useCsrfToken();

const phase = ref("stopped");
const code = ref("");
const detail = ref("");
const frameSrc = ref("");
const displaced = ref(false);
const progress = ref<number | null>(null);
const muted = ref(true);
const audioAvailable = ref(true);
const frame = ref<HTMLIFrameElement | null>(null);
const notice = ref("");
const windowStore = useWindowStore();
let lastNoticeId = 0;
const stage = ref<HTMLElement | null>(null);

let poll: ReturnType<typeof setInterval> | null = null;
let renew: ReturnType<typeof setInterval> | null = null;
let ticket = "";
let disposed = false;

const headers = () => ({ "X-HomeDock-CSRF-Token": csrfToken.value });

const busy = computed(() => ["pulling", "building", "checking", "starting"].includes(phase.value));
const running = computed(() => phase.value === "running" && !!frameSrc.value);

const statusLabel = computed(() => {
  switch (phase.value) {
    case "pulling":
      return progress.value === null ? t("Downloading the browser image...") : t("Downloading the browser image... {percent}%", { percent: progress.value });
    case "building":
      return t("Preparing the browser image...");
    case "checking":
      return t("Checking the browser sandbox...");
    case "starting":
      return t("Starting the browser...");
    case "running":
      return frameSrc.value ? t("Running") : t("Connecting...");
    case "error":
      return t("Could not start");
    case "unavailable":
      return t("Docker unavailable");
    default:
      return t("Stopped");
  }
});

const errorTitle = computed(() => {
  if (code.value === "sandbox_unavailable") return t("The browser's sandbox can't be enabled on this host");
  if (code.value === "pull_failed") return t("The browser image could not be downloaded");
  return t("The browser could not start");
});

function apply(status: BrowserStatus) {
  phase.value = status.phase;
  progress.value = typeof status.progress === "number" ? status.progress : null;
  audioAvailable.value = status.capabilities?.audio !== false;
  code.value = status.code || "";
  detail.value = status.detail || "";
}

function clearTimers() {
  if (poll) clearInterval(poll);
  if (renew) clearInterval(renew);
  poll = null;
  renew = null;
}

async function openSession() {
  const response = await axios.post("/api/browser/session", {}, { headers: headers() });
  ticket = response.data.ticket;
  frameSrc.value = response.data.path;

  // The clipboard API only exists on https pages and localhost. Pasting with Ctrl+V still works without it.
  if (!window.isSecureContext && !notice.value) {
    notice.value = t("Automatic clipboard sync needs this page to be opened over https. Until then, click inside the browser and press Ctrl+V to paste.");
  }

  if (!renew) {
    renew = setInterval(renewTicket, RENEW_MS);
  }
}

interface TransferNotice {
  id: number;
  kind: string;
  name: string;
  reason: string;
}

function describe(n: TransferNotice) {
  if (n.kind === "saved") return t("Saved {name} to the Browser folder in your dropzone.", { name: n.name });
  if (n.kind === "rejected") return t("{name} was not kept. {reason}", { name: n.name, reason: n.reason });
  return t("{name} was not sent to the browser. {reason}", { name: n.name, reason: n.reason });
}

function showNotices(list: TransferNotice[]) {
  for (const n of list) lastNoticeId = Math.max(lastNoticeId, n.id);
  if (list.length) notice.value = describe(list[list.length - 1]);
}

async function pollTransfers() {
  try {
    const response = await axios.get("/api/browser/transfers", { params: { after: lastNoticeId }, headers: headers() });
    showNotices(response.data.notices || []);
  } catch {
    // The notices are a courtesy; the next poll tries again.
  }
}

async function sendFiles() {
  try {
    const response = await axios.post("/api/browser/files/refresh", {}, { headers: headers() });
    showNotices(response.data.notices || []);
    notice.value = notice.value || t("{count} file(s) are ready under Uploads in the browser's file dialog.", { count: response.data.count });
  } catch {
    notice.value = t("The files could not be sent to the browser.");
  }
}

// The page inside has an opaque origin, so the only way to reach it is a message. The browser starts muted; the first unmute is this click.
function sendAudioState() {
  frame.value?.contentWindow?.postMessage({ type: "hd-audio", muted: muted.value }, "*");
}

function toggleMute() {
  muted.value = !muted.value;
  sendAudioState();
}

function openDownloads() {
  windowStore.openWindow("fileexplorer", { allowMultiple: true, data: { initialLocation: "dropzone", initialPath: "Browser" } });
}

// Another window opened the browser, so this one stops carrying the stream. It keeps renewing, which keeps it counted as open.
async function takeBack() {
  try {
    await openSession();
    displaced.value = false;
  } catch {
    phase.value = "error";
    detail.value = t("The browser is running, but a session could not be opened.");
  }
}

// A ticket that lapsed (a sleeping laptop, a long network drop) is replaced, which reloads the stream.
async function renewTicket() {
  try {
    await axios.post("/api/browser/session/renew", { ticket }, { headers: headers() });
    pollTransfers();
  } catch (error: any) {
    if (error?.response?.data?.code === "displaced") {
      displaced.value = true;
      frameSrc.value = "";
      return;
    }

    if (error?.response?.status === 404 && !disposed && !displaced.value) {
      try {
        await openSession();
      } catch {
        await begin();
      }
    }
  }
}

// One step of watching the start: it ends the poll on a terminal phase and opens the stream the moment the browser runs.
async function tick() {
  try {
    const response = await axios.get<BrowserStatus>("/api/browser/status", { headers: headers() });
    apply(response.data);
  } catch {
    phase.value = "error";
    detail.value = t("HomeDock OS could not be reached.");
    clearTimers();
    return;
  }

  if (disposed || busy.value) return;

  if (poll) {
    clearInterval(poll);
    poll = null;
  }

  if (phase.value === "running" && !frameSrc.value) {
    try {
      await openSession();
    } catch {
      phase.value = "error";
      detail.value = t("The browser is running, but a session could not be opened.");
    }
  }
}

async function begin() {
  clearTimers();
  frameSrc.value = "";
  displaced.value = false;

  try {
    const response = await axios.post<BrowserStatus>("/api/browser/start", {}, { headers: headers() });
    apply(response.data);
  } catch (error: any) {
    if (error?.response?.data?.phase) {
      apply(error.response.data);
    } else {
      phase.value = "error";
      detail.value = t("HomeDock OS could not be reached.");
    }
    return;
  }

  poll = setInterval(tick, POLL_MS);
  await tick();
}

async function stopBrowser() {
  clearTimers();
  frameSrc.value = "";
  ticket = "";

  try {
    const response = await axios.post<BrowserStatus>("/api/browser/stop", {}, { headers: headers() });
    apply(response.data);
  } catch {
    phase.value = "stopped";
  }
}

function toggleFullscreen() {
  if (document.fullscreenElement) {
    document.exitFullscreen();
  } else {
    stage.value?.requestFullscreen();
  }
}

onMounted(begin);

// Closing the window ends only this window's session. The browser keeps running until it has been idle long enough.
onBeforeUnmount(() => {
  disposed = true;
  clearTimers();

  if (ticket) {
    axios.post("/api/browser/session/close", { ticket }, { headers: headers() }).catch(() => {});
  }
});
</script>
