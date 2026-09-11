<script setup lang="ts">
import { debounce } from "lodash";
import { ref, watch, computed } from "vue";
import html2canvas from "html2canvas-pro";
import { Map, type LngLatBoundsLike } from "maplibre-gl";

import JsonEditorVue from "json-editor-vue";
import "vanilla-jsoneditor/themes/jse-theme-dark.css";
import { Mode } from "vanilla-jsoneditor";
import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";

import {
  useAppStore,
  useLayerStore,
  useMapStore,
  useProjectStore,
  useTutorialStore,
  usePanelStore,
} from "@/store";
import { useMapCompareStore } from "@/store/compare";
import {
  createBasemap,
  createBookmark,
  deleteBookmark,
  uploadFile,
} from "@/api/rest";
import { storeToRefs } from "pinia";
import type { Bookmark } from "@/types";

const appStore = useAppStore();
const layerStore = useLayerStore();
const mapStore = useMapStore();
const projectStore = useProjectStore();
const tutorialStore = useTutorialStore();
const panelStore = usePanelStore();
const { isComparing } = storeToRefs(useMapCompareStore());

const copyMenuShown = ref(false);
const screenOverlayShown = ref(false);
const mapOnly = ref(false);
const loadingBounds = ref(false);
const basemapList = ref();
const basemapPreviews = ref<Record<number, Map>>({});
const showBasemapCreation = ref(false);
const newBasemapTab = ref<"url" | "json">("url");
const newBasemapName = ref();
const newBasemapTileURL = ref();
const newBasemapStyleJSON = ref();
const jsonErrors = ref();
const newBasemapPreview = ref<Map | undefined>();
const newBasemapValid = computed(
  () =>
    newBasemapName.value?.length &&
    newBasemapStyleJSON.value &&
    !jsonErrors.value.length,
);

const showBookmarkCreation = ref(false);
const bookmarkToDelete = ref();
const newBookmarkName = ref("");
const newBookmarkThumbnail = ref();
const newBookmarkThumbnailURL = computed(() => {
  if (!newBookmarkThumbnail.value) return null;
  return URL.createObjectURL(newBookmarkThumbnail.value);
});
const newBookmarkValid = computed(() => {
  return (
    newBookmarkName.value.length &&
    !projectStore.availableBookmarks
      .map((v) => v.name)
      .includes(newBookmarkName.value)
  );
});
const editMode = computed(() => {
  if (projectStore.currentProject) {
    return ["owner", "collaborator"].includes(
      projectStore.permissions[projectStore.currentProject.id],
    );
  }
  return false;
});

function createBasemapPreviews() {
  if (basemapList.value) {
    const map = mapStore.getMap();
    const bounds = map.getBounds().toArray() as LngLatBoundsLike;
    mapStore.availableBasemaps.forEach((basemap) => {
      if (basemap.id === undefined || basemap.style === undefined) return;
      if (basemapPreviews.value[basemap.id]) {
        basemapPreviews.value[basemap.id].remove();
      }
      const preview = new Map({
        container: "basemap-preview-" + basemap.id,
        attributionControl: false,
        bounds,
      });

      preview.setStyle(basemap.style);
      basemapPreviews.value[basemap.id] = preview;
    });
  }
}

function cancelBasemapCreate() {
  showBasemapCreation.value = false;
  newBasemapTab.value = "url";
  newBasemapName.value = undefined;
  newBasemapTileURL.value = undefined;
  newBasemapStyleJSON.value = undefined;
  jsonErrors.value = [];
  newBasemapPreview.value = undefined;
}

function switchBasemapCreateTab() {
  newBasemapTileURL.value = undefined;
  newBasemapStyleJSON.value = undefined;
  jsonErrors.value = [];
  createNewBasemapPreview();
}

function setNewBasemapStyleFromTileURL() {
  if (newBasemapTileURL.value) {
    newBasemapStyleJSON.value = {
      version: 8,
      sources: {
        "base-source": {
          type: "raster",
          tiles: [newBasemapTileURL.value],
          tileSize: 256,
        },
      },
      layers: [
        {
          id: "base-layer",
          type: "raster",
          source: "base-source",
        },
      ],
    };
  } else {
    newBasemapStyleJSON.value = undefined;
  }
}

async function createNewBasemapPreview() {
  const map = mapStore.getMap();
  const center = map.getCenter();
  const zoom = map.getZoom();
  if (!newBasemapPreview.value) {
    newBasemapPreview.value = new Map({
      container: "basemap-preview-new",
      attributionControl: false,
    });
  }
  newBasemapPreview.value.setCenter(center);
  newBasemapPreview.value.setZoom(zoom);
  if (newBasemapStyleJSON.value) {
    if (typeof newBasemapStyleJSON.value == "string") {
      try {
        const response = await fetch(newBasemapStyleJSON.value);
        const content = await response.json();
        jsonErrors.value = validateStyleMin(content);
      } catch {
        jsonErrors.value = [{ message: "Invalid URL." }];
      }
    } else {
      jsonErrors.value = validateStyleMin(newBasemapStyleJSON.value);
    }
    if (!jsonErrors.value?.length) {
      newBasemapPreview.value.setStyle(newBasemapStyleJSON.value);
      return;
    }
  }
  newBasemapPreview.value.setStyle({
    version: 8,
    sources: {},
    layers: [],
  });
}

function submitBasemapCreate() {
  if (newBasemapValid.value && appStore.authenticated) {
    createBasemap({
      name: newBasemapName.value,
      style: newBasemapStyleJSON.value,
    }).then((basemap) => {
      cancelBasemapCreate();
      mapStore.fetchAvailableBasemaps();
      mapStore.currentBasemap = basemap;
    });
  }
}

async function fitMap() {
  loadingBounds.value = true;
  const map = mapStore.getMap();
  const bounds = await layerStore.getBoundsOfVisibleLayers();
  if (bounds) map.fitBounds(bounds);
  loadingBounds.value = false;
}

async function takeScreenshot(showSidebars: boolean) {
  copyMenuShown.value = false;
  const screenshotTarget = document.getElementById("app");
  if (screenshotTarget) {
    const canvas = await html2canvas(screenshotTarget, {
      ignoreElements: (element: Element) => {
        return (
          element.id === "controls-bar" ||
          element.classList.contains("control-menu") ||
          (!showSidebars && element.classList.contains("v-navigation-drawer"))
        );
      },
    });
    const blob: Blob | null = await new Promise((resolve) =>
      canvas.toBlob(resolve),
    );
    return blob;
  }
}

async function copyScreenshot() {
  const blob = await takeScreenshot(!mapOnly.value);
  if (blob) {
    const clipboardItem = new ClipboardItem({ "image/png": blob });
    navigator.clipboard.write([clipboardItem]);
    animateCameraFlash();
  }
}

async function saveScreenshot() {
  const blob = await takeScreenshot(!mapOnly.value);
  if (blob) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "geodatalytics_screenshot.png";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    animateCameraFlash();
  }
}

function animateCameraFlash() {
  // animate camera flash with overlay
  setTimeout(() => {
    screenOverlayShown.value = true;
    setTimeout(() => {
      screenOverlayShown.value = false;
    }, 200);
  }, 200);
}

function showBookmarkDialog() {
  takeScreenshot(true).then((blob) => {
    newBookmarkThumbnail.value = blob;
  });
  showBookmarkCreation.value = true;
}

function cancelCreateBookmark() {
  newBookmarkName.value = "";
  newBookmarkThumbnail.value = undefined;
  showBookmarkCreation.value = false;
}

function submitNewBookmark() {
  if (!appStore.authenticated) return;
  if (newBookmarkValid.value && newBookmarkThumbnail.value) {
    const thumbnailFile = new File(
      [newBookmarkThumbnail.value],
      "thumbnail.png",
      { type: "image/png" },
    );
    uploadFile(thumbnailFile).then((thumbnailURL) => {
      const bookmark = projectStore.getCurrentBookmark();
      if (bookmark) {
        bookmark.name = newBookmarkName.value;
        bookmark.thumbnail = thumbnailURL;
        createBookmark(bookmark).then((createdBookmark) => {
          cancelCreateBookmark();
          projectStore.fetchProjectBookmarks();
          projectStore.navigateToBookmark(createdBookmark);
        });
      }
    });
  }
}

function submitDeleteBookmark() {
  deleteBookmark(bookmarkToDelete.value).then(() => {
    bookmarkToDelete.value = undefined;
    projectStore.fetchProjectBookmarks();
    projectStore.navigateNoBookmark();
  });
}

function copyBookmarkLink(bookmark: Bookmark) {
  const url = `${window.location.origin}/bookmark/${bookmark.id}`;
  navigator.clipboard.writeText(url);
}

function showTutorial() {
  panelStore.resetPanels();
  tutorialStore.showTutorialStep = 1;
  tutorialStore.showWelcomeMessage = false;
}

function togglePanelVisibility(id: string) {
  panelStore.panelArrangement = panelStore.panelArrangement.map((p) => {
    if (p.id == id) p.visible = !p.visible;
    return p;
  });
}

watch(basemapList, createBasemapPreviews);
watch(newBasemapTab, switchBasemapCreateTab);
watch(newBasemapTileURL, debounce(setNewBasemapStyleFromTileURL, 1000));
watch(newBasemapStyleJSON, debounce(createNewBasemapPreview, 1000));
</script>

<template>
  <div
    id="controls-bar"
    :class="
      appStore.openSidebars.includes('left')
        ? 'controls-bar shifted'
        : 'controls-bar'
    "
  >
    <v-btn
      v-if="projectStore.currentProject"
      class="control-btn"
      variant="flat"
    >
      <v-icon
        :icon="
          projectStore.currentBookmark ? 'mdi-bookmark' : 'mdi-bookmark-outline'
        "
      ></v-icon>
      <v-menu
        activator="parent"
        open-on-hover
        open-delay="100"
        :close-on-content-click="false"
        width="450"
      >
        <v-card class="control-menu">
          <div class="control-menu-title">Project Bookmarks</div>
          <v-card-text class="pa-3">
            <div v-if="isComparing">
              While using map comparison mode, saving a new bookmark is not
              supported.
            </div>
            <v-btn
              v-else-if="editMode"
              class="control-menu-row"
              @click="showBookmarkDialog"
            >
              <div>Save current view as bookmark</div>
            </v-btn>
            <v-list
              v-if="projectStore.availableBookmarks.length"
              density="compact"
              bg-color="transparent"
            >
              <v-list-item
                v-for="bookmark in projectStore.availableBookmarks"
                :key="bookmark.id"
                class="control-menu-row pa-1"
                @click="projectStore.navigateToBookmark(bookmark)"
              >
                <template #prepend>
                  <img :src="bookmark.thumbnail" height="70px" />
                </template>
                <template #title>
                  <div style="width: 150px; text-wrap: wrap">
                    {{ bookmark.name }}
                  </div>
                </template>
                <template #append>
                  <v-btn
                    v-if="editMode"
                    v-tooltip="'Delete this bookmark'"
                    icon="mdi-delete"
                    flat
                    variant="text"
                    color="secondary-text"
                    @click.stop.prevent="bookmarkToDelete = bookmark"
                  ></v-btn>
                  <v-btn
                    v-tooltip="'Copy shareable link'"
                    icon="mdi-share"
                    flat
                    variant="text"
                    color="secondary-text"
                    @click.stop.prevent="copyBookmarkLink(bookmark)"
                  ></v-btn>
                </template>
              </v-list-item>
            </v-list>
            <div v-else>No saved bookmarks exist for this project.</div>
          </v-card-text>
        </v-card>
      </v-menu>
    </v-btn>
    <v-btn class="control-btn" variant="flat">
      <v-icon>mdi-map-outline</v-icon>
      <v-menu
        activator="parent"
        open-on-hover
        open-delay="100"
        :close-on-content-click="false"
      >
        <v-card
          class="control-menu"
          style="max-height: 400px; overflow-y: auto"
        >
          <div class="control-menu-title">Base Map Options</div>
          <v-list
            ref="basemapList"
            :selected="[mapStore.currentBasemap]"
            class="basemap-list"
            density="compact"
            mandatory
            @update:selected="
              (selected) => (mapStore.currentBasemap = selected[0])
            "
          >
            <v-list-item
              v-if="appStore.authenticated"
              key="new"
              title="Create Custom Basemap"
              class="px-2"
              style="color: rgb(var(--v-theme-primary))"
              @click="showBasemapCreation = true"
            >
              <template #prepend>
                <v-icon icon="mdi-plus" class="pa-0" color="primary"></v-icon>
              </template>
            </v-list-item>
            <v-list-item
              v-for="basemap in mapStore.availableBasemaps"
              :key="basemap.id"
              :value="basemap"
              class="px-2"
            >
              {{ basemap.name }}
              <template #prepend>
                <v-icon
                  :icon="
                    basemap.id === mapStore.currentBasemap?.id
                      ? 'mdi-check'
                      : 'none'
                  "
                  color="success"
                  class="pa-0"
                ></v-icon>
                <div
                  v-if="basemap.id !== undefined"
                  :id="'basemap-preview-' + basemap.id"
                  class="basemap-preview"
                />
                <div v-else style="width: 90px" />
              </template>
            </v-list-item>
          </v-list>
        </v-card>
      </v-menu>
    </v-btn>
    <v-btn class="control-btn" variant="flat">
      <v-icon icon="mdi-window-restore"></v-icon>
      <v-menu
        activator="parent"
        open-on-hover
        open-delay="100"
        :close-on-content-click="false"
      >
        <v-card class="control-menu">
          <div class="control-menu-title">Panel Visibility</div>
          <v-card-text class="pa-3">
            <div
              v-for="item in panelStore.panelArrangement.filter(
                (p) => p.closeable,
              )"
              :key="item.id"
              class="control-menyu-row"
              @click="togglePanelVisibility(item.id)"
            >
              <v-checkbox-btn
                :model-value="item.visible"
                :label="item.label"
              ></v-checkbox-btn>
            </div>
          </v-card-text>
        </v-card>
      </v-menu>
    </v-btn>
    <v-btn v-if="!isComparing" class="control-btn" variant="flat">
      <v-icon icon="mdi-camera"></v-icon>
      <v-menu
        v-model="copyMenuShown"
        activator="parent"
        open-on-hover
        open-delay="100"
        :close-on-content-click="false"
      >
        <v-card class="control-menu">
          <div class="control-menu-title">Take Screenshot</div>
          <v-card-text class="pa-3">
            <div class="control-menu-row">
              <v-checkbox
                v-model="mapOnly"
                label="Map Only"
                density="compact"
                hide-details
                color="secondary-text"
              />
            </div>
            <v-btn class="control-menu-row" @click="copyScreenshot">
              Copy image to clipboard
            </v-btn>
            <v-btn class="control-menu-row" @click="saveScreenshot">
              Save image
            </v-btn>
          </v-card-text>
        </v-card>
      </v-menu>
    </v-btn>
    <v-btn class="control-btn" variant="flat" @click="fitMap">
      <v-progress-circular v-if="loadingBounds" indeterminate />
      <v-icon
        v-else
        v-tooltip:bottom="'Fit Map to Visible Layers'"
        icon="mdi-fit-to-page-outline"
      ></v-icon>
    </v-btn>
    <v-btn class="control-btn" variant="flat">
      <v-icon
        v-tooltip:bottom="'Toggle Light/Dark Mode'"
        icon="mdi-theme-light-dark"
        @click="appStore.theme = appStore.theme === 'dark' ? 'light' : 'dark'"
      >
      </v-icon>
    </v-btn>
    <v-btn class="control-btn" variant="flat">
      <v-icon icon="mdi-help-circle-outline"></v-icon>
      <v-menu
        activator="parent"
        open-on-hover
        open-delay="0"
        :close-on-content-click="false"
      >
        <v-card class="control-menu">
          <div class="control-menu-title">Help</div>
          <v-card-text class="pa-3">
            <v-btn block @click="showTutorial"> Show Tutorial </v-btn>
            <table class="map-controls-table">
              <thead>
                <tr>
                  <td>Map Controls</td>
                  <td>
                    <v-icon icon="mdi-keyboard" color="secondary-text"></v-icon>
                  </td>
                  <td>
                    <v-icon icon="mdi-mouse" color="secondary-text"></v-icon>
                  </td>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Zoom</td>
                  <td>+/-</td>
                  <td>scroll</td>
                </tr>
                <tr>
                  <td>Pan</td>
                  <td>arrows</td>
                  <td>drag</td>
                </tr>
              </tbody>
            </table>
          </v-card-text>
        </v-card>
      </v-menu>
    </v-btn>
    <v-overlay
      :model-value="screenOverlayShown"
      absolute
      persistent
      :opacity="0.8"
      scrim="white"
    >
    </v-overlay>
    <v-dialog :model-value="showBasemapCreation" width="500">
      <v-card>
        <v-card-title class="pa-3">
          New Basemap
          <v-btn
            class="close-button transparent"
            variant="flat"
            icon
            @click="cancelBasemapCreate"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text
          class="d-flex"
          style="flex-direction: column; row-gap: 5px"
        >
          <v-text-field
            v-model="newBasemapName"
            label="Name"
            hide-details
            density="compact"
            autofocus
          />
          <v-tabs v-model="newBasemapTab" color="primary">
            <v-tab value="url">Tile URL</v-tab>
            <v-tab value="json">MapLibre Style JSON</v-tab>
          </v-tabs>
          <v-window v-model="newBasemapTab">
            <v-window-item value="url">
              <div>Supply a tile URL</div>
              <div>(e.g. https://a.tile.openstreetmap.org/{z}/{x}/{y}.png)</div>
              <v-expansion-panels>
                <v-expansion-panel elevation="0">
                  <v-expansion-panel-title class="pa-0">
                    Advanced: Authenticated Tile URL
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <div>
                      If your basemap requires authentication, you may append a
                      public api key to the tile URL. Ensure that the public key
                      is enabled for the following domain:
                      "geodatalytics.kitware.com".
                    </div>
                    <div>
                      (e.g.
                      https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png?key=my_public_key)
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
              <v-text-field
                v-model="newBasemapTileURL"
                label="Tile URL"
                hide-details
                density="compact"
              />
            </v-window-item>
            <v-window-item value="json">
              <div>
                Supply a JSON that adheres to the
                <a href="https://maplibre.org/maplibre-style-spec/"
                  >Maplibre Style Spec</a
                >.
              </div>
              <div>
                Style spec can be supplied directly as JSON or as a URL string
                that references a publicly accessible JSON file (e.g.
                "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json").
              </div>
              <json-editor-vue
                v-model="newBasemapStyleJSON"
                :mode="Mode.text"
                :stringified="false"
                :main-menu-bar="false"
                :ask-to-format="false"
                :indentation="4"
                :class="appStore.theme === 'dark' ? 'jse-theme-dark' : ''"
              />
            </v-window-item>
          </v-window>
          <v-spacer />
          <div v-for="(err, index) in jsonErrors" :key="index">
            Error: {{ err.message }}
          </div>
          <div v-if="!jsonErrors?.length">Map Preview:</div>
          <div
            id="basemap-preview-new"
            :style="jsonErrors?.length ? 'display: none' : ''"
          ></div>
        </v-card-text>
        <v-card-actions style="text-align: right">
          <v-btn variant="tonal" @click="cancelBasemapCreate"> Cancel </v-btn>
          <v-btn
            color="primary"
            :disabled="!newBasemapValid"
            @click="submitBasemapCreate"
          >
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <v-dialog v-if="editMode" :model-value="showBookmarkCreation" width="500">
      <v-card>
        <v-card-title class="pa-3">
          New Bookmark
          <v-btn
            class="close-button transparent"
            variant="flat"
            icon
            @click="cancelCreateBookmark"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text>
          <span v-if="newBookmarkName.length && !newBookmarkValid">
            Name must not match an existing view in this project.
          </span>
          <v-text-field
            v-model="newBookmarkName"
            label="Name"
            autofocus
            hide-details
            class="mb-4"
            @keydown.enter="submitNewBookmark"
          ></v-text-field>
          <div v-if="newBookmarkThumbnailURL">
            This thumbnail will be saved as a visual reference, but loading the
            bookmark later may result in slight differences (e.g. newly created
            objects appearing in lists)
          </div>
          <v-img
            v-if="newBookmarkThumbnailURL"
            :src="newBookmarkThumbnailURL"
          ></v-img>
          <div v-else>Loading thumbnail...</div>
        </v-card-text>
        <v-card-actions style="text-align: right">
          <v-btn variant="tonal" @click="cancelCreateBookmark"> Cancel </v-btn>
          <v-btn
            color="primary"
            :disabled="!newBookmarkValid || !newBookmarkThumbnail"
            @click="submitNewBookmark"
          >
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <v-dialog
      v-if="editMode"
      :model-value="bookmarkToDelete !== undefined"
      width="500"
    >
      <v-card>
        <v-card-title>
          Delete Bookmark
          <v-btn
            class="close-button transparent"
            variant="flat"
            icon
            @click="bookmarkToDelete = undefined"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text v-if="bookmarkToDelete">
          Are you sure you want to delete bookmark "{{
            bookmarkToDelete.name
          }}"?
        </v-card-text>
        <v-card-actions style="text-align: right">
          <v-btn variant="tonal" @click="bookmarkToDelete = undefined">
            Cancel
          </v-btn>
          <v-btn color="error" variant="tonal" @click="submitDeleteBookmark()">
            <v-icon color="error" class="mr-1">mdi-delete</v-icon>
            Delete
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style>
.controls-bar {
  padding: 6px 8px;
  position: absolute;
  top: 10px;
  left: 250px;
  background-color: rgb(var(--v-theme-surface-bright));
  display: flex;
  border-radius: 8px;
  z-index: 3;
}

.controls-bar.shifted {
  left: 375px;
}

.controls-bar i {
  font-size: 24px;
}

.control-btn {
  min-width: 0 !important;
  width: 40px;
  background-color: rgb(var(--v-theme-surface-bright));
  color: rgb(var(--v-theme-secondary-text));
}

.control-menu {
  min-width: 200px;
  border-radius: 10px;
  background-color: rgb(var(--v-theme-surface)) !important;
}

.control-menu .v-btn:not(.v-btn--flat) {
  background-color: rgb(var(--v-theme-surface-bright));
}

.control-menu-title {
  width: 100%;
  padding: 3px 8px;
  background-color: rgb(var(--v-theme-surface-bright));
}

.control-menu-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
}

.map-controls-table {
  margin-top: 8px;
  border-collapse: collapse;
}

.map-controls-table thead {
  border-bottom: 1px solid rgb(var(--v-theme-on-surface));
}

.map-controls-table td {
  padding: 4px 8px;
  text-align: center;
}

.basemap-list .v-list-item {
  height: 60px;
}

.basemap-list .v-list-item__prepend > .v-icon ~ .v-list-item__spacer {
  width: 5px;
}

.basemap-preview {
  margin: 0px 10px;
  height: 50px;
  width: 70px;
}

#basemap-preview-new {
  width: 100%;
  height: 150px;
  border: 1px solid rgb(var(--v-theme-on-surface-variant));
}
</style>
