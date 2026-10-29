<!-- homedock-ui/vue3/static/js/__Apps__/AppTerminal.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div class="app-terminal flex flex-col h-full overflow-hidden">
    <div class="flex items-center gap-1 px-2 pt-1.5 border-b overflow-x-auto flex-shrink-0 terminal-tabs" :class="themeClasses.utilityToolbarBorder" role="tablist">
      <div v-for="tab in tabs" :key="tab.id" role="tab" :aria-selected="tab.id === activeId && !picking" class="group flex items-center gap-1.5 pl-2.5 pr-1 py-1 text-xs rounded-t cursor-pointer select-none max-w-[200px] flex-shrink-0 transition-colors" :class="[themeClasses.windowText, tab.id === activeId && !picking ? themeClasses.windowButtonBg : themeClasses.windowButtonBgHover]" @click="showTab(tab.id)">
        <Icon :icon="consoleIcon" class="w-3.5 h-3.5 flex-shrink-0" />
        <span class="truncate">{{ tabLabel(tab.container) }}</span>
        <button :class="[themeClasses.windowButtonBgHover]" class="p-0.5 rounded cursor-pointer opacity-60 group-hover:opacity-100" :title="$t('Close')" :aria-label="$t('Close')" @click.stop="closeTab(tab.id)">
          <Icon :icon="closeIcon" class="w-3.5 h-3.5" />
        </button>
      </div>

      <button :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 mb-0.5 rounded cursor-pointer flex-shrink-0" :title="$t('New Session')" :aria-label="$t('New Session')" @click="openPicker">
        <Icon :icon="plusIcon" class="w-4 h-4" />
      </button>
    </div>

    <div class="relative flex-1 min-h-0">
      <AppDockerTerminal v-for="tab in tabs" v-show="tab.id === activeId && !picking" :key="tab.id" class="absolute inset-0" :app-name="tab.container" :dependency-of="tab.container === initialContainer ? dependencyOf : undefined" />

      <div v-if="picking" class="absolute inset-0 overflow-auto p-4" :class="themeClasses.terminalSurface">
        <div class="max-w-xl mx-auto">
          <h3 :class="[themeClasses.terminalStateTitle]" class="text-sm font-semibold mb-1">{{ $t("Open a terminal in...") }}</h3>
          <p :class="[themeClasses.terminalStateText]" class="text-xs mb-3">{{ $t("Each choice opens its own session in a new tab.") }}</p>

          <p v-if="loading" :class="[themeClasses.terminalStateText]" class="text-xs flex items-center gap-2">
            <Icon :icon="spinIcon" class="w-4 h-4 animate-spin" />{{ $t("Loading containers...") }}
          </p>

          <div v-else-if="loadFailed" class="flex items-center gap-3">
            <p :class="[themeClasses.terminalStateText]" class="text-xs">{{ $t("Could not list the containers.") }}</p>
            <button :class="[themeClasses.appPropsActionButtonBg, themeClasses.appPropsActionButtonBorder, themeClasses.appPropsActionButtonText, themeClasses.appPropsActionButtonBgHover]" class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg cursor-pointer" @click="loadTargets">
              <Icon :icon="reloadIcon" class="w-3.5 h-3.5" />{{ $t("Try Again") }}
            </button>
          </div>

          <p v-else-if="!targets.length" :class="[themeClasses.terminalStateText]" class="text-xs">{{ $t("There are no containers to open a terminal in yet.") }}</p>

          <ul v-else class="list-none m-0 p-0 space-y-1">
            <li v-for="target in targets" :key="target.name">
              <button :disabled="target.status !== 'running'" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="w-full flex items-center gap-2 px-3 py-2 text-xs text-left rounded-lg border-0 bg-transparent cursor-pointer disabled:opacity-40 disabled:cursor-default" @click="pick(target.name)">
                <Icon :icon="target.name === homedock ? homeIcon : containerIcon" class="w-4 h-4 flex-shrink-0" />
                <span class="truncate">{{ target.name === homedock ? $t("HomeDock OS") : target.name }}</span>
                <span v-if="target.name === homedock" class="text-[10px] opacity-50 font-mono truncate">{{ target.name }}</span>
                <span class="ml-auto pl-3 text-[10px] opacity-50 flex-shrink-0">{{ target.status === "running" ? "" : $t("Not running") }}</span>
              </button>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import axios from "axios";

import { ref, computed, onMounted } from "vue";
import { useI18n } from "vue-i18n";

import { useTheme } from "../__Themes__/ThemeSelector";
import { useCsrfToken } from "../__Composables__/useCsrfToken";
import { orderTargets, useTerminalTabs, type TerminalTarget } from "../__Composables__/useTerminalTabs";

import { Icon } from "@iconify/vue";
import consoleIcon from "@iconify-icons/mdi/console-line";
import closeIcon from "@iconify-icons/mdi/close";
import plusIcon from "@iconify-icons/mdi/plus";
import spinIcon from "@iconify-icons/mdi/loading";
import reloadIcon from "@iconify-icons/mdi/reload";
import homeIcon from "@iconify-icons/mdi/home-outline";
import containerIcon from "@iconify-icons/mdi/cube-outline";

import AppDockerTerminal from "./AppDockerTerminal.vue";

interface Props {
  appName?: string;
  dependencyOf?: string;
  data?: {
    appName?: string;
    dependencyOf?: string;
  };
}

const props = defineProps<Props>();
const { t } = useI18n();
const { themeClasses } = useTheme();
const csrfToken = useCsrfToken();

const initialContainer = props.appName || props.data?.appName || "";
const dependencyOf = props.dependencyOf || props.data?.dependencyOf;

const { tabs, activeId, open, select, close } = useTerminalTabs(initialContainer);

const picking = ref(tabs.value.length === 0);
const loading = ref(false);
const loadFailed = ref(false);
const homedock = ref<string | null>(null);
const targets = ref<TerminalTarget[]>([]);

const hasTargets = computed(() => targets.value.length > 0);

function tabLabel(container: string): string {
  return container === homedock.value ? t("HomeDock OS") : container;
}

async function loadTargets() {
  loading.value = true;
  loadFailed.value = false;

  try {
    const { data } = await axios.get("/api/container-terminal/targets", { headers: { "X-HomeDock-CSRF-Token": csrfToken.value } });

    homedock.value = data.homedock ?? null;
    targets.value = orderTargets({ homedock: homedock.value, containers: data.containers ?? [] });
  } catch {
    loadFailed.value = true;
  } finally {
    loading.value = false;
  }
}

function openPicker() {
  picking.value = true;

  if (!hasTargets.value || loadFailed.value) loadTargets();
}

function showTab(id: number) {
  select(id);
  picking.value = false;
}

function pick(container: string) {
  open(container);
  picking.value = false;
}

function closeTab(id: number) {
  close(id);

  if (tabs.value.length === 0) openPicker();
}

onMounted(loadTargets);
</script>

<style scoped>
.terminal-tabs {
  scrollbar-width: none;
}

.terminal-tabs::-webkit-scrollbar {
  display: none;
}
</style>
