// homedock-ui/vue3/static/js/__Composables__/useDomains.ts
// Copyright © 2023-2026 Banshee, All Rights Reserved
// See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
// https://www.banshee.pro

import axios from "axios";

export type DomainMode = "gated" | "direct";

export interface CertificateStatus {
  name: string;
  status: "covered" | "excluded" | "pending";
  reason: string;
}

export interface AppDomain {
  fqdn: string;
  port: number;
  protocol: string;
  path: string;
  mode: DomainMode;
  direct_refusal: string | null;
  certificate: CertificateStatus;
}

export interface AppDomains {
  container: string;
  slug: string;
  web_port: number | null;
  effective_web_port: number | null;
  ports: number[];
  base_domain: string;
  suggestion: string;
  certificate_expires_in_days: number | null;
  reachable: boolean;
  unreachable_reason: string;
  domains: AppDomain[];
}

export interface DnsCheck {
  resolves: boolean;
  reason: string;
}

const FQDN = /^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,62}$/;
const LOCAL_SUFFIX = /\.(local|localhost)$/;

export function normalizeName(value: string): string {
  return value.trim().toLowerCase().replace(/\.$/, "");
}

/** The shape check the server repeats; it alone knows which app owns a taken name, so a 409 message is shown as it comes. */
export function nameProblem(value: string, existing: string[]): string {
  const name = normalizeName(value);

  if (!name) return "Enter a domain name such as app.example.com.";
  if (name.includes("*")) return "Wildcard names are not supported. Add each name on its own.";
  if (/^\d+(\.\d+){3}$/.test(name)) return "IP addresses cannot be used as domains. Use a name.";
  if (LOCAL_SUFFIX.test(name) && !name.endsWith(".homedock.local")) return "Only names under homedock.local are allowed for local use.";
  if (!FQDN.test(name)) return "Enter a full domain name such as app.example.com.";
  if (existing.includes(name)) return "This app already uses that name.";

  return "";
}

export type Health = "healthy" | "attention" | "pending";

export function domainHealth(domain: Pick<AppDomain, "certificate" | "fqdn">): Health {
  if (domain.fqdn.endsWith(".local") || domain.fqdn.endsWith(".localhost")) return "healthy";
  if (domain.certificate.status === "covered") return "healthy";
  if (domain.certificate.status === "excluded") return "attention";

  return "pending";
}

export function openUrl(domain: Pick<AppDomain, "fqdn" | "path">, location: Pick<Location, "protocol" | "port">): string {
  const port = location.port ? `:${location.port}` : "";
  const path = domain.path && domain.path !== "/" ? domain.path : "";

  return `${location.protocol}//${domain.fqdn}${port}${path}`;
}

export function errorMessage(error: unknown, fallback: string): string {
  const message = (error as { response?: { data?: { message?: string } } })?.response?.data?.message;

  return message || fallback;
}

function headers(csrf: string) {
  return { headers: { "X-HomeDock-CSRF-Token": csrf } };
}

export async function fetchDomains(container: string, csrf: string): Promise<AppDomains> {
  const response = await axios.get("/api/domains", { params: { container }, ...headers(csrf) });

  return response.data;
}

export async function addDomain(container: string, fields: { fqdn: string; port: number; mode?: DomainMode }, csrf: string) {
  return (await axios.post("/api/domains/add", { container, ...fields }, headers(csrf))).data.domain as AppDomain;
}

export async function updateDomain(container: string, fqdn: string, changes: { port?: number; mode?: DomainMode; primary?: boolean }, csrf: string) {
  return (await axios.post("/api/domains/update", { container, fqdn, ...changes }, headers(csrf))).data.domain as AppDomain;
}

export async function removeDomain(container: string, fqdn: string, csrf: string) {
  await axios.post("/api/domains/remove", { container, fqdn }, headers(csrf));
}

export async function checkDns(fqdn: string, csrf: string): Promise<DnsCheck> {
  return (await axios.post("/api/domains/check", { fqdn }, headers(csrf))).data;
}

export async function fetchSuggestion(container: string, csrf: string): Promise<{ base_domain: string; suggestion: string }> {
  return (await axios.get("/api/domains/suggestion", { params: { container }, ...headers(csrf) })).data;
}

/** The names an install form would send: trimmed, lower-cased, blanks dropped, repeats kept once. */
export function cleanNames(rows: string[]): string[] {
  const names: string[] = [];

  for (const row of rows) {
    const name = normalizeName(row);

    if (name && !names.includes(name)) names.push(name);
  }

  return names;
}

/** The first thing wrong with the rows, or an empty string; blank rows are not a problem, they are just not sent. */
export function addressProblem(rows: string[]): string {
  for (const row of rows) {
    if (!row.trim()) continue;

    const problem = nameProblem(row, []);

    if (problem) return problem;
  }

  return "";
}
