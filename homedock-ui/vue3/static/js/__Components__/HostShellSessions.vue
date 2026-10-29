<!-- homedock-ui/vue3/static/js/__Components__/HostShellSessions.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div v-if="entries.length" class="mb-6">
    <SectionHeader title="Host Shell Sessions" description="When a shell on the host was opened and closed. What was typed is never recorded" :icon="serverIcon" />
    <table :class="[themeClasses.tableTextInner]" class="w-full text-[10px] leading-none antialiased mt-3">
      <thead>
        <tr>
          <th :class="[themeClasses.tableTextUp]" class="w-1/4 text-left font-semibold">{{ $t("Timestamp") }}</th>
          <th :class="[themeClasses.tableTextUp]" class="w-1/6 text-left font-semibold">{{ $t("Event") }}</th>
          <th :class="[themeClasses.tableTextUp]" class="w-1/5 text-left font-semibold">{{ $t("IP") }}</th>
          <th :class="[themeClasses.tableTextUp]" class="w-1/6 text-left font-semibold">{{ $t("User") }}</th>
          <th :class="[themeClasses.tableTextUp]" class="text-left font-semibold">{{ $t("Details") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(entry, index) in entries" :key="entry.timestamp + index" :class="['border-b', themeClasses.tableBorder]" class="h-6">
          <td>{{ entry.timestamp }}</td>
          <td>{{ entry.event === "open" ? $t("Opened") : $t("Closed") }}</td>
          <td>{{ entry.ip }}</td>
          <td>{{ entry.user }}</td>
          <td>{{ entry.detail }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script lang="ts" setup>
import axios from "axios";

import { ref, onMounted } from "vue";

import { useTheme } from "../__Themes__/ThemeSelector";
import { useCsrfToken } from "../__Composables__/useCsrfToken";

import SectionHeader from "./SectionHeader.vue";

import serverIcon from "@iconify-icons/mdi/server";

interface HostShellEntry {
  timestamp: string;
  event: string;
  ip: string;
  user: string;
  target: string;
  detail: string;
}

const { themeClasses } = useTheme();
const csrfToken = useCsrfToken();

const entries = ref<HostShellEntry[]>([]);

onMounted(async () => {
  try {
    const { data } = await axios.get<HostShellEntry[]>("/api/system-logs/serve_host_shell", { headers: { "X-HomeDock-CSRF-Token": csrfToken.value } });

    entries.value = Array.isArray(data) ? data.slice(0, 100) : [];
  } catch {
    entries.value = [];
  }
});
</script>
