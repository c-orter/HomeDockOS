<!-- homedock-ui/vue3/static/js/__Components__/AppDomainsCard.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div class="rounded-[10px] px-3.5 py-3 transition-all duration-200" :class="[themeClasses.appPropsUsageCardBg, themeClasses.appPropsUsageCardBorder, themeClasses.aeroExtraScope]" :aria-labelledby="headingId">
    <div class="flex items-center gap-2 mb-2.5">
      <Icon :icon="webIcon" width="20" height="20" :class="[themeClasses.appPropsCardHeaderIcon]" />
      <span :id="headingId" class="text-[15px] font-semibold m-0 flex-1" :class="[themeClasses.appPropsCardHeaderText]">{{ $t("Domains") }}</span>
      <button v-if="data" type="button" class="flex items-center gap-1 px-1.5 py-1 rounded-md text-xs font-medium cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2" :class="[themeClasses.appPropsInfoLink, themeClasses.appPropsInfoLinkHover]" @click="startAdding">
        <Icon :icon="plusIcon" width="14" height="14" />{{ $t("Add domain") }}
      </button>
    </div>

    <p v-if="loadError" class="text-xs m-0" :class="[themeClasses.appPropsStatusDangerText]" role="alert">{{ loadError }}</p>
    <p v-else-if="!data" class="text-xs m-0 opacity-60" :class="[themeClasses.appPropsInfoLabel]">{{ $t("Loading…") }}</p>

    <div v-else class="grid grid-cols-1 sm:grid-cols-[268px_1fr] rounded-[10px] border overflow-hidden min-h-[260px]" :class="[themeClasses.appPropsActionListItemBorder]">
      <ul class="list-none m-0 p-0 flex flex-col border-b sm:border-b-0 sm:border-r" :class="[themeClasses.appPropsActionListItemBorder, themeClasses.appPropsInfoCardBg]" :aria-label="$t('Domains')">
        <li v-if="windowAddress" class="flex items-start gap-2 px-3 py-2.5 border-b" :class="[themeClasses.appPropsInfoRowBorder]">
          <Icon :icon="lockIcon" width="14" height="14" class="mt-0.5 flex-shrink-0 opacity-60" :class="[themeClasses.appPropsInfoLabel]" />
          <span class="min-w-0">
            <span class="block text-xs font-medium break-all" :class="[themeClasses.appPropsInfoValue]">{{ windowAddress }}</span>
            <span class="block text-[10px] opacity-60 leading-snug" :class="[themeClasses.appPropsInfoLabel]">{{ $t("Window address. Always behind login, built in, can't be removed.") }}</span>
          </span>
        </li>

        <li v-for="domain in data.domains" :key="domain.fqdn" class="border-b" :class="[themeClasses.appPropsInfoRowBorder]">
          <button type="button" class="w-full text-left px-3 py-2 cursor-pointer border-0 bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2" :class="[themeClasses.appPropsActionListItemBgHover, !adding && domain.fqdn === selectedName ? themeClasses.appPropsActionButtonPrimaryBg : '']" :aria-current="!adding && domain.fqdn === selectedName ? 'true' : undefined" @click="select(domain.fqdn)">
            <span class="block text-xs break-all" :class="[themeClasses.appPropsInfoValue, domain.fqdn === selectedName && !adding ? 'font-semibold' : 'font-medium']">{{ domain.fqdn }}</span>
            <span class="flex items-center gap-1.5 mt-0.5 text-xs" :class="[themeClasses.appPropsInfoLabel]">
              <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" :class="healthDot(domain)" aria-hidden="true"></span>
              <span>{{ healthText(domain) }}</span>
              <template v-if="domain.fqdn === data.domains[0].fqdn"
                ><span aria-hidden="true">·</span><span>{{ $t("Primary") }}</span></template
              >
              <template v-if="domain.mode === 'direct'"
                ><span aria-hidden="true">·</span><span>{{ $t("Public") }}</span></template
              >
            </span>
          </button>
        </li>

        <li v-if="adding" class="flex flex-col gap-2 px-3 py-2.5">
          <div>
            <label :for="`${headingId}-name`" class="block text-[10px] uppercase tracking-wide opacity-60 mb-0.5" :class="[themeClasses.appPropsInfoLabel]">{{ $t("Domain name") }}</label>
            <Input :id="`${headingId}-name`" ref="nameInput" v-model:value="draft.fqdn" :class="[themeClasses.scopeSelector, themeClasses.loginFormInput]" placeholder="app.example.com" autocomplete="off" spellcheck="false" :status="formError ? 'error' : undefined" :aria-invalid="formError ? 'true' : undefined" :aria-describedby="`${headingId}-hint`" @press-enter="commitAdd" @keydown.esc="cancelAdd" />
            <p :id="`${headingId}-hint`" class="text-xs m-0 mt-1 leading-snug" :class="formError ? themeClasses.appPropsStatusDangerText : themeClasses.appPropsInfoLabel" :role="formError ? 'alert' : undefined">
              <template v-if="formError">{{ formError }}</template>
              <template v-else-if="suggestionAvailable"
                >{{ $t("Suggested:") }} <button type="button" class="p-0 border-0 bg-transparent cursor-pointer underline-offset-2 hover:underline" :class="[themeClasses.appPropsInfoLink]" @click="draft.fqdn = data.suggestion">{{ data.suggestion }}</button></template
              >
              <template v-else-if="!data.base_domain">{{ $t("Set a base domain in Settings to get a suggested name.") }}</template>
            </p>
          </div>
          <div>
            <span :id="`${headingId}-port-label`" class="block text-[10px] uppercase tracking-wide opacity-60 mb-0.5" :class="[themeClasses.appPropsInfoLabel]">{{ $t("Container port") }}</span>
            <Select class="w-full" :class="[themeClasses.scopeSelector, themeClasses.loginFormInput]" :value="draft.port" :aria-labelledby="`${headingId}-port-label`" :popup-class-name="themeClasses.scopeSelector" :show-search="false" @change="draft.port = Number($event)">
              <SelectOption v-for="port in portChoices" :key="port" :value="port" :class="[themeClasses.scopeSelector]">{{ port }}</SelectOption>
            </Select>
          </div>
          <div class="flex items-center gap-2">
            <button type="button" class="px-3 h-7 rounded-md border text-xs font-medium cursor-pointer disabled:opacity-50 disabled:cursor-default" :class="[themeClasses.appPropsActionButtonPrimaryBg, themeClasses.appPropsActionButtonPrimaryBorder, themeClasses.appPropsActionButtonPrimaryText, themeClasses.appPropsActionButtonPrimaryBgHover]" :disabled="busy" @click="commitAdd">{{ $t("Add domain") }}</button>
            <button type="button" class="px-3 h-7 rounded-md border text-xs font-medium cursor-pointer" :class="[themeClasses.appPropsActionButtonBg, themeClasses.appPropsActionButtonBorder, themeClasses.appPropsActionButtonText, themeClasses.appPropsActionButtonBgHover]" @click="cancelAdd">{{ $t("Cancel") }}</button>
          </div>
        </li>
      </ul>

      <div v-if="!data.domains.length && !adding" class="flex flex-col items-center justify-center text-center gap-2 px-4 py-8">
        <span class="text-sm font-semibold" :class="[themeClasses.appPropsInfoValue]">{{ $t("No domains yet") }}</span>
        <span class="text-xs max-w-[320px]" :class="[themeClasses.appPropsInfoLabel]">{{ $t("This app still opens in its window. Add a domain to reach it from other devices.") }}</span>
        <button type="button" class="px-3 h-7 rounded-md border text-xs font-medium cursor-pointer" :class="[themeClasses.appPropsActionButtonPrimaryBg, themeClasses.appPropsActionButtonPrimaryBorder, themeClasses.appPropsActionButtonPrimaryText, themeClasses.appPropsActionButtonPrimaryBgHover]" @click="startAdding">{{ $t("Add domain") }}</button>
      </div>

      <div v-else-if="selected && !adding" class="flex flex-col gap-3.5 p-3.5 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <h3 class="text-[13px] font-semibold m-0 break-all" :class="[themeClasses.appPropsInfoValue]">{{ selected.fqdn }}</h3>
          <span v-if="isPrimary" class="inline-flex items-center h-6 px-2.5 rounded-full border text-[11px] font-semibold uppercase tracking-wide leading-none" :class="[themeClasses.appPropsStatusDarkBg, themeClasses.appPropsStatusDarkBorder, themeClasses.appPropsStatusDarkText]">{{ $t("Primary") }}</span>
          <span class="flex items-center ml-auto">
            <button type="button" class="p-1.5 rounded-md cursor-pointer opacity-60 hover:opacity-100 focus-visible:opacity-100" :class="[copied ? themeClasses.installConfigDefaultCredsCopied : themeClasses.appPropsInfoLink]" :aria-label="$t('Copy {name}', { name: selected.fqdn })" @click="copyName">
              <Icon :icon="copied ? checkIcon : contentCopyIcon" width="14" height="14" />
            </button>
            <button type="button" class="p-1.5 rounded-md cursor-pointer opacity-60 hover:opacity-100 focus-visible:opacity-100" :class="[themeClasses.appPropsInfoLink]" :aria-label="$t('Open {name} in a new tab', { name: selected.fqdn })" @click="openInTab">
              <Icon :icon="openIcon" width="14" height="14" />
            </button>
          </span>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
          <div>
            <span :id="`${headingId}-dport`" class="block text-[10px] uppercase tracking-wide opacity-60" :class="[themeClasses.appPropsInfoLabel]">{{ $t("Container port") }}</span>
            <Select class="w-full mt-0.5" :class="[themeClasses.scopeSelector, themeClasses.loginFormInput]" :value="selected.port" :disabled="busy" :aria-labelledby="`${headingId}-dport`" :popup-class-name="themeClasses.scopeSelector" :show-search="false" @change="changePort(Number($event))">
              <SelectOption v-for="port in portChoices" :key="port" :value="port" :class="[themeClasses.scopeSelector]">{{ port }}</SelectOption>
            </Select>
            <p class="text-xs m-0 mt-1" :class="[themeClasses.appPropsInfoLabel]">{{ selected.protocol === "auto" ? $t("Protocol detected automatically") : $t("Protocol {protocol}", { protocol: selected.protocol }) }}<template v-if="selected.path">, {{ $t("path {path}", { path: selected.path }) }}</template></p>
          </div>

          <fieldset class="m-0 p-0 border-0 min-w-0">
            <legend class="block text-[10px] uppercase tracking-wide opacity-60 p-0" :class="[themeClasses.appPropsInfoLabel]">{{ $t("Who can open it") }}</legend>
            <div class="inline-flex mt-0.5 rounded-lg border overflow-hidden" :class="[themeClasses.appPropsActionButtonBorder]">
              <label v-for="option in accessOptions" :key="option.value" class="flex items-center px-3 h-7 text-xs font-medium focus-within:outline focus-within:outline-2 focus-within:-outline-offset-2" :class="[option.disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer', selected.mode === option.value ? [themeClasses.appPropsActionButtonPrimaryBg, themeClasses.appPropsActionButtonPrimaryText] : [themeClasses.appPropsActionButtonBg, themeClasses.appPropsActionButtonText]]">
                <input type="radio" class="sr-only" :name="`${headingId}-mode`" :value="option.value" :checked="selected.mode === option.value" :disabled="option.disabled || busy" @change="changeMode(option.value)" />
                {{ option.label }}
              </label>
            </div>
            <p class="text-xs m-0 mt-1 leading-snug" :class="[themeClasses.appPropsInfoLabel]">{{ selected.direct_refusal ? selected.direct_refusal : $t("Public skips the HomeDock OS login. The app must handle its own sign-in.") }}</p>
          </fieldset>

          <div>
            <span class="block text-[10px] uppercase tracking-wide opacity-60" :class="[themeClasses.appPropsInfoLabel]">{{ $t("Certificate") }}</span>
            <span class="inline-flex items-center gap-1.5 h-6 px-2.5 rounded-full border mt-0.5 text-[11px] font-semibold uppercase tracking-wide leading-none" :class="pill(certificateTone)">
              <span class="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true"></span>{{ certificateWord }}
            </span>
            <p class="text-xs m-0 mt-1 leading-snug" :class="[themeClasses.appPropsInfoLabel]">{{ certificateNote }}</p>
          </div>

          <div>
            <span class="block text-[10px] uppercase tracking-wide opacity-60" :class="[themeClasses.appPropsInfoLabel]">DNS</span>
            <span class="inline-flex items-center gap-1.5 h-6 px-2.5 rounded-full border mt-0.5 text-[11px] font-semibold uppercase tracking-wide leading-none" :class="pill(dnsTone)">
              <span class="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true"></span>{{ dnsWord }}
            </span>
            <p class="text-xs m-0 mt-1 leading-snug" :class="[themeClasses.appPropsInfoLabel]">
              <button type="button" class="p-0 border-0 bg-transparent cursor-pointer hover:underline underline-offset-2 disabled:opacity-50 disabled:cursor-default" :class="[themeClasses.appPropsInfoLink]" :disabled="dnsChecking" @click="runDnsCheck">{{ $t("Check again") }}</button>
              <template v-if="dns && !dns.resolves"> {{ $t("Create an A record for this name that points at your server.") }}</template>
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2 pt-3 border-t" :class="[themeClasses.appPropsInfoRowBorder]">
          <button type="button" class="px-3 h-7 rounded-md border text-xs font-medium cursor-pointer disabled:opacity-50 disabled:cursor-default" :class="[themeClasses.appPropsActionButtonBg, themeClasses.appPropsActionButtonBorder, themeClasses.appPropsActionButtonText, themeClasses.appPropsActionButtonBgHover]" :disabled="isPrimary || busy" @click="makePrimary">{{ $t("Make primary") }}</button>
          <span class="flex-1"></span>
          <button type="button" class="px-3 h-7 rounded-md border text-xs font-medium cursor-pointer disabled:opacity-50 disabled:cursor-default" :class="[themeClasses.appPropsActionButtonDangerBg, themeClasses.appPropsActionButtonDangerBorder, themeClasses.appPropsActionButtonDangerText, themeClasses.appPropsActionButtonDangerBgHover]" :disabled="busy" @click="removeSelected">{{ confirmingRemove ? $t("Confirm remove") : $t("Remove") }}</button>
        </div>
      </div>
    </div>

    <p v-if="data" class="text-[10px] mt-2 mb-0 opacity-60 leading-snug" :class="[themeClasses.appPropsInfoLabel]">{{ $t("Changes apply immediately. Adding or removing a name reissues the certificate about a minute later. Point each name's DNS at this server yourself.") }}</p>
    <div class="sr-only" role="status" aria-live="polite">{{ announcement }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Input, Select } from "ant-design-vue";

import { Icon } from "@iconify/vue";
import webIcon from "@iconify-icons/mdi/web";
import plusIcon from "@iconify-icons/mdi/plus";
import lockIcon from "@iconify-icons/mdi/lock";
import openIcon from "@iconify-icons/mdi/open-in-new";
import contentCopyIcon from "@iconify-icons/mdi/content-copy";
import checkIcon from "@iconify-icons/mdi/check";

import { useTheme } from "../__Themes__/ThemeSelector";
import { useCsrfToken } from "../__Composables__/useCsrfToken";
import { addDomain, checkDns, domainHealth, errorMessage, fetchDomains, nameProblem, normalizeName, openUrl, removeDomain, updateDomain, type AppDomain, type AppDomains, type DnsCheck, type DomainMode } from "../__Composables__/useDomains";

const SelectOption = Select.Option;

const props = defineProps<{ container: string; windowAddress?: string | null }>();

const { t } = useI18n();
const { themeClasses } = useTheme();
const csrfToken = useCsrfToken();

const headingId = `domains-${Math.random().toString(36).slice(2, 8)}`;

const data = ref<AppDomains | null>(null);
const loadError = ref("");
const selectedName = ref("");
const adding = ref(false);
const draft = ref({ fqdn: "", port: 0 });
const formError = ref("");
const busy = ref(false);
const confirmingRemove = ref(false);
const announcement = ref("");
const copied = ref(false);
const dns = ref<DnsCheck | null>(null);
const dnsChecking = ref(false);
const nameInput = ref<{ focus: () => void } | null>(null);

let confirmTimer: ReturnType<typeof setTimeout> | undefined;
let copiedTimer: ReturnType<typeof setTimeout> | undefined;

const selected = computed<AppDomain | null>(() => data.value?.domains.find((domain) => domain.fqdn === selectedName.value) ?? null);
const isPrimary = computed(() => !!selected.value && data.value?.domains[0]?.fqdn === selected.value.fqdn);
const portChoices = computed(() => {
  const ports = new Set(data.value?.ports ?? []);
  if (selected.value) ports.add(selected.value.port);
  return [...ports].sort((a, b) => a - b);
});
const suggestionAvailable = computed(() => !!data.value?.suggestion && !data.value.domains.some((domain) => domain.fqdn === data.value?.suggestion));

const accessOptions = computed(() => [
  { value: "gated" as DomainMode, label: t("Login required"), disabled: false },
  { value: "direct" as DomainMode, label: t("Public"), disabled: !!selected.value?.direct_refusal },
]);

function say(message: string) {
  announcement.value = "";
  setTimeout(() => (announcement.value = message), 30);
}

async function load() {
  try {
    data.value = await fetchDomains(props.container, csrfToken.value);
    loadError.value = "";

    if (!data.value.domains.some((domain) => domain.fqdn === selectedName.value)) selectedName.value = data.value.domains[0]?.fqdn ?? "";
  } catch (error) {
    loadError.value = errorMessage(error, t("Could not load this app's domains."));
  }
}

function healthDot(domain: AppDomain) {
  const health = domainHealth(domain);
  return health === "healthy" ? "bg-green-500" : health === "attention" ? "bg-yellow-500" : "bg-gray-400";
}

function healthText(domain: AppDomain) {
  const health = domainHealth(domain);
  return health === "healthy" ? t("Healthy") : health === "attention" ? t("Needs attention") : t("Certificate pending");
}

type Tone = "ok" | "warn" | "bad" | "neutral";

function pill(tone: Tone) {
  const map = {
    ok: [themeClasses.value.appPropsStatusSuccessBg, themeClasses.value.appPropsStatusSuccessBorder, themeClasses.value.appPropsStatusSuccessText],
    warn: [themeClasses.value.appPropsStatusWarningBg, themeClasses.value.appPropsStatusWarningBorder, themeClasses.value.appPropsStatusWarningText],
    bad: [themeClasses.value.appPropsStatusDangerBg, themeClasses.value.appPropsStatusDangerBorder, themeClasses.value.appPropsStatusDangerText],
    neutral: [themeClasses.value.appPropsStatusDarkBg, themeClasses.value.appPropsStatusDarkBorder, themeClasses.value.appPropsStatusDarkText],
  };
  return map[tone];
}

const isLocalName = computed(() => !!selected.value && (selected.value.fqdn.endsWith(".local") || selected.value.fqdn.endsWith(".localhost")));

const certificateTone = computed<Tone>(() => (isLocalName.value ? "neutral" : selected.value?.certificate.status === "covered" ? "ok" : selected.value?.certificate.status === "excluded" ? "bad" : "warn"));
const certificateWord = computed(() => (isLocalName.value ? t("Not needed") : selected.value?.certificate.status === "covered" ? t("Covered") : selected.value?.certificate.status === "excluded" ? t("Not covered") : t("Pending")));
const certificateNote = computed(() => {
  const domain = selected.value;
  if (!domain) return "";
  if (isLocalName.value) return t("Local names are served without a public certificate.");
  if (domain.certificate.status === "covered") {
    const days = data.value?.certificate_expires_in_days;
    return days != null ? t("Shared certificate, expires in {days} days.", { days }) : t("Shared certificate.");
  }
  if (domain.certificate.status === "excluded") return domain.certificate.reason;
  return t("This name joins the certificate at the next reissue, about a minute after the last change.");
});

const dnsTone = computed<Tone>(() => (dnsChecking.value || !dns.value ? "neutral" : dns.value.resolves ? "ok" : "warn"));
const dnsWord = computed(() => (dnsChecking.value ? t("Checking…") : !dns.value ? t("Unknown") : dns.value.resolves ? t("Resolves here") : t("Doesn't resolve here")));

async function runDnsCheck() {
  const domain = selected.value;
  if (!domain) return;

  if (isLocalName.value) {
    dns.value = { resolves: true, reason: "" };
    return;
  }

  dnsChecking.value = true;

  try {
    const result = await checkDns(domain.fqdn, csrfToken.value);
    if (selectedName.value === domain.fqdn) dns.value = result;
    say(result.resolves ? t("{name} resolves to this server.", { name: domain.fqdn }) : t("{name} does not resolve to this server.", { name: domain.fqdn }));
  } catch {
    if (selectedName.value === domain.fqdn) dns.value = null;
  } finally {
    dnsChecking.value = false;
  }
}

watch(selectedName, () => {
  dns.value = null;
  confirmingRemove.value = false;
  if (selected.value) runDnsCheck();
});

function select(name: string) {
  adding.value = false;
  selectedName.value = name;
}

async function startAdding() {
  if (!data.value) return;

  adding.value = true;
  formError.value = "";
  draft.value = { fqdn: "", port: data.value.effective_web_port ?? data.value.ports[0] ?? 80 };

  await nextTick();
  nameInput.value?.focus();
}

function cancelAdd() {
  adding.value = false;
  formError.value = "";
}

async function commitAdd() {
  if (!data.value || busy.value) return;

  const name = normalizeName(draft.value.fqdn);
  const problem = nameProblem(name, data.value.domains.map((domain) => domain.fqdn));

  if (problem) {
    formError.value = t(problem);
    return;
  }

  busy.value = true;

  try {
    await addDomain(props.container, { fqdn: name, port: draft.value.port }, csrfToken.value);
    await load();
    adding.value = false;
    selectedName.value = name;
    say(t("Domain added. Certificate reissue queued."));
  } catch (error) {
    formError.value = errorMessage(error, t("Could not add this domain."));
  } finally {
    busy.value = false;
  }
}

async function change(changes: { port?: number; mode?: DomainMode; primary?: boolean }, announce: string) {
  const domain = selected.value;
  if (!domain || busy.value) return;

  busy.value = true;

  try {
    await updateDomain(props.container, domain.fqdn, changes, csrfToken.value);
    await load();
    selectedName.value = domain.fqdn;
    say(announce);
  } catch (error) {
    say(errorMessage(error, t("Could not save the change.")));
    await load();
  } finally {
    busy.value = false;
  }
}

const changePort = (port: number) => change({ port }, t("Port changed to {port}.", { port }));
const changeMode = (mode: DomainMode) => change({ mode }, mode === "direct" ? t("Now public.") : t("Login required."));
const makePrimary = () => change({ primary: true }, t("{name} is now the primary address.", { name: selected.value?.fqdn ?? "" }));

async function removeSelected() {
  const domain = selected.value;
  if (!domain || busy.value) return;

  if (!confirmingRemove.value) {
    confirmingRemove.value = true;
    clearTimeout(confirmTimer);
    confirmTimer = setTimeout(() => (confirmingRemove.value = false), 4000);
    return;
  }

  busy.value = true;

  try {
    await removeDomain(props.container, domain.fqdn, csrfToken.value);
    confirmingRemove.value = false;
    await load();
    say(t("{name} removed. Certificate reissue queued.", { name: domain.fqdn }));
  } catch (error) {
    say(errorMessage(error, t("Could not remove this domain.")));
  } finally {
    busy.value = false;
  }
}

async function copyName() {
  if (!selected.value) return;

  try {
    await navigator.clipboard.writeText(selected.value.fqdn);
    copied.value = true;
    clearTimeout(copiedTimer);
    copiedTimer = setTimeout(() => (copied.value = false), 1500);
    say(t("Copied."));
  } catch {
    say(t("Could not copy."));
  }
}

function openInTab() {
  if (selected.value) window.open(openUrl(selected.value, window.location), "_blank", "noopener,noreferrer");
}

onMounted(load);
watch(() => props.container, load);
onBeforeUnmount(() => {
  clearTimeout(confirmTimer);
  clearTimeout(copiedTimer);
});
</script>
