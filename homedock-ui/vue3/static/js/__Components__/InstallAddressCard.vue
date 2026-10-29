<!-- homedock-ui/vue3/static/js/__Components__/InstallAddressCard.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div :class="[themeClasses.installConfigSectionCard]" class="p-4">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <Icon :icon="globeIcon" class="h-4 w-4" :class="[themeClasses.installConfigSectionTitle]" />
        <h3 :class="[themeClasses.installConfigSectionTitle]" class="text-sm font-semibold">{{ $t("Address") }}</h3>
      </div>
      <button type="button" :class="[themeClasses.installConfigSectionAddBtn]" class="text-xs font-medium transition-colors cursor-pointer" @click="addRow">{{ $t("+ Add") }}</button>
    </div>

    <div v-if="rows.length > 0" class="space-y-2">
      <div v-for="(row, index) in rows" :key="'address-' + index" class="grid grid-cols-[1fr_auto] gap-2 items-center">
        <Input :class="[themeClasses.scopeSelector, themeClasses.loginFormInput]" :value="row" :status="rowProblem(row) ? 'error' : undefined" :placeholder="suggestion || $t('app.example.com')" :aria-label="$t('Domain name')" :aria-invalid="Boolean(rowProblem(row))" @update:value="(value: string) => setRow(index, value)" />
        <button type="button" :class="[themeClasses.storeCardSubtitle]" :aria-label="$t('Remove this address')" class="p-1.5 rounded-lg transition-all duration-150 hover:opacity-70 cursor-pointer" @click="removeRow(index)">
          <Icon :icon="deleteIcon" class="h-4 w-4" />
        </button>
        <p v-if="rowProblem(row)" class="col-span-2 -mt-1 mb-0 text-[10px] text-red-500" role="alert">{{ $t(rowProblem(row)) }}</p>
      </div>
    </div>
    <div v-else class="flex flex-col items-center py-2 gap-1">
      <span :class="[themeClasses.storeCardSubtitle]" class="text-[10px] opacity-60">{{ $t("No address. The app opens from its window and by IP.") }}</span>
    </div>

    <p :class="[themeClasses.installConfigLabel]" class="mt-3 mb-0 text-[10px]">
      {{ baseDomain ? $t("Saved when you install. Each name needs DNS pointing at this server; the certificate is reissued to cover it.") : $t("Set a base domain in Settings to get a suggested address. Any domain you own works here too.") }}
    </p>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, onMounted } from "vue";

import { Input } from "ant-design-vue";
import { Icon } from "@iconify/vue";
import globeIcon from "@iconify-icons/mdi/globe";
import deleteIcon from "@iconify-icons/mdi/delete";

import { useTheme } from "../__Themes__/ThemeSelector";
import { useCsrfToken } from "../__Composables__/useCsrfToken";
import { addressProblem, fetchSuggestion, nameProblem } from "../__Composables__/useDomains";

const props = defineProps<{ container: string }>();

const rows = defineModel<string[]>("rows", { default: () => [] });
const invalid = defineModel<boolean>("invalid", { default: false });

const { themeClasses } = useTheme();
const csrfToken = useCsrfToken();

const baseDomain = ref("");
const suggestion = ref("");

const rowProblem = (row: string) => (row.trim() ? nameProblem(row, []) : "");

const problem = computed(() => addressProblem(rows.value));

function sync() {
  invalid.value = Boolean(problem.value);
}

function setRow(index: number, value: string) {
  rows.value = rows.value.map((row, at) => (at === index ? value : row));
  sync();
}

function addRow() {
  rows.value = [...rows.value, ""];
}

function removeRow(index: number) {
  rows.value = rows.value.filter((_, at) => at !== index);
  sync();
}

// the suggestion is only offered, never saved: it becomes a domain when Install is pressed
onMounted(async () => {
  try {
    const found = await fetchSuggestion(props.container, csrfToken.value);

    baseDomain.value = found.base_domain;
    suggestion.value = found.suggestion;

    if (found.suggestion && rows.value.length === 0) rows.value = [found.suggestion];
  } catch {
    // no suggestion: the card still takes names typed by hand
  }

  sync();
});
</script>
