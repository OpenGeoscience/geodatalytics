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
} from "@/store";
import { useMapCompareStore } from "@/store/compare";
import {
  createBasemap,
  createViewState,
  deleteViewState,
  uploadFile,
} from "@/api/rest";
import { storeToRefs } from "pinia";
import type { ViewState } from "@/types";

const appStore = useAppStore();
const layerStore = useLayerStore();
const mapStore = useMapStore();
const projectStore = useProjectStore();
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

const showViewStateCreation = ref(false);
const viewStateToDelete = ref();
const newViewStateName = ref("");
const newViewStateThumbnail = ref();
const newViewStateThumbnailURL = computed(() => {
  if (!newViewStateThumbnail.value) return null;
  return URL.createObjectURL(newViewStateThumbnail.value);
});
const newViewStateValid = computed(() => {
  return (
    newViewStateName.value.length &&
    !projectStore.availableViewStates
      .map((v) => v.name)
      .includes(newViewStateName.value)
  );
});
const userHasEditPermission = computed(() => {
  const user = appStore.currentUser;
  const project = projectStore.currentProject;
  return (
    user?.is_superuser ||
    (project &&
      user &&
      (project.owner.id === user.id ||
        project.collaborators.map((u) => u.id).includes(user.id)))
  );
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
  if (newBasemapValid.value) {
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

async function takeScreenshot() {
  copyMenuShown.value = false;
  const screenshotTarget = document.getElementById("app");
  if (screenshotTarget) {
    const canvas = await html2canvas(screenshotTarget, {
      ignoreElements: (element: Element) => {
        return (
          element.id === "controls-bar" ||
          element.classList.contains("control-menu") ||
          (mapOnly.value && element.classList.contains("v-navigation-drawer"))
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
  const blob = await takeScreenshot();
  if (blob) {
    const clipboardItem = new ClipboardItem({ "image/png": blob });
    navigator.clipboard.write([clipboardItem]);
    animateCameraFlash();
  }
}

async function saveScreenshot() {
  const blob = await takeScreenshot();
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

function showViewStateDialog() {
  takeScreenshot().then((blob) => {
    newViewStateThumbnail.value = blob;
  });
  showViewStateCreation.value = true;
}

function cancelCreateViewState() {
  newViewStateName.value = "";
  newViewStateThumbnail.value = undefined;
  showViewStateCreation.value = false;
}

function submitNewViewState() {
  if (newViewStateValid.value && newViewStateThumbnail.value) {
    const thumbnailFile = new File(
      [newViewStateThumbnail.value],
      "thumbnail.png",
      { type: "image/png" },
    );
    uploadFile(thumbnailFile).then((thumbnailURL) => {
      const viewState = projectStore.getCurrentViewState();
      if (viewState) {
        viewState.name = newViewStateName.value;
        viewState.thumbnail = thumbnailURL;
        createViewState(viewState).then((createdViewState) => {
          cancelCreateViewState();
          projectStore.fetchProjectViewStates();
          projectStore.navigateToViewState(createdViewState);
        });
      }
    });
  }
}

function submitDeleteViewState() {
  deleteViewState(viewStateToDelete.value).then(() => {
    viewStateToDelete.value = undefined;
    projectStore.fetchProjectViewStates();
  });
}

function copyViewStateLink(viewState: ViewState) {
  const url = `${window.location.origin}/view/${viewState.id}`;
  navigator.clipboard.writeText(url);
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
    <v-btn color="primary" class="control-btn" variant="flat">
      <v-icon>mdi-map-outline</v-icon>
      <v-menu activator="parent" :close-on-content-click="false" open-on-hover>
        <v-card style="max-height: 400px; overflow-y: auto">
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
            <v-list-subheader>Base Map Options</v-list-subheader>
            <v-list-item
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
    <v-btn class="control-btn" variant="flat" @click="fitMap">
      <v-progress-circular v-if="loadingBounds" indeterminate />
      <v-icon
        v-else
        v-tooltip="'Fit Map to Visible Layers'"
        icon="mdi-fit-to-page-outline"
      ></v-icon>
    </v-btn>
    <v-btn v-if="!isComparing" class="control-btn" variant="flat">
      <v-icon icon="mdi-camera"></v-icon>
      <v-menu
        v-model="copyMenuShown"
        activator="parent"
        :open-on-hover="true"
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
    <v-btn
      v-if="projectStore.currentProject"
      class="control-btn"
      variant="flat"
    >
      <v-icon icon="mdi-view-array" class="pb-1 pr-2"></v-icon>
      <v-icon
        icon="mdi-share"
        style="position: absolute; left: 15px; top: 8px; max-width: 10px"
      ></v-icon>
      <v-menu
        activator="parent"
        :open-on-hover="true"
        :close-on-content-click="false"
        width="450"
      >
        <v-card class="control-menu">
          <div class="control-menu-title">Saved View States</div>
          <v-card-text class="pa-3">
            <div v-if="isComparing">
              While using map comparison mode, saving a new view state is not
              supported.
            </div>
            <v-btn v-else class="control-menu-row" @click="showViewStateDialog">
              <div>Save current view state</div>
            </v-btn>
            <v-list
              v-if="projectStore.availableViewStates.length"
              density="compact"
              bg-color="transparent"
            >
              <v-list-item
                v-for="viewState in projectStore.availableViewStates"
                :key="viewState.id"
                class="control-menu-row pa-1"
                @click="projectStore.navigateToViewState(viewState)"
              >
                <template #prepend>
                  <img :src="viewState.thumbnail" height="70px" />
                </template>
                <template #title>
                  <div style="width: 150px; text-wrap: wrap">
                    {{ viewState.name }}
                  </div>
                </template>
                <template #append>
                  <v-btn
                    v-if="userHasEditPermission"
                    v-tooltip="'Delete this view state'"
                    icon="mdi-delete"
                    flat
                    variant="text"
                    @click.stop.prevent="viewStateToDelete = viewState"
                  ></v-btn>
                  <v-btn
                    v-tooltip="'Copy shareable link'"
                    icon="mdi-share"
                    flat
                    variant="text"
                    @click.stop.prevent="copyViewStateLink(viewState)"
                  ></v-btn>
                </template>
              </v-list-item>
            </v-list>
            <div v-else>No saved view states exist for this project.</div>
          </v-card-text>
        </v-card>
      </v-menu>
    </v-btn>
    <v-btn class="control-btn" variant="flat">
      <v-icon icon="mdi-information-outline"></v-icon>
      <v-menu
        activator="parent"
        :open-on-hover="true"
        :close-on-content-click="false"
      >
        <v-card class="control-menu">
          <div class="control-menu-title">Input Controls</div>
          <v-card-text class="pa-3">
            <div style="text-align: right; width: 100%">
              <v-icon icon="mdi-keyboard"></v-icon>,
              <v-icon icon="mdi-mouse"></v-icon>
            </div>
            <div class="control-menu-row">
              <div>Zoom</div>
              <div>+/-, scroll</div>
            </div>
            <div class="control-menu-row">
              <div>Pan</div>
              <div>arrows, drag</div>
            </div>
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
    <v-dialog :model-value="showViewStateCreation" width="500">
      <v-card>
        <v-card-title class="pa-3">
          New View State
          <v-btn
            class="close-button transparent"
            variant="flat"
            icon
            @click="cancelCreateViewState"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text>
          <span v-if="newViewStateName.length && !newViewStateValid">
            Name must not match an existing view in this project.
          </span>
          <v-text-field
            v-model="newViewStateName"
            label="Name"
            autofocus
            hide-details
            class="mb-4"
            @keydown.enter="submitNewViewState"
          ></v-text-field>
          <div v-if="newViewStateThumbnailURL">
            This thumbnail will be saved as a visual reference, but loading the
            view state later may result in slight differences (e.g. newly
            created objects appearing in lists)
          </div>
          <v-img
            v-if="newViewStateThumbnailURL"
            :src="newViewStateThumbnailURL"
          ></v-img>
          <div v-else>Loading thumbnail...</div>
        </v-card-text>
        <v-card-actions style="text-align: right">
          <v-btn variant="tonal" @click="cancelCreateViewState"> Cancel </v-btn>
          <v-btn
            color="primary"
            :disabled="!newViewStateValid || !newViewStateThumbnail"
            @click="submitNewViewState"
          >
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <v-dialog :model-value="viewStateToDelete !== undefined" width="500">
      <v-card>
        <v-card-title>
          Delete View State
          <v-btn
            class="close-button transparent"
            variant="flat"
            icon
            @click="viewStateToDelete = undefined"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text v-if="viewStateToDelete">
          Are you sure you want to delete view state "{{
            viewStateToDelete.name
          }}"?
        </v-card-text>
        <v-card-actions style="text-align: right">
          <v-btn variant="tonal" @click="viewStateToDelete = undefined">
            Cancel
          </v-btn>
          <v-btn color="error" variant="tonal" @click="submitDeleteViewState()">
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
  padding: 3px 8px;
  position: absolute;
  top: 10px;
  left: 250px;
  opacity: 80%;
  background-color: rgb(var(--v-theme-surface));
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
}

.control-menu {
  min-width: 200px;
  border-radius: 10px;
  background-color: rgb(var(--v-theme-surface-variant)) !important;
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
