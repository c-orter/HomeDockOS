<!-- homedock-ui/vue3/static/js/__Components__/LoginTips.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <transition name="slide-down-fade">
    <div v-show="isBannerVisible" class="relative z-30 grid grid-rows-[1fr] w-full">
      <div class="overflow-hidden">
        <div class="tips-banner relative overflow-hidden text-xs w-full min-h-8 text-white text-center flex items-center justify-center rounded-3xl py-2.5" @mouseenter="pauseRotation" @mouseleave="resumeRotation">
          <div v-for="(tip, index) in TIPS" :key="tip.text" class="tip-backdrop animate-rainbow" :class="{ 'is-active': index === currentIndex }" :style="{ backgroundImage: gradientOf(tip) }"></div>
          <span id="LoginTipsClose" class="absolute right-4 z-10 text-white cursor-pointer" @click="closeLoginTips">
            <Icon :icon="closeIcon" class="mr-1 text-current" width="14" height="14" />
          </span>
          <transition name="tip-fade" mode="out-in">
            <a :key="currentIndex" target="_blank" rel="noopener noreferrer" :href="currentTip.url" class="relative z-10 block text-balance px-8">
              <Icon :icon="openIcon" class="inline-block align-middle mr-1 text-current" width="14" height="14" />
              <span>{{ $t(currentTip.text) }}</span>
            </a>
          </transition>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";

import { Icon } from "@iconify/vue";
import openIcon from "@iconify-icons/mdi/open-in-new";
import closeIcon from "@iconify-icons/mdi/close-thick";

interface Props {
  isVisible: boolean;
}

interface LoginTip {
  text: string;
  url: string;
  colors: [string, string, string];
  weight?: number;
}

const REPO_URL = "https://github.com/BansheeTech/HomeDockOS";
const ROTATION_MS = 10000;
const STORAGE_KEY = "loginTipsClosed";
const POOL_SHARE = 40;

const TIPS: LoginTip[] = [
  { text: "HomeDock OS Enterprise: more power for your business", url: "https://docs.homedock.cloud/enterprise/overview/", colors: ["#6e0000", "#4b0092", "#1575bf"], weight: 25 },
  { text: "Star HomeDock OS on GitHub, it keeps a small team building", url: REPO_URL, colors: ["#7c2d12", "#c2410c", "#a16207"], weight: 20 },
  { text: "Prism, our window manager, is open source", url: "https://github.com/BansheeTech/prism-wm", colors: ["#312e81", "#6d28d9", "#a21caf"], weight: 15 },
  { text: "Your photos on your own server, in your own hands", url: REPO_URL, colors: ["#831843", "#be185d", "#c2410c"] },
  { text: "Stream your movies and music to every screen at home", url: REPO_URL, colors: ["#4c1d95", "#7e22ce", "#be123c"] },
  { text: "Your files stay at home, not on someone else's cloud", url: REPO_URL, colors: ["#0c4a6e", "#0369a1", "#0f766e"] },
  { text: "Turn that old laptop into your personal cloud", url: REPO_URL, colors: ["#14532d", "#15803d", "#0f766e"] },
  { text: "Run your own apps without touching a terminal", url: REPO_URL, colors: ["#1f2937", "#374151", "#0f766e"] },
  { text: "Nextcloud, Jellyfin or Immich, one click away", url: REPO_URL, colors: ["#1e3a8a", "#4338ca", "#2563eb"] },
  { text: "Edit spreadsheets and documents without uploading them anywhere", url: REPO_URL, colors: ["#064e3b", "#047857", "#0369a1"] },
  { text: "Sign a PDF without printing it", url: REPO_URL, colors: ["#7f1d1d", "#b91c1c", "#9a3412"] },
  { text: "Reach your apps from anywhere, over HTTPS", url: REPO_URL, colors: ["#134e4a", "#0f766e", "#1d4ed8"] },
  { text: "Deleted something by mistake? You have 30 days", url: REPO_URL, colors: ["#78350f", "#b45309", "#9a3412"] },
  { text: "Keep your sensitive files encrypted in the Drop Zone", url: REPO_URL, colors: ["#312e81", "#4f46e5", "#7c3aed"] },
  { text: "All your apps on one desktop, from any browser", url: REPO_URL, colors: ["#0f172a", "#1e40af", "#6d28d9"] },
  { text: "Fix an app's settings without SSH", url: REPO_URL, colors: ["#3f6212", "#4d7c0f", "#0f766e"] },
  { text: "Find out which app is eating your RAM", url: REPO_URL, colors: ["#7c2d12", "#b91c1c", "#be185d"] },
  { text: "Runs on the computer you already have", url: REPO_URL, colors: ["#1e293b", "#0e7490", "#0369a1"] },
  { text: "Every file you own, a double-click away", url: REPO_URL, colors: ["#0c4a6e", "#0284c7", "#4f46e5"] },
  { text: "Tell a friend about HomeDock OS, it helps more than you'd think", url: REPO_URL, colors: ["#881337", "#be123c", "#9d174d"] },
];

const POOL_WEIGHT = POOL_SHARE / TIPS.filter((tip) => tip.weight === undefined).length;

const gradientOf = (tip: LoginTip): string => `linear-gradient(to right, ${tip.colors.join(", ")})`;

const pickTip = (exclude: number): number => {
  const weights = TIPS.map((tip, index) => (index === exclude ? 0 : (tip.weight ?? POOL_WEIGHT)));
  let roll = Math.random() * weights.reduce((sum, weight) => sum + weight, 0);
  for (let index = 0; index < weights.length; index++) {
    roll -= weights[index];
    if (roll < 0) return index;
  }
  return weights.findIndex((weight) => weight > 0);
};

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: "update:isVisible", value: boolean): void;
}>();

const isBannerVisible = ref<boolean>(false);
const currentIndex = ref<number>(pickTip(-1));
const currentTip = computed<LoginTip>(() => TIPS[currentIndex.value]);

let rotationTimer: ReturnType<typeof setInterval> | null = null;

const nextTip = (): void => {
  currentIndex.value = pickTip(currentIndex.value);
};

const startRotation = (): void => {
  if (rotationTimer) return;
  rotationTimer = setInterval(nextTip, ROTATION_MS);
};

const stopRotation = (): void => {
  if (!rotationTimer) return;
  clearInterval(rotationTimer);
  rotationTimer = null;
};

const pauseRotation = (): void => {
  stopRotation();
};

const resumeRotation = (): void => {
  if (isBannerVisible.value) startRotation();
};

const readLastClosed = (): string | null => {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
};

const closeLoginTips = (): void => {
  try {
    localStorage.setItem(STORAGE_KEY, new Date().toISOString().split("T")[0]);
  } catch {}
  isBannerVisible.value = false;
  stopRotation();
  emit("update:isVisible", false);
};

const checkLastClosedAndShowTips = (): void => {
  const lastClosed = readLastClosed();
  const diffDays = lastClosed ? (Date.now() - new Date(lastClosed).getTime()) / (1000 * 3600 * 24) : Infinity;
  const shouldShow = diffDays > 7;

  isBannerVisible.value = shouldShow;
  emit("update:isVisible", shouldShow);
  if (shouldShow) startRotation();
};

watch(
  () => props.isVisible,
  (newValue) => {
    if (newValue) {
      checkLastClosedAndShowTips();
    }
  },
);

onBeforeUnmount(stopRotation);
</script>

<style scoped>
@keyframes rainbow {
  0% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0% 50%;
  }
}

.animate-rainbow {
  animation: rainbow 8s ease infinite;
  background-size: 200% 200%;
}

.slide-down-fade-enter-active,
.slide-down-fade-leave-active {
  transition:
    grid-template-rows 0.6s ease,
    opacity 0.6s ease;
}

.slide-down-fade-enter-from,
.slide-down-fade-leave-to {
  grid-template-rows: 0fr;
  opacity: 0;
}

.slide-down-fade-enter-to,
.slide-down-fade-leave-from {
  grid-template-rows: 1fr;
  opacity: 1;
}

@media (max-width: 639px) {
  .tips-banner {
    min-height: 52px;
  }
}

.tip-backdrop {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.8s ease;
}

.tip-backdrop.is-active {
  opacity: 1;
}

.tip-fade-enter-active,
.tip-fade-leave-active {
  transition:
    opacity 0.35s ease,
    transform 0.35s ease;
}

.tip-fade-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.tip-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
