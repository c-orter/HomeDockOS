<!-- homedock-ui/vue3/static/js/__Components__/CountBadge.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <Transition name="count-badge">
    <span v-if="count > 0" class="count-badge">
      <Transition name="count-badge-bump" mode="out-in">
        <span :key="label" class="count-badge-label">{{ label }}</span>
      </Transition>
    </span>
  </Transition>
</template>

<script lang="ts" setup>
import { computed } from "vue";

const MAX_SHOWN = 99;

const props = defineProps<{ count: number }>();

const label = computed(() => (props.count > MAX_SHOWN ? `${MAX_SHOWN}+` : String(props.count)));
</script>

<style scoped>
.count-badge {
  position: absolute;
  top: -3px;
  right: -3px;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  pointer-events: none;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: -0.01em;
  font-variant-numeric: tabular-nums;
  text-shadow: 0 0.5px 0 rgba(0, 0, 0, 0.25);
  background: linear-gradient(180deg, #4aa3ff 0%, #0a7aff 55%, #0064e6 100%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.4),
    inset 0 -1px 0 rgba(0, 0, 0, 0.12),
    0 0 0 0.5px rgba(0, 0, 0, 0.25),
    0 1px 3px rgba(0, 0, 0, 0.3);
}

.count-badge-label {
  display: block;
  position: relative;
  top: -1px;
}

.count-badge-enter-active {
  transition:
    transform 0.45s cubic-bezier(0.34, 1.56, 0.64, 1),
    opacity 0.2s ease;
}

.count-badge-leave-active {
  transition:
    transform 0.2s ease-in,
    opacity 0.2s ease-in;
}

.count-badge-enter-from,
.count-badge-leave-to {
  opacity: 0;
  transform: scale(0.3);
}

.count-badge-bump-enter-active {
  transition:
    transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1),
    opacity 0.15s ease;
}

.count-badge-bump-leave-active {
  transition:
    transform 0.12s ease-in,
    opacity 0.12s ease-in;
}

.count-badge-bump-enter-from {
  opacity: 0;
  transform: translateY(5px);
}

.count-badge-bump-leave-to {
  opacity: 0;
  transform: translateY(-5px);
}
</style>
