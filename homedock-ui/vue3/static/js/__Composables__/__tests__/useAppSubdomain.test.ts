import { describe, expect, it } from "vitest";

import { isLocalNetworkHost } from "../useAppSubdomain";

describe("isLocalNetworkHost", () => {
  it("treats LAN names and private addresses as local", () => {
    expect(isLocalNetworkHost("homedock.local")).toBe(true);
    expect(isLocalNetworkHost("192.168.1.20")).toBe(true);
    expect(isLocalNetworkHost("localhost")).toBe(true);
  });

  it("treats public names as not local", () => {
    expect(isLocalNetworkHost("apps.example.com")).toBe(false);
  });
});
