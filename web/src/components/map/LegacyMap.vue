<script setup lang="ts">
import { Map, Popup, AttributionControl, addProtocol } from "maplibre-gl";
import { Protocol } from "pmtiles";
import { onMounted, ref, watch } from "vue";
import "maplibre-gl/dist/maplibre-gl.css";

import MapTooltip from "./MapTooltip.vue";
import { oauthClient } from "@/api/auth";
import { THEMES } from "@/themes";

import { useAppStore, useMapStore, useLayerStore } from "@/store";
const appStore = useAppStore();
const mapStore = useMapStore();
const layerStore = useLayerStore();

const ATTRIBUTION = [
  "<a target='_blank' href='https://maplibre.org/'>© MapLibre</a>",
  "<span> | </span>",
  "<a target='_blank' href='https://www.openstreetmap.org/copyright'>© OpenStreetMap</a>",
];

addProtocol("pmtiles", new Protocol().tile);

// MapLibre refs
const tooltip = ref<HTMLElement>();
const attributionControl = new AttributionControl({
  compact: true,
  customAttribution: ATTRIBUTION,
});
attributionControl.onAdd = (map: Map): HTMLElement => {
  attributionControl._map = map;
  const container = document.createElement("div");
  container.innerHTML = ATTRIBUTION.join("");
  attributionControl._container = container;
  setAttributionControlStyle();
  return container;
};

function setAttributionControlStyle() {
  const container = attributionControl._container;
  container.style.padding = "3px 8px";
  container.style.marginRight = "5px";
  container.style.borderRadius = "15px";
  container.style.position = "relative";
  container.style.right = appStore.openSidebars.includes("right")
    ? "360px"
    : "0px";
  container.style.background = appStore.theme === "light" ? "white" : "black";
  container.childNodes.forEach((child) => {
    const childElement = child as HTMLElement;
    childElement.style.color = appStore.theme === "light" ? "black" : "white";
  });
}

function createMap() {
  const newMap = new Map({
    container: "mapContainer",
    attributionControl: false,
    preserveDrawingBuffer: true, // allows screenshots
    // transformRequest adds auth headers to tile requests
    transformRequest: (url) => {
      let headers = {}
      if (url.includes(import.meta.env.VITE_APP_API_ROOT)) {
        headers = oauthClient?.authHeaders
      }
      return { url, headers };
    },
    style: mapStore.currentBasemap?.style,
    center: [0, 0],
    zoom: 1, // Initial zoom level
  });

  newMap.addControl(attributionControl);

  // Add spinner while loading
  const mapContainer = document.getElementById("mapContainer")!;
  mapContainer.classList.add("spinner");
  newMap.on("load", () => {
    mapContainer.classList.remove("spinner");
  });
  newMap.on('error', (response) => {
    // AbortErrors are raised when updating style of raster layers; ignore these
    if (response.error.message !== 'AbortError') console.error(response.error)
  });

  /**
   * This is called on every click, and technically hides the tooltip on every click.
   * However, if a feature layer is clicked, that event is fired after this one, and the
   * tooltip is re-enabled and rendered with the desired contents. The net result is that
   * this only has a real effect when the base map is clicked, as that means that no other
   * feature layer can "catch" the event, and the tooltip stays hidden.
   */
  newMap.on("click", () => { mapStore.clickedFeature = undefined });

  // Order is important as the following function relies on the ref being set
  mapStore.map = newMap;
  createMapControls();
}

function createMapControls() {
  if (!mapStore.map || !tooltip.value) {
    throw new Error("Map or refs not initialized!");
  }

  // Add tooltip overlay
  const popup = new Popup({
    anchor: "bottom-left",
    closeOnClick: false,
    maxWidth: "none",
    closeButton: true,
  });

  // Link overlay ref to dom, allowing for modification elsewhere
  popup.setDOMContent(tooltip.value);

  // Set store value
  mapStore.tooltipOverlay = popup;
}

onMounted(() => {
  mapStore.fetchAvailableBasemaps().then(() => {
    createMap();
    mapStore.resetMapPosition(undefined, true);
  })
});

watch(() => mapStore.currentBasemap, () => {
  if (mapStore.map && mapStore.currentBasemap) {
    const visible = mapStore.currentBasemap.id !== undefined
    mapStore.setBasemapVisibility(visible);
    if (visible) {
      const map = mapStore.getMap();
      if (mapStore.currentBasemap.style) {
        map.setStyle(mapStore.currentBasemap.style);
      }
      map.once('idle', () => {
        layerStore.updateLayersShown();
      });
    }
  }
})

watch(() => appStore.theme, () => {
  mapStore.setBasemapToDefault();
  setAttributionControlStyle();
});

watch(() => appStore.openSidebars, () => {
  setAttributionControlStyle();
});
</script>

<template>
  <div id="mapContainer" class="map">
    <div id="map-tooltip" ref="tooltip" class="tooltip">
      <MapTooltip />
    </div>
  </div>
</template>

<style scoped>
.map {
  height: 100%;
  width: 100%;
  position: relative;
}

@keyframes spinner {
  to {
    transform: rotate(360deg);
  }
}

.spinner:after {
  content: "";
  box-sizing: border-box;
  position: absolute;
  top: 50%;
  left: 50%;
  width: 40px;
  height: 40px;
  margin-top: -20px;
  margin-left: -20px;
  border-radius: 50%;
  border: 5px solid rgba(180, 180, 180, 0.6);
  border-top-color: rgba(0, 0, 0, 0.6);
  animation: spinner 0.6s linear infinite;
}

.tooltip {
  border-radius: 5px;
  padding: 0;
  word-break: break-word;
  text-wrap: wrap;
  width: fit-content;
  min-width: 50px;
  max-width: 350px;
}

.base-layer-control {
  float: right;
  position: absolute;
  top: 2%;
  right: 2%;
  z-index: 2;
}
</style>
