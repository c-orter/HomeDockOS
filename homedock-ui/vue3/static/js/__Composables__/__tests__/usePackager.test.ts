import { describe, expect, it } from "vitest";

import { buildPackageForm, registerFailure, COMPOSE_WARNINGS } from "../usePackager";

const pkg = { slug: "demo", display_name: "Demo", category: "Media", type: "Application", description: "d", docker_image: "nginx", author: "me", version: "latest", default_username: "u", default_password: "p", suggested_port: "8080", suggested_trail: "admin" };
const compose = new File(["services: {}"], "docker-compose.yml");
const icon = new File(["x"], "icon.png");

describe("buildPackageForm", () => {
  it("carries the metadata and both files", () => {
    const form = buildPackageForm({ pkg, compose, icon, credentials: false, port: false, trail: false });

    expect(form.get("slug")).toBe("demo");
    expect(form.get("version")).toBe("latest");
    expect((form.get("compose") as File).name).toBe("docker-compose.yml");
    expect((form.get("icon") as File).name).toBe("icon.png");
    expect(form.has("default_username")).toBe(false);
    expect(form.has("suggested_port")).toBe(false);
    expect(form.has("suggested_trail")).toBe(false);
    expect(form.has("overwrite")).toBe(false);
  });

  it("adds the optional parts only when enabled", () => {
    const form = buildPackageForm({ pkg, compose, icon, credentials: true, port: true, trail: true, overwrite: true });

    expect(form.get("default_username")).toBe("u");
    expect(form.get("default_password")).toBe("p");
    expect(form.get("suggested_port")).toBe("8080");
    expect(form.get("suggested_trail")).toBe("admin");
    expect(form.get("overwrite")).toBe("true");
  });
});

describe("registerFailure", () => {
  it("maps the server's conflict codes", () => {
    expect(registerFailure({ response: { data: { code: "APP_INSTALLED" } } })).toBe("installed");
    expect(registerFailure({ response: { data: { code: "PACKAGE_EXISTS" } } })).toBe("exists");
  });

  it("treats anything else as a plain failure", () => {
    expect(registerFailure({ response: { data: { message: "x" } } })).toBe("failed");
    expect(registerFailure(new Error("network"))).toBe("failed");
    expect(registerFailure(undefined)).toBe("failed");
  });
});

describe("COMPOSE_WARNINGS", () => {
  it("has text for every code the server sends", () => {
    for (const code of ["privileged", "docker_socket", "host_root"]) expect(COMPOSE_WARNINGS[code]).toBeTruthy();
  });
});
