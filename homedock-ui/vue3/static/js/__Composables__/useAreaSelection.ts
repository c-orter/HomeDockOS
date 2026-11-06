// homedock-ui/vue3/static/js/__Composables__/useAreaSelection.ts
// Copyright © 2023-2026 Banshee, All Rights Reserved
// See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/
// https://www.banshee.pro

import { computed, onBeforeUnmount, reactive, ref, type CSSProperties, type Ref } from "vue";

const PADDING_X = 12;
const PADDING_Y = 8;
const ITEM_DRAG_THRESHOLD = 20;
const CLICK_TOLERANCE = 5;

interface AreaSelectionOptions {
  containerRef: Ref<HTMLElement | null>;
  getSelection: () => Set<string>;
  setSelection: (ids: Set<string>) => void;
  enabled?: () => boolean;
  startOnItems?: boolean;
  itemAttribute?: string;
  accepts?: (id: string) => boolean;
}

export function useAreaSelection(options: AreaSelectionOptions) {
  const { containerRef, getSelection, setSelection, enabled = () => true, startOnItems = false, itemAttribute: ITEM_ATTRIBUTE = "data-select-id", accepts = () => true } = options;

  const isSelectingArea = ref(false);
  const box = reactive({ startX: 0, startY: 0, currentX: 0, currentY: 0 });

  let origin: { x: number; y: number } | null = null;
  let startedOnItem = false;
  let base = new Set<string>();
  let suppressClick = false;

  const selectionBoxStyle = computed<CSSProperties>(() => ({
    left: `${Math.min(box.startX, box.currentX)}px`,
    top: `${Math.min(box.startY, box.currentY)}px`,
    width: `${Math.abs(box.currentX - box.startX)}px`,
    height: `${Math.abs(box.currentY - box.startY)}px`,
  }));

  function pointInContent(event: MouseEvent) {
    const container = containerRef.value!;
    const rect = container.getBoundingClientRect();
    const x = Math.max(PADDING_X, Math.min(event.clientX - rect.left, rect.width - PADDING_X));
    const y = Math.max(PADDING_Y, Math.min(event.clientY - rect.top, rect.height - PADDING_Y));
    return { x: x + container.scrollLeft, y: y + container.scrollTop };
  }

  function startBox(point: { x: number; y: number }) {
    isSelectingArea.value = true;
    box.startX = box.currentX = point.x;
    box.startY = box.currentY = point.y;
  }

  function updateSelection() {
    const container = containerRef.value;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const left = Math.min(box.startX, box.currentX);
    const top = Math.min(box.startY, box.currentY);
    const right = Math.max(box.startX, box.currentX);
    const bottom = Math.max(box.startY, box.currentY);

    const next = new Set(base);
    container.querySelectorAll<HTMLElement>(`[${ITEM_ATTRIBUTE}]`).forEach((element) => {
      const itemRect = element.getBoundingClientRect();
      const itemLeft = itemRect.left - rect.left + container.scrollLeft;
      const itemTop = itemRect.top - rect.top + container.scrollTop;
      const id = element.getAttribute(ITEM_ATTRIBUTE)!;
      if (accepts(id) && left < itemLeft + itemRect.width && right > itemLeft && top < itemTop + itemRect.height && bottom > itemTop) {
        next.add(id);
      }
    });
    setSelection(next);
  }

  function handleMouseDown(event: MouseEvent) {
    if (event.button !== 0 || !containerRef.value || !enabled()) return;

    startedOnItem = !!(event.target as HTMLElement).closest(`[${ITEM_ATTRIBUTE}]`);
    if (startedOnItem && !startOnItems) return;

    const additive = event.metaKey || event.ctrlKey || event.shiftKey;
    base = additive ? new Set(getSelection()) : new Set();
    origin = pointInContent(event);

    if (!startedOnItem) {
      if (!additive) setSelection(new Set());
      startBox(origin);
    }

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  }

  function handleMouseMove(event: MouseEvent) {
    if (!origin || !containerRef.value) return;
    const point = pointInContent(event);

    if (!isSelectingArea.value) {
      if (Math.hypot(point.x - origin.x, point.y - origin.y) <= ITEM_DRAG_THRESHOLD) return;
      startBox(origin);
    }

    box.currentX = point.x;
    box.currentY = point.y;
    updateSelection();
  }

  function handleMouseUp() {
    const dragged = isSelectingArea.value && (Math.abs(box.currentX - box.startX) > CLICK_TOLERANCE || Math.abs(box.currentY - box.startY) > CLICK_TOLERANCE);
    if (dragged) {
      suppressClick = true;
      setTimeout(() => (suppressClick = false), 50);
    }

    isSelectingArea.value = false;
    origin = null;
    startedOnItem = false;
    document.removeEventListener("mousemove", handleMouseMove);
    document.removeEventListener("mouseup", handleMouseUp);
  }

  function consumeDragClick(): boolean {
    return suppressClick;
  }

  onBeforeUnmount(handleMouseUp);

  return { isSelectingArea, selectionBoxStyle, handleMouseDown, consumeDragClick };
}
