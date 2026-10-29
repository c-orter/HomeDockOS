// homedock-ui/vue3/static/js/__Composables__/useTerminalTabs.ts
// Copyright © 2023-2026 Banshee, All Rights Reserved
// See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
// https://www.banshee.pro

import { computed, ref } from "vue";

export interface TerminalTarget {
  name: string;
  status?: string;
}

export interface TerminalTab {
  id: number;
  container: string;
  host: boolean;
  attempt: number;
}

export interface HostTarget {
  available: boolean;
  reason: string;
  requires_2fa: boolean;
}

export interface TerminalTargets {
  homedock: string | null;
  containers: TerminalTarget[];
  host?: HostTarget | null;
}

// HomeDock's own container first, then the rest by name
export function orderTargets(targets: TerminalTargets): TerminalTarget[] {
  const rest = targets.containers.filter((target) => target.name !== targets.homedock);
  const own = targets.containers.find((target) => target.name === targets.homedock);

  return own ? [own, ...rest] : rest;
}

export function useTerminalTabs(initialContainer: string = "") {
  const tabs = ref<TerminalTab[]>([]);
  const activeId = ref<number | null>(null);

  let nextId = 1;

  const activeTab = computed(() => tabs.value.find((tab) => tab.id === activeId.value) ?? null);

  function open(container: string, host = false): TerminalTab {
    const tab = { id: nextId++, container, host, attempt: 0 };

    tabs.value.push(tab);
    activeId.value = tab.id;

    return tab;
  }

  // A host tab that signed in again: its terminal starts a fresh session
  function retry(id: number) {
    const tab = tabs.value.find((candidate) => candidate.id === id);

    if (tab) tab.attempt++;
  }

  function select(id: number) {
    if (tabs.value.some((tab) => tab.id === id)) activeId.value = id;
  }

  function close(id: number) {
    const index = tabs.value.findIndex((tab) => tab.id === id);

    if (index === -1) return;

    tabs.value.splice(index, 1);

    if (activeId.value === id) activeId.value = (tabs.value[index] ?? tabs.value[index - 1])?.id ?? null;
  }

  if (initialContainer) open(initialContainer);

  return { tabs, activeId, activeTab, open, select, close, retry };
}
