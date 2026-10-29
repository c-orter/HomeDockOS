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
}

export interface TerminalTargets {
  homedock: string | null;
  containers: TerminalTarget[];
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

  function open(container: string): TerminalTab {
    const tab = { id: nextId++, container };

    tabs.value.push(tab);
    activeId.value = tab.id;

    return tab;
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

  return { tabs, activeId, activeTab, open, select, close };
}
