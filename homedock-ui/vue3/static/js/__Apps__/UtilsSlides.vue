<!-- homedock-ui/vue3/static/js/__Apps__/UtilsSlides.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div class="utils-slides flex flex-col h-full overflow-hidden">
    <div class="toolbar flex items-center gap-1 px-2 py-1.5 border-b flex-shrink-0" :class="themeClasses.utilityToolbarBorder">
      <Dropdown :trigger="['click']" placement="bottomLeft" :overlay-class-name="menuOverlayClass">
        <button :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="px-3 py-1 text-xs rounded transition-colors cursor-pointer">{{ $t("File") }}</button>
        <template #overlay>
          <Menu>
            <MenuItem key="download" :disabled="!presentation" @click="downloadOriginal">
              <div class="flex items-center gap-2">
                <Icon :icon="downloadIcon" class="w-4 h-4" />
                <span>{{ $t("Download") }}</span>
              </div>
            </MenuItem>
            <MenuDivider />
            <MenuItem key="browse" @click="browseDocuments">
              <div class="flex items-center gap-2">
                <Icon :icon="folderFileIcon" class="w-4 h-4" />
                <span>{{ $t("Browse Documents") }}</span>
              </div>
            </MenuItem>
            <MenuItem key="exit" @click="closeWindow">
              <div class="flex items-center gap-2">
                <Icon :icon="exitIcon" class="w-4 h-4" />
                <span>{{ $t("Exit") }}</span>
              </div>
            </MenuItem>
          </Menu>
        </template>
      </Dropdown>

      <div class="w-px h-4 mx-0.5" :class="themeClasses.utilityDivider"></div>

      <button :disabled="!presentation" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover, showSidebar && presentation ? 'bg-blue-500/20' : '']" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Sidebar')" @click="showSidebar = !showSidebar">
        <Icon :icon="sidebarIcon" class="w-4 h-4" />
      </button>

      <button :disabled="currentIndex <= 0" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Previous Slide')" @click="previousSlide">
        <Icon :icon="chevronLeftIcon" class="w-4 h-4" />
      </button>
      <div class="flex items-center gap-1">
        <input v-model="slideInput" :disabled="!presentation" type="text" inputmode="numeric" :class="[themeClasses.windowInputBg, themeClasses.windowText, themeClasses.windowBorder]" class="w-9 h-6 px-1 text-xs text-center rounded border outline-hidden tabular-nums" :aria-label="$t('Slide')" @keydown.enter="goToSlideInput" @blur="slideInput = String(currentIndex + 1)" />
        <span :class="['text-xs whitespace-nowrap tabular-nums', themeClasses.windowTextMuted]">/ {{ slideCount }}</span>
      </div>
      <button :disabled="currentIndex >= slideCount - 1" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Next Slide')" @click="nextSlide">
        <Icon :icon="chevronRightIcon" class="w-4 h-4" />
      </button>

      <div class="flex-1"></div>

      <button :disabled="!presentation" :class="themeClasses.storeCardGetPill" class="present-button flex items-center justify-center gap-1.5 h-7 px-3.5 rounded-full border-0 text-xs font-semibold cursor-pointer flex-shrink-0 transition-colors duration-150 disabled:opacity-40 disabled:cursor-default" :title="$t('Present (F5)')" @click="startPresenting">
        <Icon :icon="presentIcon" class="w-3.5 h-3.5 flex-shrink-0" />
        <span class="present-label">{{ $t("Present") }}</span>
      </button>
    </div>

    <div class="flex flex-1 min-h-0">
      <aside v-if="showSidebar && presentation" ref="sidebarRef" class="slides-sidebar flex-shrink-0 w-48 overflow-y-auto border-r px-3 py-3 space-y-3" :class="themeClasses.fileExplorerSidebar">
        <button v-for="index in slideIndices" :key="`${revision}-${index}`" :data-slide="index" type="button" class="thumbnail-item flex flex-col items-center gap-1.5 w-full bg-transparent border-0 p-0 cursor-pointer" @click="goToSlide(index)">
          <span :ref="(el) => observeThumbnail(el as HTMLElement | null, index)" class="thumbnail-frame block overflow-hidden bg-white rounded-[3px]" :class="{ active: index === currentIndex }" :style="thumbnailStyle"></span>
          <span class="text-[11px] tabular-nums px-1.5 rounded" :class="index === currentIndex ? 'bg-blue-500 text-white' : themeClasses.windowTextMuted">{{ index + 1 }}</span>
        </button>
      </aside>

      <div ref="stageRef" class="slides-stage relative flex-1 min-w-0 flex items-center justify-center overflow-hidden" :class="themeClasses.imageViewerBg" @dragenter.prevent.stop="onDragEnter" @dragover.prevent.stop="onDragOver" @dragleave.stop="onDragLeave" @drop.prevent.stop="onDrop">
        <div v-show="presentation && !isLoading && !error" ref="slideRef" class="slide-canvas bg-white"></div>

        <Transition name="drop-fade">
          <div v-if="isDragOver" class="absolute inset-3 z-10 flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-blue-500 bg-blue-500/10 pointer-events-none">
            <Icon :icon="slidesIcon" class="w-10 h-10 text-blue-500" />
            <span class="text-sm font-semibold text-blue-500">{{ $t("Drop to open") }}</span>
          </div>
        </Transition>

        <div v-if="isLoading" class="absolute inset-0 flex items-center justify-center">
          <div class="flex flex-col items-center gap-3">
            <Icon :icon="loadingIcon" class="w-8 h-8 animate-spin" :class="themeClasses.windowTextMuted" />
            <span :class="['text-sm', themeClasses.windowTextMuted]">{{ $t("Loading presentation...") }}</span>
          </div>
        </div>

        <div v-else-if="error" class="absolute inset-0 flex items-center justify-center">
          <div class="flex flex-col items-center gap-3 text-center p-8">
            <div class="w-16 h-16 rounded-2xl flex items-center justify-center bg-red-500/10">
              <Icon :icon="alertIcon" class="w-8 h-8 text-red-500" />
            </div>
            <h3 :class="['text-lg font-medium', themeClasses.windowText]">{{ $t("Cannot Display Presentation") }}</h3>
            <p :class="['text-sm max-w-xs', themeClasses.windowTextMuted]">{{ error }}</p>
          </div>
        </div>

        <div v-else-if="!presentation" class="absolute inset-0 flex items-center justify-center">
          <div class="flex flex-col items-center gap-3 text-center p-8">
            <div class="w-16 h-16 rounded-2xl flex items-center justify-center" :class="themeClasses.imageViewerBg">
              <Icon :icon="slidesIcon" class="w-8 h-8" :class="themeClasses.windowTextMuted" />
            </div>
            <h3 :class="['text-lg font-medium', themeClasses.windowText]">{{ $t("No Presentation") }}</h3>
            <p :class="['text-sm max-w-xs', themeClasses.windowTextMuted]">{{ $t("Open a PowerPoint presentation (.pptx) to view it here.") }}</p>
            <button type="button" :class="[themeClasses.storeCardGetPill]" class="flex items-center gap-1.5 h-8 mt-1 px-4 rounded-full border-0 text-xs font-semibold cursor-pointer transition-colors duration-150" @click="browseDocuments">
              <Icon :icon="folderFileIcon" class="w-4 h-4" />
              {{ $t("Browse Documents") }}
            </button>
            <span :class="['text-xs', themeClasses.windowTextMuted]">{{ $t("or drop a presentation here") }}</span>
          </div>
        </div>
      </div>
    </div>

    <StatusBar :icon="slidesIcon" :message="fileName || $t('No Presentation')" :info="slideCount > 0 ? $t('Slide {n} of {total}', { n: currentIndex + 1, total: slideCount }) : ''" :show-help="true">
      <template #help>
        <div class="space-y-2.5 max-w-sm">
          <div class="flex items-center gap-2">
            <StatusBarHelpIcon :icon="slidesIcon" />
            <h4 :class="['text-base font-semibold', themeClasses.statusBarText]">{{ $t("Slides") }}</h4>
          </div>
          <div :class="['text-[10px] md:text-xs md:leading-4 space-y-2 leading-relaxed', themeClasses.statusBarInfo]">
            <p>{{ $t("Slides opens PowerPoint presentations (.pptx) for viewing. Use the arrow keys to move between slides and Present (F5) to show them full screen.") }}</p>
            <p>{{ $t("Fonts that are not installed are replaced with similar ones, so some slides may look slightly different from PowerPoint.") }}</p>
          </div>
        </div>
      </template>
    </StatusBar>

    <Teleport to="body">
      <div v-if="isPresenting" ref="presenterRef" class="slides-presenter" @click="nextSlide" @contextmenu.prevent="previousSlide">
        <div ref="presenterSlideRef" class="bg-white"></div>
        <button type="button" class="presenter-close" :title="$t('Close')" @click.stop="stopPresenting">
          <Icon :icon="closeIcon" class="w-5 h-5" />
        </button>
        <span class="presenter-counter">{{ currentIndex + 1 }} / {{ slideCount }}</span>
      </div>
    </Teleport>
  </div>
</template>

<script lang="ts" setup>
import { ref, shallowRef, computed, onMounted, onUnmounted, watch, nextTick } from "vue";
import { useI18n } from "vue-i18n";

import { Dropdown, Menu, MenuItem, MenuDivider } from "ant-design-vue";

import type { LoadedPresentation } from "pptx-viewer";

import { Icon } from "@iconify/vue";
import slidesIcon from "@iconify-icons/mdi/file-presentation-box";
import chevronLeftIcon from "@iconify-icons/mdi/chevron-left";
import chevronRightIcon from "@iconify-icons/mdi/chevron-right";
import sidebarIcon from "@iconify-icons/mdi/page-layout-sidebar-left";
import presentIcon from "@iconify-icons/mdi/presentation-play";
import downloadIcon from "@iconify-icons/mdi/download";
import folderFileIcon from "@iconify-icons/mdi/folder-file";
import exitIcon from "@iconify-icons/mdi/exit-to-app";
import loadingIcon from "@iconify-icons/mdi/loading";
import alertIcon from "@iconify-icons/mdi/alert-circle-outline";
import closeIcon from "@iconify-icons/mdi/close";

import { useTheme } from "../__Themes__/ThemeSelector";
import { useWindowStore } from "../__Stores__/windowStore";
import { useResponsive } from "../__Composables__/useResponsive";
import { triggerDownload, type ExternalBinaryFile } from "../__Composables__/useExternalFile";

import StatusBar from "../__Components__/StatusBar.vue";
import StatusBarHelpIcon from "../__Components__/StatusBarHelpIcon.vue";

const PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation";

const ZIP_MAGIC_BYTES = [0x50, 0x4b, 0x03, 0x04];

const DOCUMENTS_FOLDER = "Documents";

const THUMBNAIL_WIDTH = 152;

const STAGE_PADDING = 24;

const SAFE_LINK = /^(https?:|mailto:)/i;

const SAFE_IMAGE = /^(data:image\/|blob:|#)/i;

const BLOCKED_TAGS = new Set(["script", "iframe", "object", "embed", "link", "meta", "style", "base", "form"]);

const URL_ATTRIBUTES = new Set(["href", "xlink:href", "src", "action", "formaction"]);

const props = defineProps<{ _windowId?: string; slidesFile?: ExternalBinaryFile }>();

const { themeClasses } = useTheme();
const { t } = useI18n();
const windowStore = useWindowStore();
const { isDesktopOrWider } = useResponsive();

const stageRef = ref<HTMLElement | null>(null);
const slideRef = ref<HTMLElement | null>(null);
const sidebarRef = ref<HTMLElement | null>(null);
const presenterRef = ref<HTMLElement | null>(null);
const presenterSlideRef = ref<HTMLElement | null>(null);

const presentation = shallowRef<LoadedPresentation | null>(null);
const originalBuffer = shallowRef<ArrayBuffer | null>(null);
const fileName = ref("");
const originalWindowTitle = props._windowId ? windowStore.getWindowById(props._windowId)?.title || "" : "";
const isLoading = ref(false);
const error = ref<string | null>(null);
const currentIndex = ref(0);
const slideInput = ref("1");
const revision = ref(0);
const showSidebar = ref(isDesktopOrWider.value);
const isPresenting = ref(false);

const isDragOver = ref(false);
let dragDepth = 0;

let loadToken = 0;
let stageObserver: ResizeObserver | null = null;
let thumbnailObserver: IntersectionObserver | null = null;
const thumbnailElements = new Map<Element, number>();
const renderedThumbnails = new Set<number>();

const slideCount = computed(() => presentation.value?.slides.length ?? 0);

const slideIndices = computed(() => Array.from({ length: slideCount.value }, (_, index) => index));

const aspect = computed(() => {
  const size = presentation.value?.slideSize;
  return size ? size.height / size.width : 9 / 16;
});

const thumbnailStyle = computed(() => ({ width: `${THUMBNAIL_WIDTH}px`, height: `${Math.round(THUMBNAIL_WIDTH * aspect.value)}px` }));

const menuOverlayClass = computed(() => (themeClasses.value.scopeSelector === "aero-mode-theme" ? "dark-mode-theme" : themeClasses.value.scopeSelector));

function updateWindowTitle() {
  if (!props._windowId || !originalWindowTitle) return;
  windowStore.updateWindowTitle(props._windowId, fileName.value ? `${originalWindowTitle} - ${fileName.value}` : originalWindowTitle);
}

watch(fileName, updateWindowTitle);

watch(currentIndex, (index) => (slideInput.value = String(index + 1)));

function isZip(buffer: ArrayBuffer): boolean {
  const bytes = new Uint8Array(buffer);
  return ZIP_MAGIC_BYTES.every((b, i) => bytes[i] === b);
}

function sanitizeSlide(root: Element) {
  for (const element of Array.from(root.querySelectorAll("*"))) {
    if (BLOCKED_TAGS.has(element.localName)) {
      element.remove();
      continue;
    }

    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim();

      if (name.startsWith("on")) element.removeAttribute(attribute.name);
      else if (URL_ATTRIBUTES.has(name) && !(element.localName === "a" ? SAFE_LINK : SAFE_IMAGE).test(value)) element.removeAttribute(attribute.name);
    }
  }
}

async function renderInto(container: HTMLElement | null, index: number, width: number, height: number) {
  const current = presentation.value;
  if (!container || !current || index < 0 || index >= current.slides.length || width <= 0 || height <= 0) return;

  const { renderSlideToElement } = await import("pptx-viewer");
  if (presentation.value !== current) return;

  try {
    renderSlideToElement(current, index, container, { width, height });
    sanitizeSlide(container);
  } catch (err) {
    console.error("Failed to render slide:", index, err);
  }
}

function fitSize(availableWidth: number, availableHeight: number) {
  const width = Math.max(0, Math.min(availableWidth, availableHeight / aspect.value));
  return { width: Math.floor(width), height: Math.floor(width * aspect.value) };
}

function renderCurrentSlide() {
  const stage = stageRef.value;
  if (!stage || !presentation.value) return;

  const { width, height } = fitSize(stage.clientWidth - STAGE_PADDING * 2, stage.clientHeight - STAGE_PADDING * 2);
  if (slideRef.value) {
    slideRef.value.style.width = `${width}px`;
    slideRef.value.style.height = `${height}px`;
  }
  renderInto(slideRef.value, currentIndex.value, width, height);

  if (isPresenting.value) renderPresenterSlide();
}

function renderPresenterSlide() {
  const { width, height } = fitSize(window.innerWidth, window.innerHeight);
  if (presenterSlideRef.value) {
    presenterSlideRef.value.style.width = `${width}px`;
    presenterSlideRef.value.style.height = `${height}px`;
  }
  renderInto(presenterSlideRef.value, currentIndex.value, width, height);
}

function ensureThumbnailObserver() {
  if (thumbnailObserver || !sidebarRef.value) return thumbnailObserver;

  thumbnailObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const index = thumbnailElements.get(entry.target);
        if (!entry.isIntersecting || index === undefined || renderedThumbnails.has(index)) continue;
        renderedThumbnails.add(index);
        renderInto(entry.target as HTMLElement, index, THUMBNAIL_WIDTH, Math.round(THUMBNAIL_WIDTH * aspect.value));
      }
    },
    { root: sidebarRef.value, rootMargin: "200px 0px" },
  );

  return thumbnailObserver;
}

function observeThumbnail(element: HTMLElement | null, index: number) {
  const observer = ensureThumbnailObserver();
  if (!element || !observer || thumbnailElements.has(element)) return;

  thumbnailElements.set(element, index);
  observer.observe(element);
}

function observeAllThumbnails() {
  sidebarRef.value?.querySelectorAll<HTMLElement>("[data-slide] .thumbnail-frame").forEach((element) => {
    observeThumbnail(element, Number((element.parentElement as HTMLElement).dataset.slide));
  });
}

function resetThumbnails() {
  thumbnailObserver?.disconnect();
  thumbnailObserver = null;
  thumbnailElements.clear();
  renderedThumbnails.clear();
}

watch(showSidebar, async (visible) => {
  resetThumbnails();
  if (!visible) return;
  revision.value++;
  await nextTick();
  observeAllThumbnails();
});

watch(currentIndex, async (index) => {
  renderCurrentSlide();
  await nextTick();
  sidebarRef.value?.querySelector(`[data-slide="${index}"]`)?.scrollIntoView({ block: "nearest" });
});

async function openPresentation(buffer: ArrayBuffer, name: string) {
  const token = ++loadToken;

  isLoading.value = true;
  error.value = null;
  fileName.value = name;

  try {
    if (!isZip(buffer)) throw new Error(t("File does not appear to be a valid PowerPoint presentation."));

    const { loadPresentation } = await import("pptx-viewer");
    const loaded = await loadPresentation(buffer.slice(0));
    if (token !== loadToken) {
      loaded.cleanup();
      return;
    }
    if (!loaded.slides.length) throw new Error(t("This presentation has no slides."));

    presentation.value?.cleanup();
    resetThumbnails();
    presentation.value = loaded;
    originalBuffer.value = buffer;
    currentIndex.value = 0;
    revision.value++;
  } catch (err: any) {
    if (token !== loadToken) return;
    console.error("Failed to load presentation:", err);
    presentation.value?.cleanup();
    presentation.value = null;
    error.value = err?.message || t("Failed to open presentation");
  } finally {
    if (token === loadToken) isLoading.value = false;
  }

  await nextTick();
  renderCurrentSlide();
  observeAllThumbnails();
}

function goToSlide(index: number) {
  if (!slideCount.value) return;
  currentIndex.value = Math.max(0, Math.min(index, slideCount.value - 1));
}

function goToSlideInput() {
  const index = Number.parseInt(slideInput.value, 10);
  if (Number.isFinite(index)) goToSlide(index - 1);
  slideInput.value = String(currentIndex.value + 1);
}

function nextSlide() {
  goToSlide(currentIndex.value + 1);
}

function previousSlide() {
  goToSlide(currentIndex.value - 1);
}

async function startPresenting() {
  if (!presentation.value) return;

  isPresenting.value = true;
  await nextTick();
  renderPresenterSlide();

  try {
    await presenterRef.value?.requestFullscreen?.();
  } catch {
    return;
  }
}

function stopPresenting() {
  isPresenting.value = false;
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
}

function handleFullscreenChange() {
  if (!document.fullscreenElement && isPresenting.value) isPresenting.value = false;
  else if (isPresenting.value) renderPresenterSlide();
}

function handleViewportResize() {
  if (isPresenting.value) renderPresenterSlide();
}

function downloadOriginal() {
  if (!originalBuffer.value) return;
  triggerDownload(new Blob([originalBuffer.value], { type: PPTX_MIME }), fileName.value || "presentation.pptx");
}

function browseDocuments() {
  windowStore.openFileInApp("fileexplorer", {
    data: { initialLocation: "storage", initialPath: DOCUMENTS_FOLDER },
  });
}

function closeWindow() {
  if (props._windowId) windowStore.closeWindow(props._windowId);
}

function isPptxFile(file: File): boolean {
  return file.type === PPTX_MIME || file.name.toLowerCase().endsWith(".pptx");
}

function hasDraggedFiles(event: DragEvent): boolean {
  return Boolean(event.dataTransfer?.types.includes("Files"));
}

function onDragEnter(event: DragEvent) {
  if (!hasDraggedFiles(event)) return;
  dragDepth++;
  isDragOver.value = true;
}

function onDragOver(event: DragEvent) {
  if (!hasDraggedFiles(event) || !event.dataTransfer) return;
  event.dataTransfer.dropEffect = "copy";
}

function onDragLeave(event: DragEvent) {
  if (!hasDraggedFiles(event)) return;
  dragDepth = Math.max(0, dragDepth - 1);
  if (dragDepth === 0) isDragOver.value = false;
}

async function onDrop(event: DragEvent) {
  dragDepth = 0;
  isDragOver.value = false;

  const file = Array.from(event.dataTransfer?.files ?? []).find(isPptxFile);
  if (file) openPresentation(await file.arrayBuffer(), file.name);
}

function isEditableTarget(element: EventTarget | null) {
  return element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || (element instanceof HTMLElement && element.isContentEditable);
}

function handleKeydown(event: KeyboardEvent) {
  if (!isPresenting.value && props._windowId && windowStore.activeWindowId !== props._windowId) return;
  if (!presentation.value || isEditableTarget(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;

  const forward = ["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"];
  const backward = ["ArrowLeft", "ArrowUp", "PageUp", "Backspace"];

  if (forward.includes(event.key)) nextSlide();
  else if (backward.includes(event.key)) previousSlide();
  else if (event.key === "Home") goToSlide(0);
  else if (event.key === "End") goToSlide(slideCount.value - 1);
  else if (event.key === "F5") startPresenting();
  else if (event.key === "Escape" && isPresenting.value) stopPresenting();
  else return;

  event.preventDefault();
}

function handleIncomingFile(event: Event) {
  const incoming = (event as CustomEvent<{ slidesFile?: ExternalBinaryFile }>).detail?.slidesFile;
  if (incoming) openPresentation(incoming.buffer, incoming.name);
}

onMounted(() => {
  document.addEventListener("keydown", handleKeydown);
  document.addEventListener("fullscreenchange", handleFullscreenChange);
  window.addEventListener("resize", handleViewportResize);

  if (props._windowId) window.addEventListener(`homedock:open-file-${props._windowId}`, handleIncomingFile);

  if (stageRef.value) {
    stageObserver = new ResizeObserver(() => renderCurrentSlide());
    stageObserver.observe(stageRef.value);
  }

  updateWindowTitle();
  if (props.slidesFile) openPresentation(props.slidesFile.buffer, props.slidesFile.name);
});

onUnmounted(() => {
  document.removeEventListener("keydown", handleKeydown);
  document.removeEventListener("fullscreenchange", handleFullscreenChange);
  window.removeEventListener("resize", handleViewportResize);

  if (props._windowId) window.removeEventListener(`homedock:open-file-${props._windowId}`, handleIncomingFile);

  stageObserver?.disconnect();
  resetThumbnails();
  stopPresenting();
  loadToken++;
  presentation.value?.cleanup();
  presentation.value = null;
});
</script>

<style scoped>
.utils-slides {
  user-select: none;
}

.slide-canvas {
  box-shadow:
    0 1px 3px rgb(0 0 0 / 0.12),
    0 8px 24px rgb(0 0 0 / 0.12);
}

.slide-canvas :deep(a) {
  cursor: pointer;
}

.thumbnail-frame {
  box-shadow: 0 0 0 1px rgb(0 0 0 / 0.12);
  transition: box-shadow 0.15s ease;
}

.thumbnail-item:hover .thumbnail-frame {
  box-shadow:
    0 0 0 1px rgb(0 0 0 / 0.2),
    0 2px 6px rgb(0 0 0 / 0.12);
}

.thumbnail-frame.active {
  box-shadow: 0 0 0 3px #3b82f6;
}

.thumbnail-frame :deep(svg) {
  pointer-events: none;
}

.slides-presenter {
  position: fixed;
  inset: 0;
  z-index: 2147483000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #000;
  cursor: pointer;
}

.presenter-close {
  position: absolute;
  top: 16px;
  right: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 9999px;
  color: #fff;
  background: rgb(0 0 0 / 0.55);
  box-shadow:
    0 0 0 1px rgb(255 255 255 / 0.18),
    0 2px 8px rgb(0 0 0 / 0.3);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.2s ease,
    background-color 0.15s ease;
}

.presenter-close:hover {
  background: rgb(0 0 0 / 0.75);
}

.presenter-counter {
  position: absolute;
  bottom: 16px;
  right: 16px;
  padding: 4px 10px;
  border-radius: 9999px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: rgb(255 255 255 / 0.9);
  background: rgb(0 0 0 / 0.55);
  box-shadow: 0 0 0 1px rgb(255 255 255 / 0.18);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
  opacity: 0;
  transition: opacity 0.2s ease;
}

.slides-presenter:hover .presenter-close,
.slides-presenter:hover .presenter-counter {
  opacity: 1;
}

.drop-fade-enter-active,
.drop-fade-leave-active {
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}

.drop-fade-enter-from,
.drop-fade-leave-to {
  opacity: 0;
  transform: scale(0.98);
}

@container window (max-width: 520px) {
  .present-button {
    width: 1.75rem;
    padding: 0;
  }

  .present-label {
    display: none;
  }
}
</style>
