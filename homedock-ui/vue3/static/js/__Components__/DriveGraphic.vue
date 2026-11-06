<!-- homedock-ui/vue3/static/js/__Components__/DriveGraphic.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div class="drive-graphic-box" :style="{ width: `${size}px`, height: `${size}px` }">
    <div class="drive-graphic" :style="{ transform: size === BASE_SIZE ? undefined : `scale(${size / BASE_SIZE})` }">
      <div v-if="kind === 'nvme'" class="drive-nvme">
        <span class="nvme-notch"></span>
        <span class="nvme-chip nvme-chip-main"></span>
        <span class="nvme-chip nvme-chip-small"></span>
        <span class="nvme-label"></span>
        <span class="nvme-contacts"></span>
      </div>

      <div v-else-if="kind === 'usb'" class="drive-usb">
        <span class="usb-plug"><span class="usb-plug-hole"></span><span class="usb-plug-hole"></span></span>
        <span class="usb-body"><span class="usb-ring"></span><span class="usb-led"></span></span>
      </div>

      <div v-else-if="kind === 'optical'" class="drive-optical">
        <span class="optical-shine"></span>
      </div>

      <div v-else :class="['drive-box', kind === 'ssd' && 'drive-box-ssd']">
        <span class="drive-top">
          <span class="drive-screw drive-screw-left"></span>
          <span class="drive-screw drive-screw-right"></span>
          <span v-if="kind === 'ssd'" class="drive-sticker"></span>
        </span>
        <span class="drive-front"><span class="drive-led"></span></span>
      </div>

      <span v-if="system" class="drive-badge">
        <Icon :icon="homedockIcon" class="drive-badge-glyph" />
      </span>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed } from "vue";
import { Icon } from "@iconify/vue";
import { homedockIcon } from "../__Config__/HomeDockIcon";

const BASE_SIZE = 64;

const props = withDefaults(defineProps<{ mediaType?: string; system?: boolean; size?: number }>(), {
  mediaType: "disk",
  system: false,
  size: BASE_SIZE,
});

const kind = computed(() => {
  switch (props.mediaType) {
    case "nvme":
    case "ssd":
    case "usb":
    case "optical":
      return props.mediaType;
    default:
      return "hdd";
  }
});
</script>

<style scoped>
.drive-graphic-box {
  position: relative;
  flex-shrink: 0;
  pointer-events: none;
  isolation: isolate;
}

.drive-graphic {
  position: absolute;
  top: 0;
  left: 0;
  width: 64px;
  height: 64px;
  transform-origin: top left;
}

.drive-box {
  position: absolute;
  inset: 17px 4px 15px;
  display: flex;
  flex-direction: column;
  border-radius: 6px;
  overflow: hidden;
  box-shadow:
    0 0 0 0.5px rgba(0, 0, 0, 0.28),
    0 2px 5px rgba(0, 0, 0, 0.22);
}

.drive-top {
  position: relative;
  flex: 1;
  background: linear-gradient(180deg, #f8fafc 0%, #dfe3e8 55%, #cfd5dc 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.drive-front {
  position: relative;
  height: 9px;
  background: linear-gradient(180deg, #9aa3ae 0%, #7b8591 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25);
}

.drive-screw {
  position: absolute;
  top: 4px;
  width: 3px;
  height: 3px;
  border-radius: 9999px;
  background: radial-gradient(circle at 35% 35%, #ffffff 0%, #9ca3af 70%);
  box-shadow: 0 0 0 0.5px rgba(0, 0, 0, 0.25);
}

.drive-screw-left {
  left: 4px;
}

.drive-screw-right {
  right: 4px;
}

.drive-led {
  position: absolute;
  top: 3px;
  right: 6px;
  width: 3px;
  height: 3px;
  border-radius: 9999px;
  background: #4ade80;
  box-shadow: 0 0 3px #4ade80;
}

.drive-box-ssd .drive-top {
  background: linear-gradient(180deg, #4b5563 0%, #374151 55%, #2b3340 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.18);
}

.drive-box-ssd .drive-front {
  background: linear-gradient(180deg, #1f2937 0%, #111827 100%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.drive-box-ssd .drive-screw {
  background: radial-gradient(circle at 35% 35%, #d1d5db 0%, #4b5563 70%);
}

.drive-sticker {
  position: absolute;
  top: 7px;
  left: 50%;
  width: 26px;
  height: 7px;
  border-radius: 2px;
  transform: translateX(-50%);
  background: linear-gradient(90deg, #e5e7eb 0%, #e5e7eb 62%, #3b82f6 62%, #3b82f6 100%);
  opacity: 0.9;
}

.drive-nvme {
  position: absolute;
  top: 24px;
  left: 3px;
  right: 3px;
  height: 16px;
  border-radius: 2px 3px 3px 2px;
  background: linear-gradient(180deg, #2f3a48 0%, #1c2430 100%);
  box-shadow:
    0 0 0 0.5px rgba(0, 0, 0, 0.4),
    0 2px 4px rgba(0, 0, 0, 0.25),
    inset 0 1px 0 rgba(255, 255, 255, 0.12);
}

.nvme-notch {
  position: absolute;
  top: 50%;
  left: -2px;
  width: 6px;
  height: 6px;
  border-radius: 9999px;
  transform: translateY(-50%);
  background: radial-gradient(circle, transparent 0 1.5px, #c9a227 1.5px 3px);
}

.nvme-chip {
  position: absolute;
  top: 3px;
  bottom: 3px;
  border-radius: 1.5px;
  background: linear-gradient(180deg, #11161d 0%, #070a0e 100%);
  box-shadow: inset 0 0 0 0.5px rgba(255, 255, 255, 0.14);
}

.nvme-chip-main {
  left: 8px;
  width: 15px;
}

.nvme-chip-small {
  left: 26px;
  width: 9px;
}

.nvme-label {
  position: absolute;
  top: 4px;
  left: 38px;
  width: 8px;
  height: 8px;
  border-radius: 1px;
  background: #e5e7eb;
  opacity: 0.85;
}

.nvme-contacts {
  position: absolute;
  top: 2px;
  right: 1px;
  bottom: 2px;
  width: 6px;
  background: repeating-linear-gradient(180deg, #e8c25a 0 1.5px, transparent 1.5px 2.5px);
}

.drive-usb {
  position: absolute;
  inset: 0;
}

.usb-body {
  position: absolute;
  top: 21px;
  left: 6px;
  width: 38px;
  height: 22px;
  border-radius: 6px 4px 4px 6px;
  background: linear-gradient(180deg, #22b4d3 0%, #0891b2 60%, #0b7690 100%);
  box-shadow:
    0 0 0 0.5px rgba(0, 0, 0, 0.3),
    0 2px 5px rgba(0, 0, 0, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.35);
}

.usb-ring {
  position: absolute;
  top: 50%;
  left: 4px;
  width: 6px;
  height: 6px;
  border-radius: 9999px;
  transform: translateY(-50%);
  background: rgba(0, 0, 0, 0.28);
  box-shadow: inset 0 1px 1px rgba(0, 0, 0, 0.35);
}

.usb-led {
  position: absolute;
  top: 50%;
  right: 5px;
  width: 3px;
  height: 3px;
  border-radius: 9999px;
  transform: translateY(-50%);
  background: #bbf7d0;
  box-shadow: 0 0 3px #4ade80;
}

.usb-plug {
  position: absolute;
  top: 25px;
  left: 43px;
  width: 16px;
  height: 14px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
  padding-left: 5px;
  border-radius: 0 2px 2px 0;
  background: linear-gradient(180deg, #f1f5f9 0%, #cbd5e1 50%, #a8b3c1 100%);
  box-shadow:
    0 0 0 0.5px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.usb-plug-hole {
  display: block;
  width: 4px;
  height: 2.5px;
  border-radius: 0.5px;
  background: #475569;
}

.drive-optical {
  position: absolute;
  inset: 6px;
  border-radius: 9999px;
  background:
    radial-gradient(circle, transparent 0 5px, rgba(255, 255, 255, 0.85) 5px 7px, rgba(148, 163, 184, 0.9) 7px 8px, transparent 8px),
    conic-gradient(from 200deg, #e2e8f0, #c7d2fe, #f5d0fe, #fde68a, #bbf7d0, #bae6fd, #e2e8f0, #cbd5e1, #e2e8f0);
  -webkit-mask-image: radial-gradient(circle, transparent 0 4px, #000 4.5px);
  mask-image: radial-gradient(circle, transparent 0 4px, #000 4.5px);
  box-shadow: inset 0 0 0 0.5px rgba(0, 0, 0, 0.2);
  filter: drop-shadow(0 2px 3px rgba(0, 0, 0, 0.25));
}

.optical-shine {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: conic-gradient(from 300deg, transparent 0deg, rgba(255, 255, 255, 0.7) 20deg, transparent 45deg, transparent 180deg, rgba(255, 255, 255, 0.55) 200deg, transparent 225deg);
}

.drive-badge {
  position: absolute;
  right: 2px;
  bottom: 3px;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 5px;
  background: linear-gradient(180deg, #ffffff 0%, #e5e7eb 100%);
  box-shadow:
    0 0 0 0.5px rgba(0, 0, 0, 0.25),
    0 1px 3px rgba(0, 0, 0, 0.3);
}

.drive-badge-glyph {
  width: 11px;
  height: 11px;
  color: #1f2937;
}
</style>
