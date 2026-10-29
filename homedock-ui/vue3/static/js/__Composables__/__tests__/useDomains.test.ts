import { describe, expect, it } from "vitest";

import { addressProblem, cleanNames, domainHealth, errorMessage, nameProblem, normalizeName, openUrl } from "../useDomains";

const cert = (status: "covered" | "excluded" | "pending", reason = "") => ({ name: "x", status, reason });

describe("nameProblem", () => {
  it("accepts a plain domain and normalises case and the trailing dot", () => {
    expect(nameProblem("App.Example.com.", [])).toBe("");
    expect(normalizeName(" App.Example.com. ")).toBe("app.example.com");
  });

  it("rejects empty, wildcard, IP and bare names with a reason", () => {
    expect(nameProblem("", [])).toMatch(/Enter a domain name/);
    expect(nameProblem("*.example.com", [])).toMatch(/Wildcard/);
    expect(nameProblem("192.168.1.5", [])).toMatch(/IP addresses/);
    expect(nameProblem("localhost", [])).toMatch(/full domain name/);
  });

  it("allows homedock.local but no other local names", () => {
    expect(nameProblem("app.homedock.local", [])).toBe("");
    expect(nameProblem("app.lan.local", [])).toMatch(/homedock\.local/);
    expect(nameProblem("app.localhost", [])).toMatch(/homedock\.local/);
  });

  it("rejects a name the app already has", () => {
    expect(nameProblem("a.example.com", ["a.example.com"])).toMatch(/already uses/);
  });
});

describe("domainHealth", () => {
  it("follows certificate coverage, and local names need none", () => {
    expect(domainHealth({ fqdn: "a.example.com", certificate: cert("covered") })).toBe("healthy");
    expect(domainHealth({ fqdn: "a.example.com", certificate: cert("excluded", "why") })).toBe("attention");
    expect(domainHealth({ fqdn: "a.example.com", certificate: cert("pending") })).toBe("pending");
    expect(domainHealth({ fqdn: "a.homedock.local", certificate: cert("excluded") })).toBe("healthy");
  });
});

describe("openUrl and errorMessage", () => {
  it("builds the address with the page's scheme and port, and keeps a path prefix", () => {
    expect(openUrl({ fqdn: "a.example.com", path: "/web" }, { protocol: "https:", port: "" })).toBe("https://a.example.com/web");
    expect(openUrl({ fqdn: "a.example.com", path: "" }, { protocol: "http:", port: "8080" })).toBe("http://a.example.com:8080");
  });

  it("prefers the server's message", () => {
    expect(errorMessage({ response: { data: { message: "x is already used by immich." } } }, "fallback")).toBe("x is already used by immich.");
    expect(errorMessage(new Error("net"), "fallback")).toBe("fallback");
  });
});

describe("install form names", () => {
  it("sends each name once, trimmed and lower-cased, and never a blank", () => {
    expect(cleanNames([" App.Example.com ", "", "app.example.com", "b.example.com."])).toEqual(["app.example.com", "b.example.com"]);
    expect(cleanNames([])).toEqual([]);
  });

  it("reports the first bad row and ignores blank ones", () => {
    expect(addressProblem(["", "  "])).toBe("");
    expect(addressProblem(["ok.example.com", ""])).toBe("");
    expect(addressProblem(["ok.example.com", "nope"])).toMatch(/full domain name/);
    expect(addressProblem(["*.example.com"])).toMatch(/Wildcard/);
  });
});
