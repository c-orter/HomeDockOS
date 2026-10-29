import { describe, expect, it } from "vitest";

import { describeChange, envObject, envRows, formatMapping, formatMappings, networkList, networkRows, parseMapping, parseVolume } from "../useComposeForm";

describe("ports and volumes round-trip", () => {
  const ports = ["18080:80", "127.0.0.1:18443:443/tcp", "80", "53:53/udp"];

  it("keeps every port entry exactly", () => {
    expect(formatMappings(ports.map(parseMapping))).toEqual(ports);
  });

  it("splits on the last colon so the bind address stays with the host side", () => {
    expect(parseMapping("127.0.0.1:18443:443/tcp")).toEqual({ host: "127.0.0.1:18443", container: "443/tcp" });
    expect(parseMapping("80")).toEqual({ host: "", container: "80" });
  });

  it("keeps volumes with modes and named volumes", () => {
    const volumes = ["/srv/a:/a", "media:/media:ro", "/anonymous"];
    expect(volumes.map(parseVolume).map(formatMapping)).toEqual(volumes);
    expect(parseVolume("media:/media:ro")).toEqual({ host: "media", container: "/media:ro" });
  });

  it("drops empty rows", () => {
    expect(formatMappings([{ host: "", container: "" }, { host: "1", container: "2" }])).toEqual(["1:2"]);
  });
});

describe("environment", () => {
  it("keeps empty values and trims names", () => {
    expect(envObject([{ key: " A ", value: "" }, { key: "", value: "x" }, { key: "B", value: "1" }])).toEqual({ A: "", B: "1" });
    expect(envRows({ A: "1" })).toEqual([{ key: "A", value: "1" }]);
  });
});

describe("networks", () => {
  it("shows no networks as the default and writes them back as none", () => {
    expect(networkRows([])).toEqual([{ type: "default", customName: "" }]);
    expect(networkList(networkRows([]))).toEqual([]);
  });

  it("round-trips presets and custom names", () => {
    expect(networkList(networkRows(["homedock_network", "backend"]))).toEqual(["homedock_network", "backend"]);
    expect(networkRows(["backend"])).toEqual([{ type: "other", customName: "backend" }]);
  });
});

describe("describeChange", () => {
  it("renders each kind", () => {
    expect(describeChange({ section: "ports", kind: "added", item: "1:1" })).toEqual({ section: "Ports", text: "+ 1:1" });
    expect(describeChange({ section: "environment", kind: "added", item: "A", after: "1" }).text).toBe("+ A = 1");
    expect(describeChange({ section: "volumes", kind: "removed", item: "/a:/a" }).text).toBe("− /a:/a");
    expect(describeChange({ section: "environment", kind: "changed", item: "TZ", before: "UTC", after: "CET" }).text).toBe("TZ: UTC → CET");
    expect(describeChange({ section: "privileged", kind: "changed", before: false, after: true }).text).toBe("off → on");
    expect(describeChange({ section: "networks", kind: "changed", before: [], after: ["host"] }).text).toBe("default → host");
    expect(describeChange({ section: "ports", kind: "cleared", item: "published ports", note: "Host networking ignores published ports" }).text).toContain("Host networking");
  });
});
