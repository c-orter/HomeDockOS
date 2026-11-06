<!-- homedock-ui/vue3/static/js/__Components__/PDFSignatureDialog.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <AppDialog v-model:visible="visible" title="Add Signature" ok-text="Add" cancel-text="Cancel" :width="460" :ok-disabled="isEmpty" :icon="signatureIcon" @ok="confirm" @cancel="visible = false">
    <div class="flex flex-col gap-3">
      <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <SegmentedControl v-model="mode" :options="modeOptions" class="flex-shrink-0" />
        <div class="flex items-center gap-1.5">
          <button v-for="color in INK_COLORS" :key="color" type="button" class="signature-swatch w-5 h-5 rounded-full border-0 cursor-pointer" :class="{ active: inkColor === color }" :style="{ backgroundColor: color }" :title="$t('Color')" @click="inkColor = color"></button>
        </div>
      </div>

      <div class="signature-pad relative h-40 rounded-xl border overflow-hidden" :class="[themeClasses.windowBorder]">
        <canvas v-show="mode === 'draw'" ref="canvasRef" class="absolute inset-0 w-full h-full cursor-crosshair touch-none" @pointerdown="startStroke" @pointermove="continueStroke" @pointerup="endStroke" @pointercancel="endStroke" @pointerleave="endStroke"></canvas>
        <div v-if="mode === 'draw' && !hasStrokes" class="absolute inset-0 flex items-center justify-center pointer-events-none text-sm text-gray-400">{{ $t("Sign here") }}</div>
        <div v-if="mode === 'type'" class="absolute inset-0 flex items-center justify-center px-4">
          <input ref="typeInputRef" v-model="typedName" type="text" maxlength="60" :placeholder="$t('Type your name')" class="signature-typed w-full bg-transparent border-0 outline-hidden text-center text-gray-900" :style="{ color: inkColor }" @keyup.enter="confirm" />
        </div>
        <div class="absolute left-6 right-6 bottom-9 border-b border-dashed border-gray-300 pointer-events-none"></div>
      </div>

      <div class="flex items-center justify-between">
        <span :class="['text-[11px] opacity-50', themeClasses.windowText]">{{ $t("The signature is added as an image you can move and resize.") }}</span>
        <button type="button" :disabled="isEmpty" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="px-2 py-1 text-xs rounded transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-default" @click="clear">{{ $t("Clear") }}</button>
      </div>
    </div>
  </AppDialog>
</template>

<script lang="ts" setup>
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

import drawIcon from "@iconify-icons/mdi/draw";
import keyboardIcon from "@iconify-icons/mdi/keyboard-outline";
import signatureIcon from "@iconify-icons/mdi/signature-freehand";

import { useTheme } from "../__Themes__/ThemeSelector";

import AppDialog from "./AppDialog.vue";
import SegmentedControl from "./SegmentedControl.vue";

const INK_COLORS = ["#111827", "#1d4ed8", "#b91c1c"];

const SIGNATURE_FONT = '"Snell Roundhand", "Segoe Script", "Brush Script MT", "Apple Chancery", cursive';

const EXPORT_SCALE = 3;

const EXPORT_PADDING = 8;

const visible = defineModel<boolean>("visible", { required: true });

const emit = defineEmits<{ confirm: [file: File] }>();

const { t } = useI18n();
const { themeClasses } = useTheme();

const mode = ref<"draw" | "type">("draw");
const inkColor = ref(INK_COLORS[0]);
const typedName = ref("");
const strokes = ref<{ x: number; y: number }[][]>([]);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const typeInputRef = ref<HTMLInputElement | null>(null);

let activeStroke: { x: number; y: number }[] | null = null;

const modeOptions = computed(() => [
  { value: "draw", label: t("Draw"), icon: drawIcon },
  { value: "type", label: t("Text"), icon: keyboardIcon },
]);

const hasStrokes = computed(() => strokes.value.length > 0);

const isEmpty = computed(() => (mode.value === "draw" ? !hasStrokes.value : !typedName.value.trim()));

function prepareCanvas() {
  const canvas = canvasRef.value;
  if (!canvas) return;

  const ratio = window.devicePixelRatio || 1;
  canvas.width = canvas.clientWidth * ratio;
  canvas.height = canvas.clientHeight * ratio;
  redraw();
}

function drawStrokes(context: CanvasRenderingContext2D, scale: number, offsetX = 0, offsetY = 0) {
  context.lineCap = "round";
  context.lineJoin = "round";
  context.lineWidth = 2.4 * scale;
  context.strokeStyle = inkColor.value;

  for (const stroke of strokes.value) {
    context.beginPath();
    stroke.forEach((point, index) => {
      const x = (point.x - offsetX) * scale;
      const y = (point.y - offsetY) * scale;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    });
    if (stroke.length === 1) context.lineTo((stroke[0].x - offsetX) * scale + 0.1, (stroke[0].y - offsetY) * scale);
    context.stroke();
  }
}

function redraw() {
  const canvas = canvasRef.value;
  const context = canvas?.getContext("2d");
  if (!canvas || !context) return;

  context.clearRect(0, 0, canvas.width, canvas.height);
  drawStrokes(context, window.devicePixelRatio || 1);
}

function pointFrom(event: PointerEvent) {
  const rect = canvasRef.value!.getBoundingClientRect();
  return { x: event.clientX - rect.left, y: event.clientY - rect.top };
}

function startStroke(event: PointerEvent) {
  if (event.button !== 0) return;

  canvasRef.value?.setPointerCapture(event.pointerId);
  activeStroke = [pointFrom(event)];
  strokes.value = [...strokes.value, activeStroke];
  redraw();
}

function continueStroke(event: PointerEvent) {
  if (!activeStroke) return;

  activeStroke.push(pointFrom(event));
  redraw();
}

function endStroke() {
  activeStroke = null;
}

function clear() {
  strokes.value = [];
  typedName.value = "";
  redraw();
}

function canvasToFile(canvas: HTMLCanvasElement): Promise<File> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(new File([blob], "signature.png", { type: "image/png" })) : reject(new Error("Signature export failed"))), "image/png");
  });
}

function exportDrawing(): HTMLCanvasElement {
  const points = strokes.value.flat();
  const minX = Math.min(...points.map((point) => point.x)) - EXPORT_PADDING;
  const minY = Math.min(...points.map((point) => point.y)) - EXPORT_PADDING;
  const maxX = Math.max(...points.map((point) => point.x)) + EXPORT_PADDING;
  const maxY = Math.max(...points.map((point) => point.y)) + EXPORT_PADDING;

  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil((maxX - minX) * EXPORT_SCALE);
  canvas.height = Math.ceil((maxY - minY) * EXPORT_SCALE);
  drawStrokes(canvas.getContext("2d")!, EXPORT_SCALE, minX, minY);

  return canvas;
}

function exportTyped(): HTMLCanvasElement {
  const text = typedName.value.trim();
  const fontSize = 44 * EXPORT_SCALE;
  const font = `${fontSize}px ${SIGNATURE_FONT}`;

  const measure = document.createElement("canvas").getContext("2d")!;
  measure.font = font;
  const metrics = measure.measureText(text);

  const padding = EXPORT_PADDING * EXPORT_SCALE;
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(metrics.width + padding * 2);
  canvas.height = Math.ceil(fontSize * 1.5 + padding * 2);

  const context = canvas.getContext("2d")!;
  context.font = font;
  context.fillStyle = inkColor.value;
  context.textBaseline = "middle";
  context.fillText(text, padding, canvas.height / 2);

  return canvas;
}

async function confirm() {
  if (isEmpty.value) return;

  const file = await canvasToFile(mode.value === "draw" ? exportDrawing() : exportTyped());
  visible.value = false;
  emit("confirm", file);
}

const canvasObserver = new ResizeObserver(prepareCanvas);

watch(canvasRef, (canvas, previous) => {
  if (previous) canvasObserver.unobserve(previous);
  if (canvas) canvasObserver.observe(canvas);
});

watch(inkColor, redraw);

watch(mode, async (next) => {
  await nextTick();
  if (next === "type") typeInputRef.value?.focus();
});

watch(visible, (open) => {
  if (!open) return;

  strokes.value = [];
  typedName.value = "";
  redraw();
});

onUnmounted(() => canvasObserver.disconnect());
</script>

<style scoped>
.signature-pad {
  background: #fff;
}

.signature-typed {
  font-family: "Snell Roundhand", "Segoe Script", "Brush Script MT", "Apple Chancery", cursive;
  font-size: 2.25rem;
}

.signature-typed::placeholder {
  color: #9ca3af;
  font-family: inherit;
}

.signature-swatch {
  box-shadow: 0 0 0 1px rgb(128 128 128 / 0.55);
  transition: box-shadow 0.15s ease;
}

.signature-swatch.active {
  box-shadow:
    0 0 0 2px var(--color-white, #fff),
    0 0 0 4px #3b82f6;
}
</style>
