// homedock-ui/vue3/static/js/__Composables__/useBrowserAvailability.ts
// Copyright © 2023-2026 Banshee, All Rights Reserved
// See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
// https://www.banshee.pro

import { ref } from "vue";
import axios from "axios";

// The Browser window runs in a container, so it is offered only while the container engine answers.
export const browserAvailable = ref(false);

let requested = false;

// Every request to HomeDock's API carries its CSRF token, GETs included, so the caller passes the one it holds.
export async function loadBrowserAvailability(csrfToken: string) {
  if (requested) return;
  requested = true;

  try {
    const response = await axios.get("/api/browser/status", { headers: { "X-HomeDock-CSRF-Token": csrfToken } });
    browserAvailable.value = !!response.data?.available;
  } catch {
    requested = false;
  }
}
