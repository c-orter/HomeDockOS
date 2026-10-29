import { describe, expect, it } from "vitest";

import { orderTargets, useTerminalTabs } from "../useTerminalTabs";

describe("orderTargets", () => {
  it("puts the HomeDock container first and keeps the rest in order", () => {
    const ordered = orderTargets({ homedock: "homedock-os", containers: [{ name: "a" }, { name: "homedock-os" }, { name: "b" }] });

    expect(ordered.map((target) => target.name)).toEqual(["homedock-os", "a", "b"]);
  });

  it("lists every container when HomeDock is not containerised", () => {
    expect(orderTargets({ homedock: null, containers: [{ name: "a" }, { name: "b" }] }).map((target) => target.name)).toEqual(["a", "b"]);
  });
});

describe("useTerminalTabs", () => {
  it("starts empty so the picker shows", () => {
    const { tabs, activeTab } = useTerminalTabs();

    expect(tabs.value).toEqual([]);
    expect(activeTab.value).toBeNull();
  });

  it("starts preselected on a container", () => {
    const { tabs, activeTab } = useTerminalTabs("web");

    expect(tabs.value).toHaveLength(1);
    expect(activeTab.value?.container).toBe("web");
  });

  it("gives every tab its own id, even for the same container", () => {
    const { tabs, open } = useTerminalTabs();

    open("web");
    open("web");

    expect(new Set(tabs.value.map((tab) => tab.id)).size).toBe(2);
  });

  it("activates the new tab, and picks a neighbour when the active one closes", () => {
    const { activeTab, open, close } = useTerminalTabs();
    const first = open("a");
    const second = open("b");
    const third = open("c");

    expect(activeTab.value?.id).toBe(third.id);

    close(third.id);
    expect(activeTab.value?.id).toBe(second.id);

    close(first.id);
    expect(activeTab.value?.id).toBe(second.id);

    close(second.id);
    expect(activeTab.value).toBeNull();
  });
});
