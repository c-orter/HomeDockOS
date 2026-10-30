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
        <button v-if="running" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded cursor-pointer" :title="$t('Fullscreen')" :aria-label="$t('Fullscreen')" @click="toggleFullscreen">
          <Icon :icon="fullscreenIcon" class="w-4 h-4" />
        </button>
        <button v-if="running || busy" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded cursor-pointer" :title="$t('Stop the browser')" :aria-label="$t('Stop the browser')" @click="stopBrowser">
          <Icon :icon="stopIcon" class="w-4 h-4" />
        </button>
      </div>
    </div>

    <div ref="stage" class="relative flex-1 min-h-0" :class="themeClasses.terminalSurface">
      <!-- No allow-same-origin: the page inside gets an opaque origin and cannot read HomeDock's cookies, storage or API. -->
      <iframe v-if="frameSrc" :src="frameSrc" class="absolute inset-0 w-full h-full border-0" sandbox="allow-scripts allow-forms allow-pointer-lock allow-downloads allow-popups" allow="fullscreen" :title="$t('Browser')" referrerpolicy="no-referrer"></iframe>

      <div v-else class="absolute inset-0 overflow-auto p-4">
        <div class="max-w-md mx-auto">
          <template v-if="phase === 'unavailable'">
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
            <p :class="[themeClasses.terminalStateText]" class="text-xs leading-relaxed mb-3">{{ $t("Your profile, with its logins and bookmarks, is kept for the next start.") }}</p>
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

interface BrowserStatus {
  available: boolean;
  phase: string;
  code: string;
  detail: string;
}

const POLL_MS = 1000;
const RENEW_MS = 30000;

const { t } = useI18n();
const { themeClasses } = useTheme();
const csrfToken = useCsrfToken();

const phase = ref("stopped");
const code = ref("");
const detail = ref("");
const frameSrc = ref("");
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
      return t("Downloading the browser image...");
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

const errorTitle = computed(() => (code.value === "sandbox_unavailable" ? t("The browser's sandbox can't be enabled on this host") : t("The browser could not start")));

function apply(status: BrowserStatus) {
  phase.value = status.phase;
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

  if (!renew) {
    renew = setInterval(renewTicket, RENEW_MS);
  }
}

// A ticket that lapsed (a sleeping laptop, a long network drop) is replaced, which reloads the stream.
async function renewTicket() {
  try {
    await axios.post("/api/browser/session/renew", { ticket }, { headers: headers() });
  } catch (error: any) {
    if (error?.response?.status === 404 && !disposed) {
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
    const response = await axios.get<BrowserStatus>("/api/browser/status");
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

onBeforeUnmount(() => {
  disposed = true;
  clearTimers();
});
</script>
