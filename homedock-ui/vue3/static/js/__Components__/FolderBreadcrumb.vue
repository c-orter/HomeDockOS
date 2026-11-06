<!-- homedock-ui/vue3/static/js/__Components__/FolderBreadcrumb.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div class="folder-breadcrumb" :class="[themeClasses.folderBreadcrumbBg, themeClasses.folderBreadcrumbBorder, $slots.actions && 'has-actions']">
    <Icon :icon="desktopIcon" class="breadcrumb-icon" :class="themeClasses.folderBreadcrumbIcon" />
    <span class="breadcrumb-text breadcrumb-root" :class="themeClasses.folderBreadcrumbText">{{ $t("Desktop") }}</span>
    <Icon :icon="chevronRightIcon" class="breadcrumb-separator" :class="themeClasses.folderBreadcrumbSeparator" />
    <Icon :icon="icon" class="breadcrumb-icon" :class="themeClasses.folderBreadcrumbIcon" />
    <span class="breadcrumb-text breadcrumb-name" :class="themeClasses.folderBreadcrumbText">{{ name }}</span>
    <span class="breadcrumb-count" :class="themeClasses.folderAppCount">({{ count }})</span>
    <div v-if="$slots.actions" class="breadcrumb-actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script lang="ts" setup>
import { useTheme } from "../__Themes__/ThemeSelector";

import { Icon } from "@iconify/vue";
import desktopIcon from "@iconify-icons/mdi/desktop-mac";
import chevronRightIcon from "@iconify-icons/mdi/chevron-right";

defineProps<{ icon: any; name: string; count: string }>();

const { themeClasses } = useTheme();
</script>

<style scoped>
.folder-breadcrumb {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 3.25rem;
  padding: 0 1rem;
  border-bottom: 1px solid transparent;
  flex-shrink: 0;
}

.breadcrumb-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.breadcrumb-separator {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.breadcrumb-text {
  font-size: 0.875rem;
  font-weight: 500;
  white-space: nowrap;
}

.breadcrumb-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.breadcrumb-count {
  font-size: 0.75rem;
  margin-left: 0.25rem;
  white-space: nowrap;
}

.breadcrumb-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: auto;
  flex-shrink: 0;
}

.has-actions .breadcrumb-name {
  flex-shrink: 0;
}

@container window (max-width: 900px) {
  .has-actions .breadcrumb-root,
  .has-actions .breadcrumb-root + .breadcrumb-separator,
  .has-actions .breadcrumb-count,
  .has-actions .breadcrumb-icon:first-child {
    display: none;
  }
}
</style>
