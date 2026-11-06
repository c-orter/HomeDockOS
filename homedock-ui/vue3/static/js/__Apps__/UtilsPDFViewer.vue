<!-- homedock-ui/vue3/static/js/__Apps__/UtilsPDFViewer.vue -->
<!-- Copyright © 2023-2026 Banshee, All Rights Reserved -->
<!-- See LICENSE.md or https://polyformproject.org/licenses/strict/1.0.0/ -->
<!-- https://www.banshee.pro -->

<template>
  <div class="pdf-viewer flex flex-col h-full overflow-hidden">
    <div class="toolbar flex items-center gap-1 px-2 py-1.5 border-b flex-shrink-0" :class="themeClasses.utilityToolbarBorder">
      <Dropdown :trigger="['click']" placement="bottomLeft" :overlay-class-name="menuOverlayClass">
        <button :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="px-3 py-1 text-xs rounded transition-colors cursor-pointer">{{ $t("File") }}</button>
        <template #overlay>
          <Menu>
            <MenuItem key="save" :disabled="!pdfDocument || saving" @click="save">
              <div class="flex items-center gap-2">
                <Icon :icon="contentSaveIcon" class="w-4 h-4" />
                <span>{{ hasSource ? $t("Save") : $t("Save to Documents") }}</span>
                <span class="ml-auto pl-4 text-[10px] opacity-50">Ctrl+S</span>
              </div>
            </MenuItem>
            <MenuItem key="download" :disabled="!pdfDocument" @click="downloadCopy">
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
            <MenuItem key="exit" @click="handleExit">
              <div class="flex items-center gap-2">
                <Icon :icon="exitIcon" class="w-4 h-4" />
                <span>{{ $t("Exit") }}</span>
              </div>
            </MenuItem>
          </Menu>
        </template>
      </Dropdown>

      <div class="w-px h-4 mx-0.5" :class="themeClasses.utilityDivider"></div>

      <button :disabled="!pdfDocument" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover, showSidebar && pdfDocument ? 'bg-blue-500/20' : '']" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Sidebar')" @click="showSidebar = !showSidebar">
        <Icon :icon="sidebarIcon" class="w-4 h-4" />
      </button>

      <button :disabled="currentPage <= 1" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Previous Page')" @click="previousPage">
        <Icon :icon="chevronLeftIcon" class="w-4 h-4" />
      </button>
      <div class="flex items-center gap-1">
        <input v-model="pageInput" :disabled="!pdfDocument" type="text" inputmode="numeric" :class="[themeClasses.windowInputBg, themeClasses.windowText, themeClasses.windowBorder]" class="page-input w-9 h-6 px-1 text-xs text-center rounded border outline-hidden tabular-nums" :aria-label="$t('Page')" @keydown.enter="goToPageInput" @blur="pageInput = String(currentPage)" />
        <span :class="['text-xs whitespace-nowrap tabular-nums', themeClasses.windowTextMuted]">/ {{ totalPages }}</span>
      </div>
      <button :disabled="currentPage >= totalPages" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Next Page')" @click="nextPage">
        <Icon :icon="chevronRightIcon" class="w-4 h-4" />
      </button>

      <div class="toolbar-zoom flex items-center gap-1">
        <div class="w-px h-4 mx-0.5" :class="themeClasses.utilityDivider"></div>

        <button :disabled="!pdfDocument" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Zoom Out (-)')" @click="zoomOut">
          <Icon :icon="magnifyMinusIcon" class="w-4 h-4" />
        </button>
        <span :class="['text-xs min-w-[40px] text-center tabular-nums', themeClasses.windowText]">{{ Math.round(zoom * 100) }}%</span>
        <button :disabled="!pdfDocument" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Zoom In (+)')" @click="zoomIn">
          <Icon :icon="magnifyPlusIcon" class="w-4 h-4" />
        </button>
      </div>

      <div class="toolbar-optional flex items-center gap-1">
        <button :disabled="!pdfDocument" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover, fitMode === 'page-width' ? 'bg-blue-500/20' : '']" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Fit to Width')" @click="setFit('page-width')">
          <Icon :icon="arrowExpandHorizontalIcon" class="w-4 h-4" />
        </button>
        <button :disabled="!pdfDocument" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover, fitMode === 'page-fit' ? 'bg-blue-500/20' : '']" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Fit to Page')" @click="setFit('page-fit')">
          <Icon :icon="fitToPageIcon" class="w-4 h-4" />
        </button>
        <button :disabled="!pdfDocument" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Rotate')" @click="rotate">
          <Icon :icon="rotateRightIcon" class="w-4 h-4" />
        </button>
      </div>

      <div class="flex-1"></div>

      <Transition name="drop-fade">
        <button v-if="showSavePill" type="button" :disabled="saving || saveState === 'saved'" :title="hasSource ? $t('Save') : $t('Save to Documents')" :aria-label="hasSource ? $t('Save') : $t('Save to Documents')" :class="saveState === 'saved' ? themeClasses.storeCardInstalledPill : themeClasses.storeCardGetPill" class="drop-save-button flex items-center justify-center gap-1.5 h-7 px-3.5 rounded-full border-0 text-xs font-semibold cursor-pointer flex-shrink-0 transition-colors duration-150 disabled:cursor-default" @click="save">
          <Icon :icon="saving ? loadingIcon : saveState === 'saved' ? checkIcon : saveIcon" :class="saving ? 'animate-spin' : ''" class="w-3.5 h-3.5 flex-shrink-0" />
          <span class="drop-save-label">{{ saveState === "saved" ? $t("Saved") : hasSource ? $t("Save") : $t("Save to Documents") }}</span>
        </button>
      </Transition>

      <button :disabled="!pdfDocument" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover, showFind ? 'bg-blue-500/20' : '']" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Find (Ctrl+F)')" @click="toggleFind">
        <Icon :icon="magnifyIcon" class="w-4 h-4" />
      </button>
      <button :disabled="!pdfDocument" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover, showAnnotations && pdfDocument ? 'bg-blue-500/20' : '']" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Annotate')" @click="toggleAnnotations">
        <Icon :icon="annotateIcon" class="w-4 h-4" />
      </button>
    </div>

    <div v-if="showAnnotations && pdfDocument" class="annotate-bar flex flex-wrap items-center gap-x-1 gap-y-1.5 px-2 py-1 border-b flex-shrink-0" :class="themeClasses.utilityToolbarBorder">
      <button v-for="tool in TOOLS" :key="tool.mode" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover, editorMode === tool.mode ? 'bg-blue-500/20' : '']" class="p-1 rounded transition-colors cursor-pointer" :title="$t(tool.label)" @click="selectTool(tool.mode)">
        <Icon :icon="tool.icon" class="w-4 h-4" />
      </button>
      <button :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors cursor-pointer" :title="$t('Add Signature')" @click="showSignatureDialog = true">
        <Icon :icon="signatureIcon" class="w-4 h-4" />
      </button>

      <template v-if="activeStyle">
        <div class="w-px h-4 mx-1" :class="themeClasses.utilityDivider"></div>
        <div class="flex items-center gap-1.5">
          <button v-for="color in activeStyle.swatches" :key="color" type="button" class="annotate-swatch w-4 h-4 rounded-full border-0 cursor-pointer flex-shrink-0" :class="{ active: activeStyle.color === color }" :style="{ backgroundColor: color }" :title="$t('Color')" @click="setToolColor(color)"></button>
        </div>
        <template v-if="activeStyle.size">
          <div class="w-px h-4 mx-1" :class="themeClasses.utilityDivider"></div>
          <input :value="activeStyle.size.value" type="range" :min="activeStyle.size.min" :max="activeStyle.size.max" class="annotate-size w-20 cursor-pointer" :title="$t(activeStyle.size.label)" @input="setToolSize(Number(($event.target as HTMLInputElement).value))" />
        </template>
      </template>

      <div class="flex-1"></div>

      <button :disabled="!canUndo" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Undo')" @click="uiManager?.undo()">
        <Icon :icon="undoIcon" class="w-4 h-4" />
      </button>
      <button :disabled="!canRedo" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Redo')" @click="uiManager?.redo()">
        <Icon :icon="redoIcon" class="w-4 h-4" />
      </button>
      <button :disabled="!hasSelectedEditor" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Delete')" @click="uiManager?.delete()">
        <Icon :icon="deleteIcon" class="w-4 h-4" />
      </button>
    </div>

    <div v-if="showFind && pdfDocument" class="find-bar flex items-center gap-1.5 px-2 py-1 border-b flex-shrink-0" :class="themeClasses.utilityToolbarBorder">
      <div class="relative flex-1 min-w-0 max-w-xs">
        <Icon :icon="magnifyIcon" :class="['absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5', themeClasses.explorerSearchIcon]" />
        <input ref="findInputRef" v-model="findQuery" type="text" :placeholder="$t('Find in document...')" :class="[themeClasses.explorerSearchInput, themeClasses.explorerSearchInputText]" class="w-full h-6 pl-7 pr-2 text-xs rounded-md border outline-hidden" @keydown.enter.prevent="findAgain($event.shiftKey)" @keydown.esc.prevent="closeFind" />
      </div>
      <span :class="['text-[11px] whitespace-nowrap tabular-nums', findNotFound ? 'text-red-500' : themeClasses.windowTextMuted]">{{ findStatus }}</span>
      <button :disabled="!findCount.total" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Previous Match')" @click="findAgain(true)">
        <Icon :icon="chevronUpIcon" class="w-4 h-4" />
      </button>
      <button :disabled="!findCount.total" :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="p-1 rounded transition-colors disabled:opacity-30 cursor-pointer disabled:cursor-default" :title="$t('Next Match')" @click="findAgain(false)">
        <Icon :icon="chevronDownIcon" class="w-4 h-4" />
      </button>
      <button :class="[themeClasses.windowText, themeClasses.windowButtonBgHover]" class="ml-auto p-1 rounded transition-colors cursor-pointer" :title="$t('Close')" @click="closeFind">
        <Icon :icon="closeIcon" class="w-4 h-4" />
      </button>
    </div>

    <div class="flex flex-1 min-h-0">
      <aside v-if="showSidebar && pdfDocument" class="pdf-sidebar flex flex-col w-48 flex-shrink-0 border-r" :class="themeClasses.fileExplorerSidebar">
        <div v-if="outline.length" class="flex justify-center px-2 pt-2">
          <SegmentedControl v-model="sidebarView" :options="sidebarOptions" />
        </div>
        <PDFThumbnails v-if="sidebarView === 'pages' || !outline.length" :pdf="pdfDocument" :current-page="currentPage" :rotation="rotation" :revision="revision" @select="goToPage" @menu="openPageMenu" />
        <div v-else class="flex-1 min-h-0 overflow-y-auto py-2">
          <button v-for="(entry, index) in outline" :key="index" type="button" :class="[themeClasses.fileExplorerSidebarItem]" class="outline-item block w-full text-left text-xs py-1 pr-2 bg-transparent border-0 cursor-pointer truncate" :style="{ paddingLeft: `${10 + entry.depth * 12}px` }" :title="entry.title" @click="openOutlineEntry(entry)">{{ entry.title }}</button>
        </div>
      </aside>

      <div class="relative flex-1 min-w-0" :class="themeClasses.imageViewerBg" @dragenter.prevent.stop="onDragEnter" @dragover.prevent.stop="onDragOver" @dragleave.stop="onDragLeave" @drop.prevent.stop="onDrop">
        <div ref="containerRef" class="pdf-container absolute inset-0 overflow-auto" :class="{ invisible: !pdfDocument || isLoading || error }" tabindex="0" @wheel="handleWheel" @touchstart="handleTouchStart" @touchmove="handleTouchMove" @touchend="handleTouchEnd" @touchcancel="handleTouchEnd">
          <div ref="viewerRef" class="pdfViewer"></div>
        </div>

        <Transition name="drop-fade">
          <div v-if="isDragOver" class="absolute inset-3 z-10 flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-blue-500 bg-blue-500/10 pointer-events-none">
            <Icon :icon="filePdfIcon" class="w-10 h-10 text-blue-500" />
            <span class="text-sm font-semibold text-blue-500">{{ $t("Drop to open") }}</span>
          </div>
        </Transition>

        <div v-if="isLoading" class="absolute inset-0 flex items-center justify-center">
          <div class="flex flex-col items-center gap-3">
            <Icon :icon="loadingIcon" class="w-8 h-8 animate-spin" :class="themeClasses.windowTextMuted" />
            <span :class="['text-sm', themeClasses.windowTextMuted]">{{ $t("Loading PDF...") }}</span>
          </div>
        </div>

        <div v-else-if="error" class="absolute inset-0 flex items-center justify-center">
          <div class="flex flex-col items-center gap-3 text-center p-8">
            <div class="w-16 h-16 rounded-2xl flex items-center justify-center bg-red-500/10">
              <Icon :icon="alertIcon" class="w-8 h-8 text-red-500" />
            </div>
            <h3 :class="['text-lg font-medium', themeClasses.windowText]">{{ $t("Cannot Display PDF") }}</h3>
            <p :class="['text-sm max-w-xs', themeClasses.windowTextMuted]">{{ error }}</p>
          </div>
        </div>

        <div v-else-if="!pdfDocument" class="absolute inset-0 flex items-center justify-center">
          <div class="flex flex-col items-center gap-3 text-center p-8">
            <div class="w-16 h-16 rounded-2xl flex items-center justify-center" :class="themeClasses.imageViewerBg">
              <Icon :icon="filePdfIcon" class="w-8 h-8" :class="themeClasses.windowTextMuted" />
            </div>
            <h3 :class="['text-lg font-medium', themeClasses.windowText]">{{ $t("No PDF") }}</h3>
            <p :class="['text-sm max-w-xs', themeClasses.windowTextMuted]">{{ $t("Open a PDF file to view it here.") }}</p>
            <button type="button" :class="[themeClasses.storeCardGetPill]" class="flex items-center gap-1.5 h-8 mt-1 px-4 rounded-full border-0 text-xs font-semibold cursor-pointer transition-colors duration-150" @click="browseDocuments">
              <Icon :icon="folderFileIcon" class="w-4 h-4" />
              {{ $t("Browse Documents") }}
            </button>
            <span :class="['text-xs', themeClasses.windowTextMuted]">{{ $t("or drop a PDF here") }}</span>
          </div>
        </div>
      </div>
    </div>

    <StatusBar :icon="filePdfIcon" :message="statusMessage" :info="totalPages > 0 ? $t('Page {n} of {total}', { n: currentPage, total: totalPages }) : ''" :loading="saving">
      <template v-if="isValidated" #extra>
        <div class="flex items-center gap-1 text-green-500 text-[10px]">
          <Icon :icon="shieldCheckIcon" class="w-3.5 h-3.5" />
          <span>{{ $t("Verified") }}</span>
        </div>
      </template>
      <template #help>
        <div class="space-y-3 max-w-sm">
          <div class="flex items-center gap-2">
            <StatusBarHelpIcon :icon="filePdfIcon" />
            <h4 :class="['text-base font-semibold', themeClasses.statusBarText]">{{ $t("PDF Editor") }}</h4>
          </div>
          <div :class="['text-[10px] md:text-xs md:leading-4 space-y-2.5 leading-relaxed', themeClasses.statusBarInfo]">
            <p>{{ $t("A secure PDF editor powered by PDF.js.") }}</p>
            <div class="space-y-1.5">
              <div class="flex items-start gap-2">
                <Icon :icon="shieldCheckIcon" class="w-3.5 h-3.5 mt-0.5 text-green-500 flex-shrink-0" />
                <p>{{ $t("Secure: PDFs are rendered safely without executing embedded scripts.") }}</p>
              </div>
              <div class="flex items-start gap-2">
                <Icon :icon="annotateIcon" class="w-3.5 h-3.5 mt-0.5 text-blue-500 flex-shrink-0" />
                <p>{{ $t("Annotate: Highlight text, add notes, draw, insert images and sign. Form fields can be filled in directly.") }}</p>
              </div>
              <div class="flex items-start gap-2">
                <Icon :icon="sidebarIcon" class="w-3.5 h-3.5 mt-0.5 text-purple-500 flex-shrink-0" />
                <p>{{ $t("Pages: Right-click a thumbnail in the sidebar to move, delete or extract that page.") }}</p>
              </div>
              <div class="flex items-start gap-2">
                <Icon :icon="magnifyIcon" class="w-3.5 h-3.5 mt-0.5 text-amber-500 flex-shrink-0" />
                <p>{{ $t("Find: Press Ctrl+F to search the text of the document.") }}</p>
              </div>
            </div>
          </div>
        </div>
      </template>
    </StatusBar>

    <ContextMenu :visible="pageMenu.visible" :x="pageMenu.x" :y="pageMenu.y" :items="pageMenuItems" @close="pageMenu.visible = false" />

    <PDFSignatureDialog v-model:visible="showSignatureDialog" @confirm="insertSignature" />

    <AppDialog v-model:visible="showPasswordDialog" title="Password Required" ok-text="Open" cancel-text="Cancel" :icon="lockIcon" :mask-closable="false" :ok-disabled="!passwordInput" @ok="submitPassword" @cancel="cancelPassword">
      <div class="space-y-2">
        <p :class="['text-sm m-0', themeClasses.notTextDown]">{{ passwordRetry ? $t("Incorrect password. Please try again.") : $t("This PDF is protected. Enter its password to open it.") }}</p>
        <input ref="passwordInputRef" v-model="passwordInput" type="password" autocomplete="off" :class="[themeClasses.windowInputBg, themeClasses.windowText, themeClasses.windowBorder]" class="w-full px-3 py-2 text-sm rounded-lg border outline-hidden" @keyup.enter="submitPassword" />
      </div>
    </AppDialog>

    <AppDialog v-model:visible="showExtractWarning" title="Extract Page" content="The extracted page will be saved to Storage/Documents without Drop Zone encryption." ok-text="Extract Page" cancel-text="Cancel" type="warning" @ok="confirmExtractPage" @cancel="showExtractWarning = false" />

    <AppDialog v-model:visible="showUnsavedDialog" title="Unsaved Changes" :content="unsavedDialogMessage" ok-text="Save" cancel-text="Cancel" :dismiss-text="$t('Don\'t Save')" type="warning" :mask-closable="false" @ok="handleUnsavedSave" @cancel="handleUnsavedCancel" @dismiss="handleUnsavedDiscard" />
  </div>
</template>

<script lang="ts" setup>
import { ref, shallowRef, computed, onMounted, onUnmounted, watch, nextTick, reactive } from "vue";
import { useI18n } from "vue-i18n";

import { Dropdown, Menu, MenuItem, MenuDivider } from "ant-design-vue";

import * as pdfjsLib from "pdfjs-dist";
import { AnnotationEditorParamsType, AnnotationEditorType, AnnotationMode, PasswordResponses } from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { EventBus, PDFFindController, PDFLinkService, PDFViewer } from "pdfjs-dist/web/pdf_viewer.mjs";
import "pdfjs-dist/web/pdf_viewer.css";

import { Icon } from "@iconify/vue";
import filePdfIcon from "@iconify-icons/mdi/file-pdf-box";
import magnifyPlusIcon from "@iconify-icons/mdi/magnify-plus-outline";
import magnifyMinusIcon from "@iconify-icons/mdi/magnify-minus-outline";
import magnifyIcon from "@iconify-icons/mdi/magnify";
import fitToPageIcon from "@iconify-icons/mdi/fit-to-page-outline";
import arrowExpandHorizontalIcon from "@iconify-icons/mdi/arrow-expand-horizontal";
import chevronLeftIcon from "@iconify-icons/mdi/chevron-left";
import chevronRightIcon from "@iconify-icons/mdi/chevron-right";
import chevronUpIcon from "@iconify-icons/mdi/chevron-up";
import chevronDownIcon from "@iconify-icons/mdi/chevron-down";
import closeIcon from "@iconify-icons/mdi/close";
import loadingIcon from "@iconify-icons/mdi/loading";
import alertIcon from "@iconify-icons/mdi/alert-circle-outline";
import shieldCheckIcon from "@iconify-icons/mdi/shield-check-outline";
import folderFileIcon from "@iconify-icons/mdi/folder-file";
import saveIcon from "@iconify-icons/mdi/content-save-outline";
import contentSaveIcon from "@iconify-icons/mdi/content-save";
import downloadIcon from "@iconify-icons/mdi/download";
import exitIcon from "@iconify-icons/mdi/exit-to-app";
import checkIcon from "@iconify-icons/mdi/check";
import sidebarIcon from "@iconify-icons/mdi/page-layout-sidebar-left";
import rotateRightIcon from "@iconify-icons/mdi/rotate-right";
import annotateIcon from "@iconify-icons/mdi/draw-pen";
import cursorIcon from "@iconify-icons/mdi/cursor-default-outline";
import markerIcon from "@iconify-icons/mdi/marker";
import formatTextIcon from "@iconify-icons/mdi/format-text";
import drawIcon from "@iconify-icons/mdi/draw";
import imagePlusIcon from "@iconify-icons/mdi/image-plus";
import signatureIcon from "@iconify-icons/mdi/signature-freehand";
import undoIcon from "@iconify-icons/mdi/undo";
import redoIcon from "@iconify-icons/mdi/redo";
import deleteIcon from "@iconify-icons/mdi/delete-outline";
import arrowUpIcon from "@iconify-icons/mdi/arrow-up";
import arrowDownIcon from "@iconify-icons/mdi/arrow-down";
import fileExportIcon from "@iconify-icons/mdi/file-export-outline";
import lockIcon from "@iconify-icons/mdi/lock-outline";

import { useTheme } from "../__Themes__/ThemeSelector";
import { useWindowStore } from "../__Stores__/windowStore";
import { useResponsive } from "../__Composables__/useResponsive";
import { useExternalFile, triggerDownload, type ExternalBinaryFile, type ExternalFileTarget } from "../__Composables__/useExternalFile";

import StatusBar from "../__Components__/StatusBar.vue";
import StatusBarHelpIcon from "../__Components__/StatusBarHelpIcon.vue";
import AppDialog from "../__Components__/AppDialog.vue";
import ContextMenu, { type ContextMenuItem } from "../__Components__/ContextMenu.vue";
import SegmentedControl from "../__Components__/SegmentedControl.vue";
import PDFThumbnails from "../__Components__/PDFThumbnails.vue";
import PDFSignatureDialog from "../__Components__/PDFSignatureDialog.vue";

import { notifyError, notifySuccess } from "../__Components__/Notifications.vue";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
(globalThis as { pdfjsLib?: typeof pdfjsLib }).pdfjsLib = pdfjsLib;

type FitMode = "page-width" | "page-fit" | "custom";

interface OutlineNode {
  title: string;
  dest: string | unknown[] | null;
  url: string | null;
  items: OutlineNode[];
}

interface OutlineEntry {
  title: string;
  dest: string | unknown[] | null;
  url: string | null;
  depth: number;
}

interface ToolStyle {
  swatches: string[];
  colorParam: number;
  color: string;
  size?: { param: number; value: number; min: number; max: number; label: string };
}

const PDF_MIME = "application/pdf";

const PDF_MAGIC_BYTES = [0x25, 0x50, 0x44, 0x46, 0x2d];

const DOCUMENTS_FOLDER = "Documents";

const SAVED_FEEDBACK_MS = 2000;

const MIN_ZOOM = 0.25;

const MAX_ZOOM = 4;

const SIGNATURE_WIDTH = 220;

const INK_SWATCHES = ["#111827", "#dc2626", "#2563eb", "#16a34a", "#f59e0b"];

const HIGHLIGHT_COLORS = [
  ["yellow", "#FFFF98"],
  ["green", "#53FFBC"],
  ["blue", "#80EBFF"],
  ["pink", "#FFCBE6"],
  ["red", "#FF4F5F"],
];

const HIGHLIGHT_SWATCHES = HIGHLIGHT_COLORS.map(([, color]) => color);

const TOOLS = [
  { mode: AnnotationEditorType.NONE, icon: cursorIcon, label: "Select" },
  { mode: AnnotationEditorType.HIGHLIGHT, icon: markerIcon, label: "Highlight" },
  { mode: AnnotationEditorType.FREETEXT, icon: formatTextIcon, label: "Text" },
  { mode: AnnotationEditorType.INK, icon: drawIcon, label: "Draw" },
  { mode: AnnotationEditorType.STAMP, icon: imagePlusIcon, label: "Image" },
];

const props = defineProps<{
  _windowId?: string;
  pdfFile?: ExternalBinaryFile;
}>();

const { themeClasses } = useTheme();
const { t } = useI18n();
const windowStore = useWindowStore();
const { savedDescription, saveToSource, saveNewToStorage } = useExternalFile();
const { isDesktopOrWider } = useResponsive();

const containerRef = ref<HTMLDivElement | null>(null);
const viewerRef = ref<HTMLDivElement | null>(null);
const findInputRef = ref<HTMLInputElement | null>(null);
const passwordInputRef = ref<HTMLInputElement | null>(null);

const pdfDocument = shallowRef<PDFDocumentProxy | null>(null);
const target = shallowRef<ExternalFileTarget | null>(null);
const fileName = ref("");
const originalWindowTitle = props._windowId ? windowStore.getWindowById(props._windowId)?.title || "" : "";
const isLoading = ref(false);
const error = ref<string | null>(null);
const isValidated = ref(false);
const revision = ref(0);

const currentPage = ref(1);
const totalPages = ref(0);
const pageInput = ref("1");
const zoom = ref(1);
const fitMode = ref<FitMode>("page-width");
const rotation = ref(0);

const showSidebar = ref(isDesktopOrWider.value);
const sidebarView = ref<"pages" | "outline">("pages");
const outline = shallowRef<OutlineEntry[]>([]);

const showAnnotations = ref(false);
const editorMode = ref<number>(AnnotationEditorType.NONE);
const canUndo = ref(false);
const canRedo = ref(false);
const hasSelectedEditor = ref(false);

const toolStyles = reactive<Record<number, ToolStyle>>({
  [AnnotationEditorType.HIGHLIGHT]: { swatches: HIGHLIGHT_SWATCHES, colorParam: AnnotationEditorParamsType.HIGHLIGHT_COLOR, color: HIGHLIGHT_SWATCHES[0] },
  [AnnotationEditorType.FREETEXT]: { swatches: INK_SWATCHES, colorParam: AnnotationEditorParamsType.FREETEXT_COLOR, color: INK_SWATCHES[0], size: { param: AnnotationEditorParamsType.FREETEXT_SIZE, value: 14, min: 8, max: 72, label: "Font Size" } },
  [AnnotationEditorType.INK]: { swatches: INK_SWATCHES, colorParam: AnnotationEditorParamsType.INK_COLOR, color: INK_SWATCHES[2], size: { param: AnnotationEditorParamsType.INK_THICKNESS, value: 2, min: 1, max: 20, label: "Thickness" } },
});

const showFind = ref(false);
const findQuery = ref("");
const findCount = ref({ current: 0, total: 0 });
const findNotFound = ref(false);

const isModified = ref(false);
const saving = ref(false);
const saveState = ref<"idle" | "saved">("idle");
const showUnsavedDialog = ref(false);
const showSignatureDialog = ref(false);
const pendingFile = shallowRef<ExternalBinaryFile | null>(null);

const showPasswordDialog = ref(false);
const passwordInput = ref("");
const passwordRetry = ref(false);
let passwordCallback: ((password: string) => void) | null = null;
let passwordReject: (() => void) | null = null;

const pageMenu = reactive({ visible: false, x: 0, y: 0, page: 0 });
const showExtractWarning = ref(false);
const pendingExtractPage = ref(0);

const isDragOver = ref(false);
let dragDepth = 0;

let eventBus: EventBus | null = null;
let linkService: PDFLinkService | null = null;
let findController: PDFFindController | null = null;
let pdfViewer: PDFViewer | null = null;
let uiManager: any = null;
let resizeObserver: ResizeObserver | null = null;
let loadToken = 0;
let pinchDistance = 0;
let pendingSignature = false;
let viewerReadyResolve: () => void = () => {};
const viewerReady = new Promise<void>((resolve) => (viewerReadyResolve = resolve));

const hasSource = computed(() => Boolean(target.value?.source));

const showSavePill = computed(() => Boolean(pdfDocument.value) && (!hasSource.value || isModified.value || saveState.value === "saved"));

const menuOverlayClass = computed(() => (themeClasses.value.scopeSelector === "aero-mode-theme" ? "dark-mode-theme" : themeClasses.value.scopeSelector));

const statusMessage = computed(() => (fileName.value ? `${fileName.value}${isModified.value ? " *" : ""}` : t("No PDF")));

const unsavedDialogMessage = computed(() => t('"{name}" has unsaved changes. Do you want to save before closing?', { name: fileName.value }));

const activeStyle = computed(() => toolStyles[editorMode.value] ?? null);

const sidebarOptions = computed(() => [
  { value: "pages", label: t("Pages") },
  { value: "outline", label: t("Outline") },
]);

const findStatus = computed(() => {
  if (!findQuery.value) return "";
  if (findNotFound.value) return t("Not found");
  if (!findCount.value.total) return "";
  return t("{current} of {total}", { current: findCount.value.current, total: findCount.value.total });
});

const pageMenuItems = computed<ContextMenuItem[]>(() => {
  const page = pageMenu.page;
  return [
    { label: "Move Up", icon: arrowUpIcon, disabled: page <= 1, action: () => movePage(page, -1) },
    { label: "Move Down", icon: arrowDownIcon, disabled: page >= totalPages.value, action: () => movePage(page, 1) },
    { divider: true },
    { label: "Extract Page", icon: fileExportIcon, action: () => requestExtractPage(page) },
    { label: "Delete Page", icon: deleteIcon, disabled: totalPages.value <= 1, action: () => deletePage(page) },
  ];
});

function updateWindowTitle() {
  if (!props._windowId || !originalWindowTitle) return;
  windowStore.updateWindowTitle(props._windowId, fileName.value ? `${originalWindowTitle} - ${fileName.value}${isModified.value ? " *" : ""}` : originalWindowTitle);
}

watch([fileName, isModified], updateWindowTitle);

watch(currentPage, (page) => (pageInput.value = String(page)));

function targetOf(source: ExternalBinaryFile): ExternalFileTarget {
  const { buffer: _buffer, ...rest } = source;
  return rest;
}

function validatePDFMagicBytes(buffer: ArrayBuffer): boolean {
  const bytes = new Uint8Array(buffer);
  return PDF_MAGIC_BYTES.every((b, i) => bytes[i] === b);
}

function flattenOutline(nodes: OutlineNode[] | null, depth = 0, into: OutlineEntry[] = []): OutlineEntry[] {
  for (const node of nodes ?? []) {
    into.push({ title: node.title, dest: node.dest, url: node.url, depth });
    flattenOutline(node.items, depth + 1, into);
  }
  return into;
}

async function initViewer() {
  const container = containerRef.value;
  const viewer = viewerRef.value;
  if (!container || !viewer) return;

  const { EventBus, PDFLinkService, PDFFindController, PDFViewer, LinkTarget } = await import("pdfjs-dist/web/pdf_viewer.mjs");

  eventBus = new EventBus();
  linkService = new PDFLinkService({ eventBus, externalLinkTarget: LinkTarget.BLANK, externalLinkRel: "noopener noreferrer nofollow" });
  findController = new PDFFindController({ eventBus, linkService, updateMatchesCountOnProgress: true });
  pdfViewer = new PDFViewer({
    container,
    viewer,
    eventBus,
    linkService,
    findController,
    annotationMode: AnnotationMode.ENABLE_FORMS,
    annotationEditorMode: AnnotationEditorType.NONE,
    annotationEditorHighlightColors: HIGHLIGHT_COLORS.map(([name, color]) => `${name}=${color}`).join(","),
  });
  linkService.setViewer(pdfViewer);

  eventBus.on("pagesinit", () => {
    if (!pdfViewer) return;
    pdfViewer.pagesRotation = rotation.value;
    pdfViewer.currentScaleValue = fitMode.value === "custom" ? String(zoom.value) : fitMode.value;
  });
  eventBus.on("pagechanging", ({ pageNumber }: { pageNumber: number }) => (currentPage.value = pageNumber));
  eventBus.on("scalechanging", ({ scale, presetValue }: { scale: number; presetValue?: string }) => {
    zoom.value = scale;
    fitMode.value = presetValue === "page-width" || presetValue === "page-fit" ? presetValue : "custom";
  });
  eventBus.on("annotationeditoruimanager", ({ uiManager: manager }: { uiManager: any }) => (uiManager = manager));
  eventBus.on("switchannotationeditormode", (options: { mode: number }) => {
    if (pdfViewer) pdfViewer.annotationEditorMode = options;
  });
  eventBus.on("annotationeditormodechanged", ({ mode }: { mode: number }) => {
    editorMode.value = mode;
    if (!uiManager?.hasSelection) applyToolDefaults();
  });
  eventBus.on("editingstateschanged", ({ details }: { details: Record<string, boolean> }) => {
    canUndo.value = Boolean(details.hasSomethingToUndo);
    canRedo.value = Boolean(details.hasSomethingToRedo);
    hasSelectedEditor.value = Boolean(details.hasSelectedEditor);
  });
  eventBus.on("reporttelemetry", ({ source, details }: { source: any; details?: { data?: { action?: string } } }) => {
    if (!pendingSignature || details?.data?.action !== "inserted_image") return;
    pendingSignature = false;
    fitSignature(source);
  });
  eventBus.on("annotationeditorparamschanged", ({ details }: { details: [number, unknown][] }) => syncToolParams(details));
  eventBus.on("updatefindmatchescount", ({ matchesCount }: { matchesCount: { current: number; total: number } }) => (findCount.value = matchesCount));
  eventBus.on("updatefindcontrolstate", ({ state, matchesCount }: { state: number; matchesCount: { current: number; total: number } }) => {
    findNotFound.value = state === 1;
    if (matchesCount) findCount.value = matchesCount;
  });

  resizeObserver = new ResizeObserver(() => {
    if (pdfViewer?.pdfDocument && fitMode.value !== "custom") pdfViewer.currentScaleValue = fitMode.value;
  });
  resizeObserver.observe(container);

  viewerReadyResolve();
}

function applyToolDefaults() {
  if (!uiManager) return;

  for (const style of Object.values(toolStyles)) {
    uiManager.updateParams(style.colorParam, style.color);
    if (style.size) uiManager.updateParams(style.size.param, style.size.value);
  }
}

function syncToolParams(details: [number, unknown][]) {
  if (!uiManager?.hasSelection) return;

  for (const [param, value] of details) {
    for (const style of Object.values(toolStyles)) {
      if (style.colorParam === param && typeof value === "string") style.color = value;
      if (style.size?.param === param && typeof value === "number") style.size.value = value;
    }
  }
}

function requestPassword(update: (password: string) => void, reason: number) {
  passwordRetry.value = reason === PasswordResponses.INCORRECT_PASSWORD;
  passwordInput.value = "";
  passwordCallback = update;
  showPasswordDialog.value = true;
  nextTick(() => passwordInputRef.value?.focus());
}

function submitPassword() {
  if (!passwordInput.value || !passwordCallback) return;
  showPasswordDialog.value = false;
  passwordCallback(passwordInput.value);
  passwordCallback = null;
}

function cancelPassword() {
  showPasswordDialog.value = false;
  passwordCallback = null;
  passwordReject?.();
}

async function openDocument(buffer: ArrayBuffer, name: string, nextTarget: ExternalFileTarget | null, options: { keepModified?: boolean; page?: number } = {}) {
  const token = ++loadToken;

  isLoading.value = true;
  error.value = null;
  isValidated.value = false;
  fileName.value = name;
  target.value = nextTarget;
  saveState.value = "idle";
  if (!options.keepModified) isModified.value = false;

  try {
    if (!validatePDFMagicBytes(buffer)) {
      throw new Error(t("File does not appear to be a valid PDF. Magic bytes validation failed."));
    }

    isValidated.value = true;
    await viewerReady;

    const task = pdfjsLib.getDocument({ data: new Uint8Array(buffer.slice(0)), enableXfa: false, verbosity: 0 });
    task.onPassword = requestPassword;
    passwordReject = () => task.destroy();

    const pdf = await task.promise;
    passwordReject = null;
    if (token !== loadToken) {
      task.destroy();
      return;
    }

    const previous = pdfDocument.value;
    Object.assign(pdf.annotationStorage, { onSetModified: () => (isModified.value = true) });

    pdfDocument.value = pdf;
    totalPages.value = pdf.numPages;
    currentPage.value = 1;
    revision.value++;
    editorMode.value = AnnotationEditorType.NONE;
    uiManager = null;

    pdfViewer!.setDocument(pdf);
    linkService!.setDocument(pdf, null);
    previous?.loadingTask.destroy();

    if (options.page) {
      eventBus!.on("pagesinit", () => pdfViewer && (pdfViewer.currentPageNumber = Math.min(options.page!, pdf.numPages)), { once: true });
    }

    outline.value = flattenOutline((await pdf.getOutline()) as OutlineNode[] | null);
    if (findQuery.value && showFind.value) runFind("");
  } catch (err: any) {
    if (token !== loadToken) return;
    if (err?.name === "PasswordException" || err?.message === "Worker was destroyed" || err?.name === "AbortException") {
      error.value = t("This PDF is protected and could not be opened without its password.");
    } else {
      console.error("Failed to load PDF:", err);
      error.value = err?.message || t("Failed to load PDF");
    }
  } finally {
    if (token === loadToken) isLoading.value = false;
  }
}

function loadFile(next: ExternalBinaryFile) {
  openDocument(next.buffer, next.name, next.source ? targetOf(next) : null);
}

function goToPage(page: number) {
  if (!pdfViewer?.pdfDocument) return;
  pdfViewer.currentPageNumber = Math.max(1, Math.min(page, totalPages.value));
}

function goToPageInput() {
  const page = Number.parseInt(pageInput.value, 10);
  if (Number.isFinite(page)) goToPage(page);
  pageInput.value = String(currentPage.value);
}

function nextPage() {
  pdfViewer?.nextPage();
}

function previousPage() {
  pdfViewer?.previousPage();
}

function zoomIn() {
  if (!pdfViewer?.pdfDocument) return;
  pdfViewer.currentScale = Math.min(MAX_ZOOM, zoom.value * 1.25);
}

function zoomOut() {
  if (!pdfViewer?.pdfDocument) return;
  pdfViewer.currentScale = Math.max(MIN_ZOOM, zoom.value / 1.25);
}

function setFit(mode: "page-width" | "page-fit") {
  if (!pdfViewer?.pdfDocument) return;
  pdfViewer.currentScaleValue = mode;
}

function rotate() {
  if (!pdfViewer?.pdfDocument) return;
  rotation.value = (rotation.value + 90) % 360;
  pdfViewer.pagesRotation = rotation.value;
}

function openOutlineEntry(entry: OutlineEntry) {
  if (entry.dest) linkService?.goToDestination(entry.dest as any);
  else if (entry.url) window.open(entry.url, "_blank", "noopener,noreferrer");
}

function handleWheel(event: WheelEvent) {
  if (!event.ctrlKey && !event.metaKey) return;
  if (!pdfViewer?.pdfDocument) return;

  event.preventDefault();
  const factor = Math.exp(-event.deltaY / 200);
  const next = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom.value * factor));
  pdfViewer.updateScale({ scaleFactor: next / zoom.value, origin: [event.clientX, event.clientY] });
}

function touchDistance(touches: TouchList) {
  return Math.hypot(touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY);
}

function handleTouchStart(event: TouchEvent) {
  if (event.touches.length === 2) pinchDistance = touchDistance(event.touches);
}

function handleTouchMove(event: TouchEvent) {
  if (event.touches.length !== 2 || !pinchDistance || !pdfViewer?.pdfDocument) return;

  event.preventDefault();
  const distance = touchDistance(event.touches);
  const next = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom.value * (distance / pinchDistance)));
  const origin: [number, number] = [(event.touches[0].clientX + event.touches[1].clientX) / 2, (event.touches[0].clientY + event.touches[1].clientY) / 2];
  pdfViewer.updateScale({ scaleFactor: next / zoom.value, origin });
  pinchDistance = distance;
}

function handleTouchEnd(event: TouchEvent) {
  if (event.touches.length < 2) pinchDistance = 0;
}

function toggleAnnotations() {
  showAnnotations.value = !showAnnotations.value;
  if (!showAnnotations.value) selectTool(AnnotationEditorType.NONE);
}

function selectTool(mode: number) {
  if (!pdfViewer?.pdfDocument) return;

  uiManager?.unselectAll();

  if (mode === AnnotationEditorType.STAMP) {
    uiManager?.currentLayer?.pasteEditor({ mode: AnnotationEditorType.STAMP }, {});
    return;
  }

  pdfViewer.annotationEditorMode = { mode };
}

function setToolColor(color: string) {
  const style = activeStyle.value;
  if (!style) return;
  style.color = color;
  uiManager?.updateParams(style.colorParam, color);
}

function setToolSize(value: number) {
  const size = activeStyle.value?.size;
  if (!size) return;
  size.value = value;
  uiManager?.updateParams(size.param, value);
}

function insertSignature(file: File) {
  if (!showAnnotations.value) showAnnotations.value = true;
  pendingSignature = true;
  uiManager?.currentLayer?.pasteEditor({ mode: AnnotationEditorType.STAMP }, { bitmapFile: file });
}

function fitSignature(editor: any) {
  const [pageWidth, pageHeight] = editor.pageDimensions as [number, number];
  const currentWidth = editor.width * pageWidth;
  if (!currentWidth || currentWidth <= SIGNATURE_WIDTH) return;

  const aspect = (editor.height * pageHeight) / currentWidth;
  const centerX = editor.x + editor.width / 2;
  const centerY = editor.y + editor.height / 2;

  editor.width = SIGNATURE_WIDTH / pageWidth;
  editor.height = (SIGNATURE_WIDTH * aspect) / pageHeight;
  editor.x = centerX - editor.width / 2;
  editor.y = centerY - editor.height / 2;
  editor.setDims();
  editor.fixAndSetPosition();
}

function runFind(type: "" | "again", findPrevious = false) {
  if (!eventBus) return;
  findNotFound.value = false;
  if (!findQuery.value) findCount.value = { current: 0, total: 0 };
  eventBus.dispatch("find", { source: null, type, query: findQuery.value, caseSensitive: false, entireWord: false, highlightAll: true, findPrevious, matchDiacritics: false });
}

function findAgain(previous: boolean) {
  if (findQuery.value) runFind("again", previous);
}

watch(findQuery, () => runFind(""));

async function openFind() {
  if (!pdfDocument.value) return;
  showFind.value = true;
  await nextTick();
  findInputRef.value?.focus();
  findInputRef.value?.select();
}

function closeFind() {
  showFind.value = false;
  eventBus?.dispatch("findbarclose", { source: null });
  findCount.value = { current: 0, total: 0 };
  findNotFound.value = false;
}

function toggleFind() {
  if (showFind.value) closeFind();
  else openFind();
}

async function documentBytes(): Promise<Uint8Array<ArrayBuffer>> {
  uiManager?.endCurrentEditing?.();
  return pdfDocument.value!.saveDocument();
}

async function save(): Promise<boolean> {
  if (!pdfDocument.value || saving.value) return false;

  saving.value = true;

  try {
    const blob = new Blob([await documentBytes()], { type: PDF_MIME });
    let saved = target.value;

    if (saved?.source) {
      await saveToSource(saved, blob, PDF_MIME);
    } else {
      saved = await saveNewToStorage(fileName.value.replace(/\.pdf$/i, ""), "pdf", blob, PDF_MIME);
      target.value = saved;
      fileName.value = saved.name;
    }

    pdfDocument.value?.annotationStorage.resetModified();
    isModified.value = false;
    saveState.value = "saved";
    notifySuccess(t("File saved"), savedDescription(saved), themeClasses.value.scopeSelector);
    setTimeout(() => (saveState.value = "idle"), SAVED_FEEDBACK_MS);
    return true;
  } catch (err: any) {
    notifyError(t(err.response?.data?.error || err.message || "Failed to save file"));
    return false;
  } finally {
    saving.value = false;
  }
}

async function downloadCopy() {
  if (!pdfDocument.value) return;

  try {
    triggerDownload(new Blob([await documentBytes()], { type: PDF_MIME }), fileName.value || "document.pdf");
  } catch {
    notifyError(t("Failed to save file"));
  }
}

function openPageMenu(page: number, event: MouseEvent) {
  pageMenu.page = page;
  pageMenu.x = event.clientX;
  pageMenu.y = event.clientY;
  pageMenu.visible = true;
}

async function extractFromCurrent(pageInfos: Parameters<PDFDocumentProxy["extractPages"]>[0]): Promise<Uint8Array> {
  const task = pdfjsLib.getDocument({ data: await documentBytes(), enableXfa: false, verbosity: 0 });

  try {
    return await (await task.promise).extractPages(pageInfos);
  } finally {
    task.destroy();
  }
}

async function reorganize(pageInfos: Parameters<PDFDocumentProxy["extractPages"]>[0], page: number) {
  if (!pdfDocument.value) return;

  try {
    const bytes = await extractFromCurrent(pageInfos);
    isModified.value = true;
    await openDocument(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer, fileName.value, target.value, { keepModified: true, page });
  } catch (err) {
    console.error("Failed to reorganize PDF:", err);
    notifyError(t("Failed to update pages"));
  }
}

function movePage(page: number, offset: number) {
  const from = page - 1;
  const to = from + offset;
  if (to < 0 || to >= totalPages.value) return;

  const order = Array.from({ length: totalPages.value }, (_, index) => index);
  order.splice(to, 0, order.splice(from, 1)[0]);

  const positions = new Array<number>(order.length);
  order.forEach((source, position) => (positions[source] = position));

  reorganize([{ document: null, pageIndices: positions }], to + 1);
}

function deletePage(page: number) {
  if (totalPages.value <= 1) return;
  reorganize([{ document: null, excludePages: [page - 1] }], Math.min(page, totalPages.value - 1));
}

function requestExtractPage(page: number) {
  if (target.value?.source !== "dropzone") {
    extractPage(page);
    return;
  }

  pendingExtractPage.value = page;
  showExtractWarning.value = true;
}

function confirmExtractPage() {
  showExtractWarning.value = false;
  if (pendingExtractPage.value) extractPage(pendingExtractPage.value);
  pendingExtractPage.value = 0;
}

async function extractPage(page: number) {
  if (!pdfDocument.value) return;

  try {
    const bytes = await extractFromCurrent([{ document: null, includePages: [page - 1] }]);
    const baseName = fileName.value.replace(/\.pdf$/i, "") || t("Document");
    const saved = await saveNewToStorage(`${baseName} - ${t("Page {n}", { n: page })}`, "pdf", new Blob([bytes as Uint8Array<ArrayBuffer>], { type: PDF_MIME }), PDF_MIME);
    notifySuccess(t("Page extracted"), savedDescription(saved), themeClasses.value.scopeSelector);
  } catch (err: any) {
    notifyError(t(err.response?.data?.error || err.message || "Failed to save file"));
  }
}

function isPdfFile(file: File): boolean {
  return file.type === PDF_MIME || file.name.toLowerCase().endsWith(".pdf");
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

  const file = Array.from(event.dataTransfer?.files ?? []).find(isPdfFile);
  if (!file) return;

  handleIncomingPdf({ name: file.name, buffer: await file.arrayBuffer() });
}

function browseDocuments() {
  windowStore.openFileInApp("fileexplorer", {
    data: { initialLocation: "storage", initialPath: DOCUMENTS_FOLDER },
  });
}

function isEditableTarget(element: EventTarget | null) {
  if (!(element instanceof HTMLElement)) return false;
  return element.isContentEditable || element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement;
}

function handleKeydown(event: KeyboardEvent) {
  if (props._windowId && windowStore.activeWindowId !== props._windowId) return;
  if (showUnsavedDialog.value || showSignatureDialog.value || showPasswordDialog.value) return;

  const modifier = event.ctrlKey || event.metaKey;
  const key = event.key.toLowerCase();

  if (modifier && key === "s") {
    event.preventDefault();
    save();
    return;
  }

  if (modifier && key === "f") {
    event.preventDefault();
    openFind();
    return;
  }

  if (isEditableTarget(event.target) || hasSelectedEditor.value) return;

  if (event.key === "Escape" && editorMode.value !== AnnotationEditorType.NONE) {
    selectTool(AnnotationEditorType.NONE);
  } else if (modifier) {
    return;
  } else if (event.key === "+" || event.key === "=") {
    event.preventDefault();
    zoomIn();
  } else if (event.key === "-") {
    event.preventDefault();
    zoomOut();
  } else if (event.key === "ArrowLeft") {
    event.preventDefault();
    previousPage();
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    nextPage();
  } else if (event.key === "Home") {
    event.preventDefault();
    goToPage(1);
  } else if (event.key === "End") {
    event.preventDefault();
    goToPage(totalPages.value);
  }
}

function closeWindow() {
  if (props._windowId) windowStore.closeWindow(props._windowId);
}

function continueAfterUnsaved() {
  const next = pendingFile.value;
  pendingFile.value = null;

  if (next) loadFile(next);
  else closeWindow();
}

async function handleUnsavedSave() {
  showUnsavedDialog.value = false;
  if (await save()) continueAfterUnsaved();
}

function handleUnsavedDiscard() {
  showUnsavedDialog.value = false;
  isModified.value = false;
  continueAfterUnsaved();
}

function handleUnsavedCancel() {
  showUnsavedDialog.value = false;
  pendingFile.value = null;
}

function handleExit() {
  if (isModified.value) showUnsavedDialog.value = true;
  else closeWindow();
}

function handleIncomingPdf(incoming: ExternalBinaryFile) {
  if (isModified.value) {
    pendingFile.value = incoming;
    showUnsavedDialog.value = true;
  } else {
    loadFile(incoming);
  }
}

function handleIncomingFile(event: Event) {
  const incoming = (event as CustomEvent<{ pdfFile?: ExternalBinaryFile }>).detail?.pdfFile;
  if (incoming) handleIncomingPdf(incoming);
}

function handleWindowCloseRequest(event: Event) {
  if (!isModified.value) return;

  event.preventDefault();
  pendingFile.value = null;
  showUnsavedDialog.value = true;
}

onMounted(async () => {
  document.addEventListener("keydown", handleKeydown);

  if (props._windowId) {
    window.addEventListener(`homedock:open-file-${props._windowId}`, handleIncomingFile);
    window.addEventListener(`homedock:request-close-${props._windowId}`, handleWindowCloseRequest);
  }

  await initViewer();
  if (props.pdfFile) loadFile(props.pdfFile);
});

onUnmounted(() => {
  document.removeEventListener("keydown", handleKeydown);
  resizeObserver?.disconnect();

  if (props._windowId) {
    window.removeEventListener(`homedock:open-file-${props._windowId}`, handleIncomingFile);
    window.removeEventListener(`homedock:request-close-${props._windowId}`, handleWindowCloseRequest);
  }

  loadToken++;
  pdfViewer?.setDocument(null as unknown as PDFDocumentProxy);
  pdfDocument.value?.loadingTask.destroy();
  pdfDocument.value = null;
  uiManager = null;
});
</script>

<style scoped>
.pdf-viewer {
  user-select: none;
}

.pdf-container {
  touch-action: pan-x pan-y;
  outline: none;
}

.pdf-container :deep(.pdfViewer) {
  padding: 16px 0;
}

.pdf-container :deep(.pdfViewer .page) {
  margin: 0 auto 16px;
  border: 0;
  box-shadow:
    0 1px 3px rgb(0 0 0 / 0.12),
    0 8px 24px rgb(0 0 0 / 0.12);
}

.pdf-container :deep(.editToolbar) {
  display: none !important;
}

.pdf-container :deep(.textLayer) {
  -webkit-user-select: text;
  user-select: text;
}

.annotate-swatch {
  box-shadow: 0 0 0 1px rgb(128 128 128 / 0.55);
  transition: box-shadow 0.15s ease;
}

.annotate-swatch.active {
  box-shadow:
    0 0 0 2px rgb(255 255 255 / 0.9),
    0 0 0 3.5px #3b82f6;
}

.annotate-size {
  accent-color: #3b82f6;
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

@container window (max-width: 600px) {
  .toolbar-optional {
    display: none;
  }
}

@container window (max-width: 440px) {
  .toolbar-zoom {
    display: none;
  }
}

@container window (max-width: 520px) {
  .drop-save-button {
    width: 1.75rem;
    padding: 0;
  }

  .drop-save-label {
    display: none;
  }
}
</style>
