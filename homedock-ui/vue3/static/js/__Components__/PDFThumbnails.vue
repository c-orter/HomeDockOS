<!-- homedock-ui/vue3/static/js/__Components__/PDFThumbnails.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div ref="listRef" class="pdf-thumbnails flex-1 min-h-0 overflow-y-auto px-3 py-3 space-y-3">
    <button v-for="page in pages" :key="`${revision}-${page}`" :ref="(el) => observe(el as HTMLElement | null, page)" :data-page="page" type="button" class="thumbnail-item group flex flex-col items-center gap-1.5 w-full bg-transparent border-0 p-0 cursor-pointer" @click="emit('select', page)" @contextmenu.prevent="emit('menu', page, $event)">
      <span class="thumbnail-frame block rounded-[3px] overflow-hidden bg-white" :class="{ active: page === currentPage }" :style="frameStyle(page)">
        <canvas :ref="(el) => setCanvas(el as HTMLCanvasElement | null, page)" class="block w-full h-full"></canvas>
      </span>
      <span class="text-[11px] tabular-nums px-1.5 rounded" :class="page === currentPage ? 'bg-blue-500 text-white' : themeClasses.windowTextMuted">{{ page }}</span>
    </button>
  </div>
</template>

<script lang="ts" setup>
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";

import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

import { useTheme } from "../__Themes__/ThemeSelector";

const THUMBNAIL_WIDTH = 116;

const props = defineProps<{
  pdf: PDFDocumentProxy | null;
  currentPage: number;
  rotation: number;
  revision: number;
}>();

const emit = defineEmits<{
  select: [page: number];
  menu: [page: number, event: MouseEvent];
}>();

const { themeClasses } = useTheme();

const listRef = ref<HTMLElement | null>(null);
const aspects = shallowRef(new Map<number, number>());
const canvases = new Map<number, HTMLCanvasElement>();
const rendered = new Set<number>();
const tasks = new Map<number, RenderTask>();
const elements = new Map<Element, number>();

let observer: IntersectionObserver | null = null;

const pages = computed(() => Array.from({ length: props.pdf?.numPages ?? 0 }, (_, index) => index + 1));

function frameStyle(page: number) {
  const aspect = aspects.value.get(page) ?? 1.414;
  return { width: `${THUMBNAIL_WIDTH}px`, height: `${Math.round(THUMBNAIL_WIDTH * aspect)}px` };
}

function setCanvas(el: HTMLCanvasElement | null, page: number) {
  if (el) canvases.set(page, el);
  else canvases.delete(page);
}

async function render(page: number) {
  const pdf = props.pdf;
  const canvas = canvases.get(page);
  if (!pdf || !canvas || rendered.has(page)) return;

  rendered.add(page);

  try {
    const pdfPage = await pdf.getPage(page);
    const base = pdfPage.getViewport({ scale: 1, rotation: pdfPage.rotate + props.rotation });
    const ratio = window.devicePixelRatio || 1;
    const viewport = pdfPage.getViewport({ scale: (THUMBNAIL_WIDTH / base.width) * ratio, rotation: pdfPage.rotate + props.rotation });

    const nextAspects = new Map(aspects.value);
    nextAspects.set(page, base.height / base.width);
    aspects.value = nextAspects;

    canvas.width = Math.round(viewport.width);
    canvas.height = Math.round(viewport.height);

    const task = pdfPage.render({ canvas, viewport });
    tasks.set(page, task);
    await task.promise;
  } catch (error: any) {
    if (error?.name !== "RenderingCancelledException") rendered.delete(page);
  } finally {
    tasks.delete(page);
  }
}

function ensureObserver() {
  if (observer || !listRef.value) return observer;

  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        const page = elements.get(entry.target);
        if (entry.isIntersecting && page) render(page);
      }
    },
    { root: listRef.value, rootMargin: "200px 0px" },
  );

  return observer;
}

function observe(el: HTMLElement | null, page: number) {
  const active = ensureObserver();
  if (!el || !active || elements.has(el)) return;

  elements.set(el, page);
  active.observe(el);
}

function observeAll() {
  const items = listRef.value?.querySelectorAll<HTMLElement>("[data-page]") ?? [];
  items.forEach((el) => observe(el, Number(el.dataset.page)));
}

function reset() {
  for (const task of tasks.values()) task.cancel();
  tasks.clear();
  rendered.clear();
  aspects.value = new Map();
  observer?.disconnect();
  observer = null;
  elements.clear();
}

watch(
  () => [props.pdf, props.rotation, props.revision],
  async () => {
    reset();
    await nextTick();
    observeAll();
  },
);

watch(
  () => props.currentPage,
  async (page) => {
    await nextTick();
    listRef.value?.querySelector(`[data-page="${page}"]`)?.scrollIntoView({ block: "nearest" });
  },
);

onMounted(() => {
  observeAll();
  listRef.value?.querySelector(`[data-page="${props.currentPage}"]`)?.scrollIntoView({ block: "nearest" });
});

onUnmounted(reset);
</script>

<style scoped>
.thumbnail-frame {
  box-shadow: 0 0 0 1px rgb(0 0 0 / 0.12);
  transition: box-shadow 0.15s ease;
}

.thumbnail-item:hover .thumbnail-frame {
  box-shadow: 0 0 0 1px rgb(0 0 0 / 0.2), 0 2px 6px rgb(0 0 0 / 0.12);
}

.thumbnail-frame.active {
  box-shadow: 0 0 0 3px #3b82f6;
}
</style>
