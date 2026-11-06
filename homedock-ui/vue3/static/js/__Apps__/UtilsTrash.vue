<!-- homedock-ui/vue3/static/js/__Apps__/UtilsTrash.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div ref="rootRef" :class="['trash flex flex-col h-full overflow-hidden outline-hidden', themeClasses.scopeSelector]" tabindex="0" @keydown="handleKeydown">
    <FolderBreadcrumb :icon="trashCanIcon" :name="$t('Trash')" :count="`${items.length} ${items.length === 1 ? $t('item') : $t('items')}`">
      <template #actions>
        <button type="button" :class="[themeClasses.dropZoneSortButton]" class="trash-action h-7 px-2 flex items-center gap-1.5 rounded border text-xs font-medium transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-default" :disabled="items.length === 0" :title="selectedIds.length > 0 ? $t('Restore Selected Items') : $t('Restore All Items')" @click="requestRestore(selectedIds.length > 0 ? selectedIds : orderedIds)">
          <Icon :icon="deleteRestoreIcon" class="w-4 h-4 flex-shrink-0" />
          <span class="trash-action-label">{{ selectedIds.length > 0 ? $t("Restore Selected Items") : $t("Restore All Items") }}</span>
        </button>
        <button v-if="selectedIds.length > 0" type="button" :class="[themeClasses.dropZoneSortButton]" class="trash-action h-7 px-2 flex items-center gap-1.5 rounded border text-xs font-medium transition-colors cursor-pointer" :title="$t('Delete Permanently')" @click="requestDelete(selectedIds)">
          <Icon :icon="deleteForeverIcon" class="w-4 h-4 flex-shrink-0 text-red-500" />
          <span class="trash-action-label text-red-500">{{ $t("Delete Permanently") }}</span>
        </button>
        <button type="button" :class="[themeClasses.dropZoneSortButton]" class="trash-action h-7 px-2 flex items-center gap-1.5 rounded border text-xs font-medium transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-default" :disabled="items.length === 0" :title="$t('Empty Trash')" @click="requestEmpty">
          <Icon :icon="deleteEmptyIcon" class="w-4 h-4 flex-shrink-0 text-red-500" />
          <span class="trash-action-label text-red-500">{{ $t("Empty Trash") }}</span>
        </button>
        <button type="button" :class="[themeClasses.dropZoneSortButton]" class="h-7 w-7 rounded border transition-colors flex items-center justify-center cursor-pointer" :title="$t('Open in File Explorer')" @click="showInExplorer()">
          <Icon :icon="folderOpenIcon" class="w-4 h-4" />
        </button>
      </template>
    </FolderBreadcrumb>

    <div ref="contentRef" class="relative flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-3 py-2 select-none" @mousedown="handleAreaMouseDown" @contextmenu.prevent="openMenu($event, null)">
      <SelectionBox :visible="isSelectingArea" :style="selectionBoxStyle" />

      <div v-if="!loaded" class="flex flex-col items-center justify-center h-full text-center py-12">
        <Icon :icon="loadingIcon" :class="[themeClasses.dropZoneFileIcon]" class="w-12 h-12 animate-spin mb-4" />
      </div>

      <div v-else-if="items.length === 0" class="flex flex-col items-center justify-center h-full text-center py-12 pointer-events-none">
        <AppIconGraphic :icon="trashCanIcon" color="#64748b" :size="64" class="opacity-60 mb-4" />
        <p :class="[themeClasses.dropZoneEmptyText]" class="text-sm font-medium">{{ $t("The Trash is empty.") }}</p>
      </div>

      <template v-else>
        <section v-for="group in groups" :key="group.key" class="mb-3">
          <header :class="[themeClasses.fileExplorerSidebarSectionTitle]" class="flex items-center gap-2 px-1 py-1.5 mb-1 text-xs font-semibold">
            <AppIconGraphic :icon="group.icon" :color="group.color" :size="18" />
            <span class="opacity-80">{{ group.label }}</span>
            <span class="opacity-50 font-normal">{{ group.items.length }}</span>
          </header>
          <div class="flex flex-wrap gap-1">
            <div v-for="item in group.items" :key="item.id" :data-select-id="item.id" :title="$t('Originally in {path}', { path: originalFolder(item) })" :class="['trash-item relative inline-flex flex-col items-center gap-1 p-2 rounded-lg border w-[100px] h-[120px] cursor-pointer transition-[background,border] duration-150', selected.has(item.id) ? [themeClasses.desktopIconBgSelected, themeClasses.desktopIconBorderSelected] : ['border-transparent', themeClasses.desktopIconBg]]" @click="handleItemClick(item, $event)" @dblclick="showInExplorer(item.id)" @contextmenu.prevent.stop="openMenu($event, item)">
              <span class="relative w-16 h-16 flex-shrink-0 flex items-center justify-center pointer-events-none">
                <span :class="[themeClasses.dropZoneFileSize]" class="absolute -left-1 -bottom-1 z-10 text-[8px] font-medium px-1 py-0.5 rounded whitespace-nowrap">{{ daysLeft(item) }}d</span>
                <Icon v-if="item.location === 'dropzone' && !item.is_directory" :icon="lockIcon" :class="[themeClasses.dropZoneLockIcon]" class="absolute -right-1 -top-1 h-3 w-3" />
                <FolderGraphic v-if="item.is_directory" />
                <FileThumbnail v-else :request="thumbnailRequest(item)" class="w-14 h-14"><FileGraphic :name="item.name" /></FileThumbnail>
              </span>
              <FileNameLabel :name="item.name" :class="[themeClasses.dropZoneFileText]" class="text-[11px] leading-tight text-center line-clamp-2 w-full px-1 break-words pointer-events-none" />
            </div>
          </div>
        </section>
      </template>
    </div>

    <div :class="['trash-details flex items-center gap-3 px-4 h-[72px] border-t flex-shrink-0', themeClasses.utilityToolbarBorder]">
      <span class="relative w-12 h-12 flex-shrink-0 flex items-center justify-center">
        <template v-if="detailItem">
          <FolderGraphic v-if="detailItem.is_directory" :size="48" />
          <FileThumbnail v-else :key="detailItem.id" :request="thumbnailRequest(detailItem)" class="w-12 h-12"><FileGraphic :name="detailItem.name" :size="48" /></FileThumbnail>
        </template>
        <AppIconGraphic v-else :icon="trashCanIcon" color="#64748b" :size="42" />
        <CountBadge v-if="selectedIds.length > 1" :count="selectedIds.length" />
      </span>
      <div class="min-w-0 flex-1">
        <template v-if="detailItem">
          <p :class="[themeClasses.statusBarText]" class="text-[13px] font-semibold truncate">{{ detailItem.name }}</p>
          <p :class="[themeClasses.statusBarInfo]" class="text-[11px] truncate">{{ $t("Originally in {path}", { path: originalFolder(detailItem) }) }}</p>
          <p :class="[themeClasses.statusBarInfo]" class="text-[11px] truncate">
            {{ $t("Deleted on {date}", { date: formatDate(detailItem.deleted_at) }) }} · {{ $t("{n} days left", { n: daysLeft(detailItem) }) }}<template v-if="!detailItem.is_directory || detailItem.size > 0"> · {{ formatSize(detailItem.size) }}</template>
          </p>
        </template>
        <template v-else-if="selectedIds.length > 1">
          <p :class="[themeClasses.statusBarText]" class="text-[13px] font-semibold truncate">{{ $t("{n} items selected", { n: selectedIds.length }) }}</p>
          <p :class="[themeClasses.statusBarInfo]" class="text-[11px] truncate">{{ formatSize(selectedSize) }}</p>
        </template>
        <template v-else>
          <p :class="[themeClasses.statusBarText]" class="text-[13px] font-semibold truncate">{{ $t("Trash") }}</p>
          <p :class="[themeClasses.statusBarInfo]" class="text-[11px] truncate">
            {{ items.length }} {{ items.length === 1 ? $t("item") : $t("items") }}<template v-if="items.length > 0"> · {{ formatSize(totalSize) }}</template>
          </p>
          <p :class="[themeClasses.statusBarInfo]" class="text-[11px] truncate">{{ $t("Items are deleted permanently after {n} days", { n: trashStore.retentionDays }) }}</p>
        </template>
      </div>
    </div>

    <StatusBar :icon="trashCanIcon" :message="statusMessage" :info="statusInfo" :showHelp="true">
      <template #help>
        <div class="space-y-2.5 max-w-sm">
          <div class="flex items-center gap-2">
            <StatusBarHelpIcon :icon="trashCanIcon" />
            <h4 :class="['text-base font-semibold', themeClasses.statusBarText]">{{ $t("Trash") }}</h4>
          </div>
          <div :class="['text-[10px] md:text-xs md:leading-4 space-y-2 leading-relaxed', themeClasses.statusBarInfo]">
            <p>{{ $t("Files you delete in Storage and the Drop Zone wait here for {n} days before they are deleted for good.", { n: trashStore.retentionDays }) }}</p>
            <p>{{ $t("Restore puts an item back where it was. If something else took its name in the meantime, it comes back with a number added instead of overwriting anything.") }}</p>
            <p>{{ $t("Drop Zone items stay encrypted while they wait.") }}</p>
          </div>
        </div>
      </template>
    </StatusBar>

    <ContextMenu :visible="menu.visible" :x="menu.x" :y="menu.y" :items="menuItems" @close="menu.visible = false" />
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import { useTheme } from "../__Themes__/ThemeSelector";
import { useCsrfToken } from "../__Composables__/useCsrfToken";
import { useDialog } from "../__Composables__/useDialog";
import { useTrashActions } from "../__Composables__/useTrashActions";
import { useAreaSelection } from "../__Composables__/useAreaSelection";
import { THUMBNAIL_EXTENSIONS, thumbnailExtension, type ThumbnailRequest } from "../__Composables__/useThumbnails";
import { useTrashStore, type TrashItem } from "../__Stores__/useTrashStore";
import { useWindowStore } from "../__Stores__/windowStore";

import AppIconGraphic from "../__Components__/AppIconGraphic.vue";
import CountBadge from "../__Components__/CountBadge.vue";
import FileGraphic from "../__Components__/FileGraphic.vue";
import FolderGraphic from "../__Components__/FolderGraphic.vue";
import FileThumbnail from "../__Components__/FileThumbnail.vue";
import FileNameLabel from "../__Components__/FileNameLabel.vue";
import SelectionBox from "../__Components__/SelectionBox.vue";
import FolderBreadcrumb from "../__Components__/FolderBreadcrumb.vue";
import StatusBar from "../__Components__/StatusBar.vue";
import StatusBarHelpIcon from "../__Components__/StatusBarHelpIcon.vue";
import ContextMenu, { type ContextMenuItem } from "../__Components__/ContextMenu.vue";

import { Icon } from "@iconify/vue";
import folderIcon from "@iconify-icons/mdi/folder";
import cubeIcon from "@iconify-icons/mdi/cube";
import lockIcon from "@iconify-icons/mdi/lock";
import folderOpenIcon from "@iconify-icons/mdi/folder-open";
import deleteEmptyIcon from "@iconify-icons/mdi/delete-empty";
import deleteRestoreIcon from "@iconify-icons/mdi/delete-restore";
import deleteForeverIcon from "@iconify-icons/mdi/delete-forever";
import selectAllIcon from "@iconify-icons/mdi/select-all";
import refreshIcon from "@iconify-icons/mdi/refresh";
import trashCanIcon from "@iconify-icons/mdi/trash-can";
import loadingIcon from "@iconify-icons/mdi/loading";

const { t, locale } = useI18n();
const { themeClasses } = useTheme();
const csrfToken = useCsrfToken();
const { confirm } = useDialog();
const trashStore = useTrashStore();
const trashActions = useTrashActions();
const windowStore = useWindowStore();

const DAY_SECONDS = 86400;

const LOCATIONS = [
  { key: "storage", label: "Storage", icon: folderIcon, color: "#0ea5e9" },
  { key: "dropzone", label: "Drop Zone (Encrypted)", icon: cubeIcon, color: "#4f46e5" },
] as const;

const rootRef = ref<HTMLElement | null>(null);
const contentRef = ref<HTMLElement | null>(null);
const loaded = ref(false);
const selected = ref(new Set<string>());
const anchorId = ref<string | null>(null);
const menu = reactive({ visible: false, x: 0, y: 0, item: null as TrashItem | null });

const {
  isSelectingArea,
  selectionBoxStyle,
  handleMouseDown: startAreaSelection,
  consumeDragClick,
} = useAreaSelection({
  containerRef: contentRef,
  getSelection: () => selected.value,
  setSelection: (ids) => {
    selected.value = ids;
    anchorId.value = null;
  },
  enabled: () => items.value.length > 0,
  startOnItems: true,
});

const items = computed(() => trashStore.items);

const groups = computed(() =>
  LOCATIONS.map((location) => ({
    key: location.key,
    label: t(location.label),
    icon: location.icon,
    color: location.color,
    items: items.value.filter((item) => item.location === location.key),
  })).filter((group) => group.items.length > 0),
);

const orderedIds = computed(() => groups.value.flatMap((group) => group.items.map((item) => item.id)));

const selectedIds = computed(() => orderedIds.value.filter((id) => selected.value.has(id)));

const totalSize = computed(() => items.value.reduce((sum, item) => sum + (item.size || 0), 0));

const selectedSize = computed(() => items.value.filter((item) => selected.value.has(item.id)).reduce((sum, item) => sum + (item.size || 0), 0));

const detailItem = computed(() => (selectedIds.value.length === 1 ? (items.value.find((item) => item.id === selectedIds.value[0]) ?? null) : null));

const statusMessage = computed(() => (selectedIds.value.length > 0 ? t("{n} of {total} selected", { n: selectedIds.value.length, total: items.value.length }) : t("Trash")));

const statusInfo = computed(() => `${items.value.length} ${items.value.length === 1 ? t("item") : t("items")}`);

watch(items, (current) => {
  const alive = new Set(current.map((item) => item.id));
  selected.value = new Set([...selected.value].filter((id) => alive.has(id)));
});

function formatSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

function formatDate(seconds: number): string {
  return new Intl.DateTimeFormat(String(locale.value), { dateStyle: "medium", timeStyle: "short" }).format(new Date(seconds * 1000));
}

const { originalFolder } = trashActions;

function daysLeft(item: TrashItem): number {
  return Math.max(0, Math.ceil((item.expires_at - Date.now() / 1000) / DAY_SECONDS));
}

function thumbnailRequest(item: TrashItem): ThumbnailRequest | null {
  if (item.is_directory || item.size <= 0 || !THUMBNAIL_EXTENSIONS.has(thumbnailExtension(item.name))) return null;
  const path = `.Trash/files/${item.stored_name}`;
  const version = `${item.deleted_at}-${item.size}`;
  return { key: `${item.location}|${path}|${version}`, url: `/api/${item.location}/thumbnail`, params: { file: path, v: version } };
}

function clearSelection() {
  selected.value = new Set();
  anchorId.value = null;
}

function selectOnly(id: string) {
  selected.value = new Set([id]);
  anchorId.value = id;
}

function selectAll() {
  selected.value = new Set(orderedIds.value);
}

function handleItemClick(item: TrashItem, event: MouseEvent) {
  if (consumeDragClick()) return;
  rootRef.value?.focus();
  if (event.shiftKey && anchorId.value) {
    const ids = orderedIds.value;
    const from = ids.indexOf(anchorId.value);
    const to = ids.indexOf(item.id);
    const [start, end] = from < to ? [from, to] : [to, from];
    selected.value = new Set(ids.slice(start, end + 1));
    return;
  }
  if (event.metaKey || event.ctrlKey) {
    const next = new Set(selected.value);
    if (next.has(item.id)) next.delete(item.id);
    else next.add(item.id);
    selected.value = next;
    anchorId.value = item.id;
    return;
  }
  selectOnly(item.id);
}

function handleAreaMouseDown(event: MouseEvent) {
  rootRef.value?.focus();
  startAreaSelection(event);
}

function showInExplorer(itemId?: string) {
  menu.visible = false;
  windowStore.openFileInApp("fileexplorer", { data: { initialLocation: "trash", initialFileName: itemId } });
}

async function restore(ids: string[]) {
  menu.visible = false;
  if (ids.length === 0) return;
  await trashActions.restore(ids);
}

function requestRestore(ids: string[]) {
  menu.visible = false;
  if (ids.length === 0) return;
  const { title, content } = trashActions.restoreConfirmText(ids);
  confirm({ title, content, okText: "Restore", cancelText: "Cancel", onOk: () => restore(ids) });
}

function requestDelete(ids: string[]) {
  menu.visible = false;
  if (ids.length === 0) return;
  const { title, content } = trashActions.deleteConfirmText(ids);
  confirm({ title, content, okText: "Delete Permanently", cancelText: "Cancel", onOk: () => trashActions.deleteForever(ids) });
}

function requestEmpty() {
  menu.visible = false;
  confirm({
    title: "Empty the Trash?",
    content: "Everything in the Trash will be deleted and can't be recovered.",
    okText: "Empty Trash",
    cancelText: "Cancel",
    onOk: trashActions.empty,
  });
}

function openMenu(event: MouseEvent, item: TrashItem | null) {
  if (item && !selected.value.has(item.id)) selectOnly(item.id);
  if (!item) clearSelection();
  menu.item = item;
  menu.x = event.clientX;
  menu.y = event.clientY;
  menu.visible = true;
}

const menuItems = computed<ContextMenuItem[]>(() => {
  const ids = selectedIds.value;
  if (menu.item && ids.length > 0) {
    return [{ label: "Restore", icon: deleteRestoreIcon, action: () => requestRestore(ids) }, ...(ids.length === 1 ? [{ label: "Show in File Explorer", icon: folderOpenIcon, action: () => showInExplorer(ids[0]) }] : []), { divider: true }, { label: "Delete Permanently", icon: deleteForeverIcon, danger: true, action: () => requestDelete(ids) }];
  }
  return [{ label: "Select All", icon: selectAllIcon, disabled: items.value.length === 0, action: () => ((menu.visible = false), selectAll()) }, { label: "Restore All Items", icon: deleteRestoreIcon, disabled: items.value.length === 0, action: () => requestRestore(orderedIds.value) }, { label: "Open in File Explorer", icon: folderOpenIcon, action: () => showInExplorer() }, { divider: true }, { label: "Empty Trash", icon: deleteEmptyIcon, danger: true, disabled: items.value.length === 0, action: requestEmpty }, { divider: true }, { label: "Refresh", icon: refreshIcon, action: () => ((menu.visible = false), trashStore.fetch(csrfToken.value)) }];
});

function handleKeydown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "a") {
    event.preventDefault();
    selectAll();
  } else if (event.key === "Delete" || (event.key === "Backspace" && (event.metaKey || event.ctrlKey))) {
    event.preventDefault();
    requestDelete(selectedIds.value);
  } else if (event.key === "Enter" && selectedIds.value.length === 1) {
    event.preventDefault();
    showInExplorer(selectedIds.value[0]);
  }
}

onMounted(async () => {
  await trashStore.fetch(csrfToken.value);
  loaded.value = true;
});
</script>

<style scoped>
.trash-details {
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.9) 0%, rgba(241, 245, 249, 0.95) 100%);
}

.trash.dark-mode-theme .trash-details {
  background: linear-gradient(180deg, rgba(39, 39, 42, 0.6) 0%, rgba(24, 24, 27, 0.7) 100%);
}

.trash.aero-mode-theme .trash-details {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.03) 100%);
}

@container window (max-width: 700px) {
  .trash-action-label {
    display: none;
  }

  .trash-action {
    width: 28px;
    padding: 0;
    justify-content: center;
  }
}
</style>
