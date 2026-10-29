<!-- homedock-ui/vue3/static/js/__Components__/SettingsCredentials.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <SettingsGroup :header="$t('DOMAIN CERTIFICATE')" :footer="$t('One certificate covers the base domain, its wildcard and every domain you add to an app. A name whose DNS this server cannot edit is checked over port 80 instead.')">
    <SettingsItem v-for="entry in credentials" :key="entry.zone" :icon="keyIcon" icon-color="orange" :title="entry.zone" :description="providerLabel(entry.provider)">
      <button type="button" :aria-label="$t('Remove the credential for {zone}', { zone: entry.zone })" class="p-1.5 rounded-lg transition-all duration-150 hover:opacity-70 cursor-pointer" :class="[themeClasses.storeCardSubtitle]" @click="removeEntry(entry.zone)">
        <Icon :icon="deleteIcon" width="16" height="16" />
      </button>
    </SettingsItem>

    <SettingsItem :icon="dnsIcon" icon-color="purple" :title="$t('Add a DNS credential')" :description="$t('Which provider answers for which domain. The longest matching domain wins.')">
      <template #badge>
        <SettingsHelpTooltip :text="$t('Tokens are stored on this machine and never sent back to the browser. DuckDNS and FreeMyIP can only answer for their own exact name, so a subdomain under one of them is checked over port 80 instead.')" />
      </template>
      <div class="flex flex-wrap items-center justify-end gap-2" style="max-width: 460px">
        <Input :class="[themeClasses.scopeSelector, themeClasses.loginFormInput]" v-model:value="zone" :placeholder="$t('example.com')" :aria-label="$t('Domain')" style="width: 160px" />
        <Select class="rounded-xl" :class="[themeClasses.scopeSelector, themeClasses.loginFormInput]" v-model:value="provider" :popup-class-name="themeClasses.scopeSelector" :show-search="false" :aria-label="$t('DNS provider')" style="width: 130px">
          <SelectOption :class="[themeClasses.scopeSelector]" v-for="name in status?.providers ?? []" :key="name" :value="name">{{ providerLabel(name) }}</SelectOption>
        </Select>
        <InputPassword :class="[themeClasses.scopeSelector, themeClasses.loginFormInput]" v-model:value="token" :placeholder="$t('API token')" :aria-label="$t('API token')" autocomplete="off" style="width: 160px" />
        <button type="button" :disabled="!canAdd" class="h-9 px-4 rounded-xl text-sm font-medium border transition-all duration-200 cursor-pointer disabled:cursor-default disabled:opacity-40" :class="[themeClasses.appPropsActionButtonPrimaryBg, themeClasses.appPropsActionButtonPrimaryBorder, themeClasses.appPropsActionButtonPrimaryText, themeClasses.appPropsActionButtonPrimaryBgHover]" @click="addEntry">{{ $t("Add") }}</button>
      </div>
    </SettingsItem>

    <SettingsItem v-for="item in names" :key="item.name" :icon="item.status === 'covered' ? checkIcon : item.status === 'excluded' ? alertIcon : clockIcon" :icon-color="item.status === 'covered' ? 'green' : item.status === 'excluded' ? 'orange' : 'gray'" :title="item.name" :description="nameDescription(item)" />

    <SettingsItem :icon="certIcon" icon-color="green" :title="$t('Reissue certificate')" :description="reissueDescription" is-last>
      <template #badge>
        <SettingsHelpTooltip :text="$t('Orders the certificate again for every name above. It also happens by itself a minute after a domain is added or removed, and thirty days before expiry. The current certificate keeps serving until a whole order succeeds.')" />
      </template>
      <button type="button" :disabled="!canReissue" class="flex items-center justify-center gap-1.5 h-9 px-5 rounded-xl text-sm font-medium border transition-all duration-200 cursor-pointer disabled:cursor-default disabled:opacity-40" :class="[themeClasses.appPropsActionButtonPrimaryBg, themeClasses.appPropsActionButtonPrimaryBorder, themeClasses.appPropsActionButtonPrimaryText, themeClasses.appPropsActionButtonPrimaryBgHover]" @click="reissue">
        <Icon :icon="busy ? loadingIcon : certIcon" width="15" height="15" :class="busy ? 'animate-spin' : ''" />
        <span>{{ busy ? $t("Working...") : $t("Reissue") }}</span>
      </button>
    </SettingsItem>
  </SettingsGroup>
</template>

<script lang="ts" setup>
import { ref, computed } from "vue";
import { useI18n } from "vue-i18n";
import axios from "axios";

import { Input, Select, message } from "ant-design-vue";
import { Icon } from "@iconify/vue";

import keyIcon from "@iconify-icons/mdi/key-variant";
import dnsIcon from "@iconify-icons/mdi/dns";
import deleteIcon from "@iconify-icons/mdi/delete";
import certIcon from "@iconify-icons/mdi/certificate";
import checkIcon from "@iconify-icons/mdi/check-decagram";
import alertIcon from "@iconify-icons/mdi/alert";
import clockIcon from "@iconify-icons/mdi/clock-outline";
import loadingIcon from "@iconify-icons/mdi/loading";

import { useTheme } from "../__Themes__/ThemeSelector";
import { useCsrfToken } from "../__Composables__/useCsrfToken";
import { errorMessage } from "../__Composables__/useDomains";

import SettingsGroup from "./SettingsGroup.vue";
import SettingsItem from "./SettingsItem.vue";
import SettingsHelpTooltip from "./SettingsHelpTooltip.vue";

const InputPassword = Input.Password;
const SelectOption = Select.Option;

interface NameStatus {
  name: string;
  status: "covered" | "excluded" | "pending";
  reason: string;
}

interface CredentialStatus {
  providers: string[];
  provider_labels: Record<string, string>;
  credentials: { zone: string; provider: string }[];
  domain: string;
  names: NameStatus[];
  state: { running: boolean };
  schedule: { failures: number; last_error: string | null; next_attempt: string | null; reissue_at: string | null };
}

const props = defineProps<{ status: CredentialStatus | null }>();
const emit = defineEmits<{ (event: "refresh"): void }>();

const { t } = useI18n();
const { themeClasses } = useTheme();
const csrfToken = useCsrfToken();

const zone = ref("");
const provider = ref("");
const token = ref("");

const credentials = computed(() => props.status?.credentials ?? []);
const names = computed(() => props.status?.names ?? []);
const busy = computed(() => Boolean(props.status?.state?.running));

const providerLabel = (name: string) => props.status?.provider_labels?.[name] ?? name;

const canAdd = computed(() => Boolean(zone.value.trim().includes(".") && (provider.value || props.status?.providers?.[0]) && token.value));

const covering = computed(() => {
  const base = (props.status?.domain ?? "").toLowerCase();

  return Boolean(base && credentials.value.some((entry) => base === entry.zone || base.endsWith(`.${entry.zone}`)));
});

const canReissue = computed(() => covering.value && !busy.value);

const reissueDescription = computed(() => {
  const schedule = props.status?.schedule;

  if (!props.status?.domain) return t("Set a base domain first.");
  if (!covering.value) return t("Add a credential that covers {domain} first.", { domain: props.status.domain });
  if (schedule?.last_error) return t("The last automatic reissue failed: {error}", { error: schedule.last_error });
  if (schedule?.reissue_at) return t("Scheduled, a minute after the last change");

  return t("For {domain} and the names above", { domain: props.status.domain });
});

function nameDescription(item: NameStatus): string {
  if (item.status === "covered") return t("In the certificate");
  if (item.status === "excluded") return item.reason || t("Left out of the certificate");

  return t("Added at the next order");
}

async function addEntry() {
  try {
    await axios.post("/api/acme/credentials", { zone: zone.value, provider: provider.value || props.status?.providers?.[0], token: token.value }, { headers: { "X-HomeDock-CSRF-Token": csrfToken.value } });

    zone.value = "";
    token.value = "";
    emit("refresh");
  } catch (error) {
    message.error(errorMessage(error, t("Could not save the credential.")));
  }
}

async function removeEntry(target: string) {
  try {
    await axios.post("/api/acme/credentials/remove", { zone: target }, { headers: { "X-HomeDock-CSRF-Token": csrfToken.value } });
    emit("refresh");
  } catch (error) {
    message.error(errorMessage(error, t("Could not remove the credential.")));
  }
}

async function reissue() {
  try {
    await axios.post("/api/acme/reissue", {}, { headers: { "X-HomeDock-CSRF-Token": csrfToken.value } });

    message.info(t("Requesting certificate, this takes a few minutes."));
    emit("refresh");
  } catch (error) {
    message.error(errorMessage(error, t("Could not start the certificate request.")));
  }
}
</script>
