// homedock-ui/vue3/static/js/__Stores__/useTrashStore.ts
// Copyright © 2023-2026 Banshee, All Rights Reserved
// See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
// https://www.banshee.pro

import { defineStore } from "pinia";

import axios from "axios";

export interface TrashItem {
  id: string;
  location: "storage" | "dropzone";
  stored_name: string;
  name: string;
  original_path: string;
  deleted_at: number;
  expires_at: number;
  size: number;
  size_exceeded: boolean;
  is_directory: boolean;
}

export const useTrashStore = defineStore("trashStore", {
  state: () => ({
    items: [] as TrashItem[],
    retentionDays: 30,
  }),

  actions: {
    async fetch(csrfToken: string) {
      try {
        const response = await axios.get("/api/trash/list", { headers: { "X-HomeDock-CSRF-Token": csrfToken } });
        this.items = Array.isArray(response.data?.items) ? response.data.items : [];
        this.retentionDays = response.data?.retention_days || 30;
      } catch {
        this.items = [];
      }
    },

    async empty(csrfToken: string) {
      try {
        await axios.post("/api/trash/empty", {}, { headers: { "X-HomeDock-CSRF-Token": csrfToken } });
      } finally {
        await this.fetch(csrfToken);
      }
    },
  },
});
