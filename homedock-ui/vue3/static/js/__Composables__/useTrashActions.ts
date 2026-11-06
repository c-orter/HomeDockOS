// homedock-ui/vue3/static/js/__Composables__/useTrashActions.ts
// Copyright © 2023-2026 Banshee, All Rights Reserved
// See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
// https://www.banshee.pro

import { useI18n } from "vue-i18n";
import { message } from "ant-design-vue";

import axios from "axios";

import { useCsrfToken } from "./useCsrfToken";
import { useTrashStore, type TrashItem } from "../__Stores__/useTrashStore";
import { announceFilesChanged } from "../__Stores__/useArchiveJobsStore";

export function useTrashActions() {
  const { t } = useI18n();
  const csrfToken = useCsrfToken();
  const trashStore = useTrashStore();

  const headers = () => ({ "X-HomeDock-CSRF-Token": csrfToken.value });

  function announceRestored(restored: { location: "storage" | "dropzone"; path: string }[]) {
    const seen = new Set<string>();
    restored.forEach(({ location, path }) => {
      const folder = path.split("/").slice(0, -1).join("/");
      const key = `${location}|${folder}`;
      if (seen.has(key)) return;
      seen.add(key);
      announceFilesChanged({ location: { source: location }, folder });
    });
  }

  function nameOf(id: string) {
    return trashStore.items.find((item) => item.id === id)?.name || "";
  }

  async function restore(ids: string[]) {
    if (ids.length === 0) return;
    const name = nameOf(ids[0]);
    try {
      const response = await axios.post("/api/trash/restore", { items: ids }, { headers: headers() });
      const restoredItems: { location: "storage" | "dropzone"; path: string }[] = response.data?.restored || [];
      const restored = restoredItems.length;
      const failed = response.data?.failed || [];
      announceRestored(restoredItems);
      if (restored === 1 && ids.length === 1) {
        message.success(t('Restored "{name}"', { name }));
      } else if (restored > 0) {
        message.success(t("Restored {n} items", { n: restored }));
      }
      if (failed.length > 0) {
        message.error(t(failed[0].error || "Restore failed"));
      }
    } catch (error: any) {
      message.error(t(error?.response?.data?.error || "Restore failed"));
    }
    await trashStore.fetch(csrfToken.value);
  }

  async function deleteForever(ids: string[]) {
    if (ids.length === 0) return;
    try {
      const response = await axios.post("/api/trash/delete", { items: ids }, { headers: headers() });
      const deleted = response.data?.deleted?.length || 0;
      const failed = response.data?.failed || [];
      if (deleted > 0) {
        message.success(deleted === 1 ? t("Deleted forever") : t("Deleted {n} items forever", { n: deleted }));
      }
      if (failed.length > 0) {
        message.error(t(failed[0].error || "Failed to delete"));
      }
    } catch (error: any) {
      message.error(t(error?.response?.data?.error || "Failed to delete"));
    }
    await trashStore.fetch(csrfToken.value);
  }

  async function empty() {
    try {
      await trashStore.empty(csrfToken.value);
      message.success(t("Trash emptied"));
    } catch (error: any) {
      message.error(t(error?.response?.data?.error || "Couldn't empty the Trash"));
    }
  }

  function originalFolder(item: TrashItem): string {
    const root = item.location === "dropzone" ? t("Drop Zone") : t("Storage");
    const parent = item.original_path.split("/").slice(0, -1).join("/");
    return parent ? `${root}/${parent}` : root;
  }

  function restoreConfirmText(ids: string[]) {
    const item = ids.length === 1 ? trashStore.items.find((entry) => entry.id === ids[0]) : undefined;
    if (item) {
      return { title: t("Restore this item?"), content: t('"{name}" will go back to {path}.', { name: item.name, path: originalFolder(item) }) };
    }
    return { title: t("Restore {n} items?", { n: ids.length }), content: t("Each one will go back to where it was before you deleted it.") };
  }

  function deleteConfirmText(ids: string[]) {
    if (ids.length === 1) {
      return { title: t("Delete this item forever?"), content: t('"{name}" will leave the Trash for good and can\'t be recovered.', { name: nameOf(ids[0]) }) };
    }
    return { title: t("Delete {n} items forever?", { n: ids.length }), content: t("They will leave the Trash for good and can't be recovered.") };
  }

  return { restore, deleteForever, empty, originalFolder, restoreConfirmText, deleteConfirmText };
}
