<!-- homedock-ui/vue3/static/js/__Components__/SettingsTabBrowser.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div>
    <SettingsGroup :header="$t('BROWSER')" :footer="$t('Changes to memory, CPU and process limits apply the next time the browser starts. The idle timeout applies right away.')">
      <SettingsItem v-for="(field, index) in fields" :key="field.key" :icon="field.icon" :icon-color="field.color" :title="field.title" :description="field.description" :is-last="index === fields.length - 1">
        <div class="flex flex-col items-end gap-1">
          <input v-model="form[field.key]" type="number" :min="ranges[field.key]?.[0]" :max="ranges[field.key]?.[1]" :step="field.step" :aria-label="field.title" :aria-invalid="!!errors[field.key]" :class="[themeClasses.windowInputBg, themeClasses.windowText, themeClasses.windowBorder]" class="w-28 px-2 py-1 text-sm rounded border outline-hidden text-right" />
          <span v-if="errors[field.key]" class="text-xs text-red-500" role="alert">{{ errors[field.key] }}</span>
        </div>
      </SettingsItem>
    </SettingsGroup>

    <div class="flex items-center gap-3 px-1 mb-4">
      <button type="button" :disabled="saving" :class="[themeClasses.appPropsActionButtonPrimaryBg, themeClasses.appPropsActionButtonPrimaryBorder, themeClasses.appPropsActionButtonPrimaryText, themeClasses.appPropsActionButtonPrimaryBgHover]" class="px-3 py-1.5 text-xs font-medium rounded-lg disabled:opacity-50 cursor-pointer disabled:cursor-default" @click="saveLimits">{{ $t("Save browser settings") }}</button>
      <span v-if="savedNote" class="text-xs" :class="themeClasses.notTextDown" role="status">{{ savedNote }}</span>
    </div>

    <SettingsGroup :header="$t('IMAGE')" :footer="$t('The browser runs a pinned image that HomeDock OS downloads on the first open, and again after an update that changes the pin.')">
      <SettingsItem :icon="packageIcon" icon-color="blue" :title="image.present ? $t('Ready') : $t('Not downloaded yet')" :description="image.reference" is-last />
    </SettingsGroup>

    <SettingsGroup :header="$t('NETWORK ACCESS')" :footer="$t('By default the browser can reach only the public internet. It cannot reach this server, your home network or your apps. Everything below opens a specific destination on purpose.')">
      <div class="px-4 py-3 text-xs leading-relaxed rounded-lg mb-2 border border-amber-500/40 bg-amber-500/10" :class="themeClasses.notTextUp" role="note">
        {{ $t("Anything you allow here can be reached by every website you open in the browser, including a malicious one. Only allow what you would be comfortable having a stranger's web page talk to. This server's own address and the container engine are never reachable, whatever the list says.") }}
      </div>

      <div v-if="!allowlist.length" class="px-4 py-3 text-xs" :class="themeClasses.notTextDown">{{ $t("Nothing allowed. The browser reaches only the public internet.") }}</div>

      <SettingsItem v-for="(entry, index) in allowlist" :key="entry.id" :icon="entryIcon(entry.kind)" icon-color="orange" :title="entry.value + (entry.port ? ':' + entry.port : '')" :description="kindLabel(entry.kind)" :is-last="index === allowlist.length - 1">
        <button type="button" :class="[themeClasses.appPropsActionButtonBg, themeClasses.appPropsActionButtonBorder, themeClasses.appPropsActionButtonText, themeClasses.appPropsActionButtonBgHover]" class="px-3 py-1.5 text-xs font-medium rounded-lg cursor-pointer" :aria-label="$t('Remove {entry}', { entry: entry.value })" @click="removeEntry(entry.id)">{{ $t("Remove") }}</button>
      </SettingsItem>

      <form class="flex flex-wrap items-end gap-2 px-4 py-3" @submit.prevent="askToAdd">
        <label class="flex flex-col gap-1 text-xs" :class="themeClasses.notTextUp">
          {{ $t("Type") }}
          <select v-model="draft.kind" :class="[themeClasses.windowInputBg, themeClasses.windowText, themeClasses.windowBorder]" class="px-2 py-1 text-sm rounded border outline-hidden" @change="onKindChange">
            <option value="host">{{ $t("Host name") }}</option>
            <option value="ip">{{ $t("IP address") }}</option>
            <option value="subnet">{{ $t("Subnet") }}</option>
            <option value="app">{{ $t("Installed app") }}</option>
          </select>
        </label>

        <label class="flex flex-col gap-1 text-xs flex-1 min-w-[10rem]" :class="themeClasses.notTextUp">
          {{ draft.kind === "app" ? $t("App") : $t("Address") }}
          <select v-if="draft.kind === 'app'" v-model="draft.value" :class="[themeClasses.windowInputBg, themeClasses.windowText, themeClasses.windowBorder]" class="px-2 py-1 text-sm rounded border outline-hidden">
            <option value="" disabled>{{ $t("Choose an app") }}</option>
            <option v-for="name in apps" :key="name" :value="name">{{ name }}</option>
          </select>
          <input v-else v-model.trim="draft.value" type="text" :placeholder="placeholder" autocomplete="off" spellcheck="false" :class="[themeClasses.windowInputBg, themeClasses.windowText, themeClasses.windowBorder]" class="px-2 py-1 text-sm rounded border outline-hidden" />
        </label>

        <label class="flex flex-col gap-1 text-xs" :class="themeClasses.notTextUp">
          {{ $t("Port (optional)") }}
          <input v-model="draft.port" type="number" min="1" max="65535" :class="[themeClasses.windowInputBg, themeClasses.windowText, themeClasses.windowBorder]" class="w-24 px-2 py-1 text-sm rounded border outline-hidden" />
        </label>

        <button type="submit" :disabled="!draft.value" :class="[themeClasses.appPropsActionButtonPrimaryBg, themeClasses.appPropsActionButtonPrimaryBorder, themeClasses.appPropsActionButtonPrimaryText, themeClasses.appPropsActionButtonPrimaryBgHover]" class="px-3 py-1.5 text-xs font-medium rounded-lg disabled:opacity-50 cursor-pointer disabled:cursor-default">{{ $t("Allow...") }}</button>
      </form>
      <div v-if="listError" class="px-4 pb-3 text-xs text-red-500" role="alert">{{ listError }}</div>
    </SettingsGroup>

    <SettingsGroup :header="$t('PROFILE')" :footer="$t('The profile holds the browser\'s logins, cookies, history and bookmarks. Resetting stops the browser and deletes all of it.')">
      <SettingsItem :icon="deleteIcon" icon-color="red" :title="$t('Reset browser')" :description="$t('Delete the profile and start fresh')" is-last>
        <button type="button" :class="[themeClasses.appPropsActionButtonBg, themeClasses.appPropsActionButtonBorder, themeClasses.appPropsActionButtonText, themeClasses.appPropsActionButtonBgHover]" class="px-3 py-1.5 text-xs font-medium rounded-lg cursor-pointer" @click="askToReset">{{ $t("Reset...") }}</button>
      </SettingsItem>
    </SettingsGroup>

    <AppDialog :visible="auth.visible" :title="auth.title" :ok-text="auth.busy ? 'Checking' : auth.okText" cancel-text="Cancel" :ok-cancel="true" :close-on-ok="false" :loading="auth.busy" :ok-disabled="!auth.password || (requires2fa && !auth.code)" type="warning" @ok="confirmAuth" @cancel="closeAuth" @update:visible="(v: boolean) => !v && closeAuth()">
      <form class="flex flex-col gap-2" @submit.prevent="confirmAuth">
        <p class="text-sm leading-relaxed m-0" :class="themeClasses.notTextDown">{{ auth.message }}</p>
        <label class="text-xs font-semibold uppercase tracking-wider mt-2" :class="themeClasses.notTextUp" for="browser-auth-password">{{ $t("Password") }}</label>
        <input id="browser-auth-password" ref="passwordInput" v-model="auth.password" type="password" autocomplete="current-password" :disabled="auth.busy" :class="[themeClasses.windowInputBg, themeClasses.windowText, themeClasses.windowBorder]" class="px-2 py-1.5 text-sm rounded border outline-hidden" />
        <template v-if="requires2fa">
          <label class="text-xs font-semibold uppercase tracking-wider mt-1" :class="themeClasses.notTextUp" for="browser-auth-code">{{ $t("2FA code") }}</label>
          <input id="browser-auth-code" v-model="auth.code" type="text" inputmode="numeric" autocomplete="one-time-code" :disabled="auth.busy" :class="[themeClasses.windowInputBg, themeClasses.windowText, themeClasses.windowBorder]" class="px-2 py-1.5 text-sm rounded border outline-hidden" />
        </template>
        <div v-if="auth.error" class="text-xs text-red-500" role="alert">{{ auth.error }}</div>
      </form>
    </AppDialog>
  </div>
</template>

<script lang="ts" setup>
import axios from "axios";

import { computed, nextTick, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";

import { useTheme } from "../__Themes__/ThemeSelector";
import { useCsrfToken } from "../__Composables__/useCsrfToken";

import AppDialog from "./AppDialog.vue";
import SettingsGroup from "./SettingsGroup.vue";
import SettingsItem from "./SettingsItem.vue";

import timerIcon from "@iconify-icons/mdi/timer-sand";
import memoryIcon from "@iconify-icons/mdi/memory";
import cpuIcon from "@iconify-icons/mdi/chip";
import layersIcon from "@iconify-icons/mdi/layers-triple";
import packageIcon from "@iconify-icons/mdi/package-variant-closed";
import deleteIcon from "@iconify-icons/mdi/delete-alert";
import webIcon from "@iconify-icons/mdi/web";
import lanIcon from "@iconify-icons/mdi/lan";
import ipIcon from "@iconify-icons/mdi/ip-network";
import cubeIcon from "@iconify-icons/mdi/cube-outline";

interface Entry {
  id: string;
  kind: string;
  value: string;
  port: number | null;
}

const { t } = useI18n();
const { themeClasses } = useTheme();
const csrfToken = useCsrfToken();

const headers = () => ({ "X-HomeDock-CSRF-Token": csrfToken.value });

const form = reactive<Record<string, number | string>>({ idle_minutes: 15, memory_mb: 2048, cpus: 1, pids: 512 });
const ranges = ref<Record<string, number[]>>({});
const errors = reactive<Record<string, string>>({});
const allowlist = ref<Entry[]>([]);
const image = reactive({ reference: "", present: false });
const requires2fa = ref(false);
const apps = ref<string[]>([]);
const saving = ref(false);
const savedNote = ref("");
const listError = ref("");
const draft = reactive({ kind: "host", value: "", port: "" as string | number });
const passwordInput = ref<HTMLInputElement | null>(null);

const auth = reactive({ visible: false, busy: false, title: "", message: "", okText: "", password: "", code: "", error: "", action: "" as "" | "add" | "reset" });

type IconColor = "blue" | "purple" | "green" | "orange";

const fields = computed<{ key: string; title: string; description: string; icon: typeof timerIcon; color: IconColor; step: number }[]>(() => [
  { key: "idle_minutes", title: t("Idle timeout (minutes)"), description: t("Stop the browser after this long with no window open"), icon: timerIcon, color: "blue", step: 1 },
  { key: "memory_mb", title: t("Memory limit (MB)"), description: t("Half of it is also given to shared memory"), icon: memoryIcon, color: "purple", step: 256 },
  { key: "cpus", title: t("CPU limit (cores)"), description: t("Steps of half a core"), icon: cpuIcon, color: "green", step: 0.5 },
  { key: "pids", title: t("Process limit"), description: t("The most processes the browser may run at once"), icon: layersIcon, color: "orange", step: 64 },
]);

const placeholder = computed(() => (draft.kind === "subnet" ? "192.168.1.0/24" : draft.kind === "ip" ? "192.168.1.20" : "nas.lan"));

function kindLabel(kind: string) {
  return { host: t("Host name"), ip: t("IP address"), subnet: t("Subnet"), app: t("Installed app") }[kind] || kind;
}

function entryIcon(kind: string) {
  return { host: webIcon, ip: ipIcon, subnet: lanIcon, app: cubeIcon }[kind] || webIcon;
}

function take(data: any) {
  if (data.settings) Object.assign(form, data.settings);
  if (data.ranges) ranges.value = data.ranges;
  if (data.allowlist) allowlist.value = data.allowlist;
  if (data.image) Object.assign(image, data.image);
  if (typeof data.requires_2fa === "boolean") requires2fa.value = data.requires_2fa;
}

async function load() {
  try {
    take((await axios.get("/api/browser/settings", { headers: headers() })).data);
  } catch {
    listError.value = t("The browser settings could not be loaded.");
  }
}

async function saveLimits() {
  Object.keys(errors).forEach((k) => delete errors[k]);
  savedNote.value = "";
  saving.value = true;

  try {
    const payload = { idle_minutes: form.idle_minutes, memory_mb: form.memory_mb, cpus: form.cpus, pids: form.pids };
    take((await axios.post("/api/browser/settings/save", payload, { headers: headers() })).data);
    savedNote.value = t("Saved. Limits apply the next time the browser starts.");
  } catch (error: any) {
    const data = error?.response?.data;
    if (data?.field) errors[data.field] = data.error;
    else savedNote.value = t("The settings could not be saved.");
  } finally {
    saving.value = false;
  }
}

async function onKindChange() {
  draft.value = "";

  if (draft.kind === "app" && !apps.value.length) {
    try {
      apps.value = (await axios.get("/api/browser/allowlist/apps", { headers: headers() })).data.apps || [];
    } catch {
      apps.value = [];
    }
  }
}

async function removeEntry(id: string) {
  listError.value = "";

  try {
    allowlist.value = (await axios.post("/api/browser/allowlist/remove", { id }, { headers: headers() })).data.allowlist;
  } catch {
    listError.value = t("That entry could not be removed.");
  }
}

function openAuth(action: "add" | "reset", title: string, message: string, okText: string) {
  Object.assign(auth, { visible: true, busy: false, action, title, message, okText, password: "", code: "", error: "" });
  nextTick(() => passwordInput.value?.focus());
}

function closeAuth() {
  Object.assign(auth, { visible: false, password: "", code: "", error: "", busy: false });
}

function askToAdd() {
  listError.value = "";
  const what = `${draft.value}${draft.port ? ":" + draft.port : ""}`;
  openAuth("add", t("Allow access"), t("Websites opened in the browser will be able to reach {what}. Confirm with your password to allow it.", { what }), t("Allow"));
}

function askToReset() {
  openAuth("reset", t("Reset browser"), t("This stops the browser and deletes its logins, cookies, history and bookmarks. It cannot be undone. Confirm with your password."), t("Reset"));
}

function authError(error: any) {
  const code = error?.response?.data?.code;
  if (code === "auth_failed") return t("The password or code was not right.");
  if (code === "too_many_attempts") return t("Too many attempts. Wait a few minutes and try again.");
  return error?.response?.data?.error || t("That did not work.");
}

async function confirmAuth() {
  if (auth.busy || !auth.password) return;
  auth.busy = true;
  auth.error = "";
  const credentials = { password: auth.password, code: auth.code };

  try {
    if (auth.action === "add") {
      const entry = { kind: draft.kind, value: draft.value, port: draft.port === "" ? null : Number(draft.port) };
      const data = (await axios.post("/api/browser/allowlist/add", { entry, ...credentials }, { headers: headers() })).data;
      allowlist.value = data.allowlist;
      Object.assign(draft, { value: "", port: "" });
    } else {
      await axios.post("/api/browser/reset", credentials, { headers: headers() });
      savedNote.value = t("The browser was reset.");
    }

    closeAuth();
  } catch (error: any) {
    auth.error = authError(error);
    auth.password = "";
    auth.busy = false;
  }
}

onMounted(load);
</script>
