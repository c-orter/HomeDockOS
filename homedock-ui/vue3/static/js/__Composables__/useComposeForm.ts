// homedock-ui/vue3/static/js/__Composables__/useComposeForm.ts
// Copyright © 2023-2026 Banshee, All Rights Reserved
// See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
// https://www.banshee.pro

export interface Mapping {
  host: string;
  container: string;
}

export interface EnvRow {
  key: string;
  value: string;
}

export interface NetworkRow {
  type: string;
  customName: string;
}

export const PRESET_NETWORKS = ["host", "bridge", "homedock_network", "none"];

export function parseMapping(entry: string): Mapping {
  const cut = entry.lastIndexOf(":");
  if (cut === -1) return { host: "", container: entry.trim() };
  return { host: entry.slice(0, cut).trim(), container: entry.slice(cut + 1).trim() };
}

export function parseVolume(entry: string): Mapping {
  const cut = entry.indexOf(":");
  if (cut === -1) return { host: "", container: entry.trim() };
  return { host: entry.slice(0, cut).trim(), container: entry.slice(cut + 1).trim() };
}

export function formatMapping(row: Mapping): string {
  const host = row.host.trim();
  const container = row.container.trim();
  if (!container) return host ? `${host}:` : "";
  return host ? `${host}:${container}` : container;
}

export function formatMappings(rows: Mapping[]): string[] {
  return rows.map(formatMapping).filter((entry) => entry !== "");
}

export function envRows(environment: Record<string, string>): EnvRow[] {
  return Object.entries(environment).map(([key, value]) => ({ key, value: String(value) }));
}

export function envObject(rows: EnvRow[]): Record<string, string> {
  const env: Record<string, string> = {};
  for (const row of rows) if (row.key.trim()) env[row.key.trim()] = row.value;
  return env;
}

export function networkRows(networks: string[]): NetworkRow[] {
  if (networks.length === 0) return [{ type: "default", customName: "" }];
  return networks.map((net) => (PRESET_NETWORKS.includes(net) ? { type: net, customName: "" } : { type: "other", customName: net }));
}

export function networkList(rows: NetworkRow[]): string[] {
  return rows.map((row) => (row.type === "other" ? row.customName.trim() : row.type)).filter((name) => name !== "" && name !== "default");
}

export interface Change {
  section: string;
  kind: "added" | "removed" | "changed" | "cleared";
  item?: string;
  before?: unknown;
  after?: unknown;
  note?: string;
}

const SECTION_TITLES: Record<string, string> = {
  ports: "Ports",
  volumes: "Volumes",
  environment: "Environment",
  networks: "Network",
  capabilities: "Capabilities",
  privileged: "Privileged Mode",
  restartPolicy: "Restart Policy",
};

const show = (value: unknown): string => (Array.isArray(value) ? (value.length ? value.join(", ") : "default") : typeof value === "boolean" ? (value ? "on" : "off") : String(value));

export function describeChange(change: Change): { section: string; text: string } {
  const section = SECTION_TITLES[change.section] ?? change.section;

  if (change.kind === "added") return { section, text: `+ ${change.item}${change.after !== undefined ? ` = ${change.after}` : ""}` };
  if (change.kind === "removed") return { section, text: `− ${change.item}` };
  if (change.kind === "cleared") return { section, text: `− ${change.item}${change.note ? ` (${change.note})` : ""}` };
  return { section, text: `${change.item ? `${change.item}: ` : ""}${show(change.before)} → ${show(change.after)}` };
}
