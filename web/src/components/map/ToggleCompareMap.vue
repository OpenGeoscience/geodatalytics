<script setup lang="ts">
import { useAppStore, useLayerStore, useMapStore } from "@/store";
import { useMapCompareStore } from "@/store/compare";
import { computed, ref, watch } from "vue";
import type { Ref } from "vue";
import { ToggleCompare } from "vue-maplibre-compare";
import { oauthClient } from "@/api/auth";
import 'vue-maplibre-compare/dist/vue-maplibre-compare.css'
import { addProtocol, AttributionControl, Popup } from "maplibre-gl";
import type { StyleSpecification, Map, ResourceType } from "maplibre-gl";
import { useTheme } from 'vuetify';
import { Protocol } from "pmtiles";
import { storeToRefs } from "pinia";
import MapTooltip from "./MapTooltip.vue";

const ATTRIBUTION = [
  "<a target='_blank' href='https://maplibre.org/'>© MapLibre</a>",
  "<span> | </span>",
  "<a target='_blank' href='https://www.openstreetmap.org/copyright'>© OpenStreetMap</a>",
];

addProtocol("pmtiles", new Protocol().tile);

const appStore = useAppStore();
const mapStore = useMapStore();
const compareStore = useMapCompareStore();
const layerStore = useLayerStore();
const theme = useTheme();
const {
  isComparing,
  mapStats,
  mapLayersA,
  mapLayersB,
  mapAStyle,
  mapBStyle,
} = storeToRefs(compareStore);

// MapLibre refs
const tooltip = ref<HTMLElement>();
const compareTooltip = ref<HTMLElement>();
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
  if (!container) return;
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


const handleMapReady = async (newMap: Map, mapId: 'A' | 'B') => {
  if (mapStore.availableBasemaps.length === 0) {
    await mapStore.fetchAvailableBasemaps();
  }
    newMap.addControl(attributionControl);
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
    newMap.on("click", (e) => {
      // check if click is in the compare map and it's enabled
      if (e.point.x > compareStore.sliderEnd.position && isComparing.value) {
        return; // let the compare map handle this click
      }
      mapStore.clickedFeature = undefined;
    });
    if (mapId === 'A') {
        newMap.setStyle(mapStore.currentBasemap?.style as StyleSpecification);
        mapStore.map = newMap;
        mapStore.resetMapPosition(undefined, true);
    } else if (mapId === 'B') {
        mapStore.compareMap = newMap;
        newMap.on("click", () => {mapStore.compareClickedFeature = undefined });
        createMapControls(newMap, 'B');
        // the B map style is compared implicitly we need to add click handlers for features here as well
        if (mapBStyle.value && mapBStyle.value?.sources)
        Object.entries(mapBStyle.value.sources).forEach(([key,source]) => {
          if (source.type === 'vector') {
            mapStore.setupVectorLayerClickHandlers(newMap, key, mapStore.handleCompareLayerClick);
          }
        });
    }
    createMapControls(newMap);
    newMap.once('idle', () => {
      layerStore.updateLayersShown();
    });
}

function createMapControls(map: Map, mapType: 'A' | 'B' = 'A') {
  const currentTooltip = mapType === 'A' ? tooltip : compareTooltip;
  if (!map || !currentTooltip.value) {
    throw new Error("Map or tooltip not initialized!");
  }

  // Add tooltip overlay
  const popup = new Popup({
    anchor: "bottom-left",
    closeOnClick: false,
    maxWidth: "none",
    closeButton: true,
  });

  // Link overlay ref to dom, allowing for modification elsewhere
    popup.setDOMContent(currentTooltip.value);
  if (mapType === 'A') {
    // Set store value
    mapStore.tooltipOverlay = popup;
    return;
  } else if (mapType === 'B') {
    // Set store value
    mapStore.compareTooltipOverlay = popup;
    return;
  }
}

watch(() => appStore.theme, () => {
  if (!mapStore.map) return;
  mapStore.setBasemapToDefault();
  setAttributionControlStyle();
  //layerStore.updateLayersShown();
});

watch(() => appStore.openSidebars, () => {
  setAttributionControlStyle();
});

const transformRequest = (url: string, _resourceType?: ResourceType) => {
    // Only add auth headers to our own tile requests
    if (url.includes(import.meta.env.VITE_APP_API_ROOT)) {
        return {
            url,
            headers: oauthClient?.authHeaders,
        };
    }
    return { url };
}

// @ts-ignore for "Type instantiation is excessively deep and possibly infinite"
const mapStyleA: Ref<StyleSpecification | string> = ref(mapStore.currentBasemap?.style as StyleSpecification);
watch(isComparing, (newVal) => {
   if (!newVal && mapStore.map) {
        mapStore.map.jumpTo({
            center: mapStats.value?.center,
            zoom: mapStats.value?.zoom,
            bearing: mapStats.value?.bearing,
            pitch: mapStats.value?.pitch,
        });
        mapStore.compareMap = undefined;
    } else if (newVal && mapStore.map) {
        mapStyleA.value = mapStore.map.getStyle();
        compareStore.updateSlider({percentage: 50, position: window.innerWidth * 0.5});
    }
});

watch(mapAStyle, (newStyle) => {
    if (isComparing.value && mapStore.map) {
        mapStyleA.value = newStyle as StyleSpecification;
    }
}, { deep: true});

// Updating the basemap for either map should update both maps
// Maps need to load their style if is a direct url string before updating mapStyleA
// Then if comparing we need to do another idle until mapB is updated and then set the order
const updateBasemap = () => {
  const map  = mapStore.map;
  if (map && mapStore.currentBasemap) {
    const visible = mapStore.currentBasemap.id !== undefined
    mapStore.setBasemapVisibility(visible);
    if (visible) {
      if (mapStore.currentBasemap.style) {
        map.setStyle(mapStore.currentBasemap.style);
        map.once('idle', () => {
          layerStore.updateLayersShown();
          if (isComparing.value && mapStore.compareMap && mapStore.currentBasemap?.style) {
            mapStore.compareMap.setStyle(mapStore.currentBasemap.style);
            compareStore.mapLayersA = compareStore.updateCompareLayersList('A');
            if (mapStore.compareMap) {
              mapStore.compareMap.once('idle', () => {
                compareStore.updateCompareLayerStyle();
                compareStore.mapLayersB = compareStore.updateCompareLayersList('B');
              });
            }
          }
        });
      }
    }
  }
}

watch(() => mapStore.currentBasemap, () => {
    updateBasemap();
});

const swiperColor = computed(() => {
    return {
      swiper: theme.global.current.value.colors.primary,
      arrow: theme.global.current.value.colors['button-text'],
    };
});
</script>

<template>
    <div>
        <ToggleCompare
            :map-style-a="mapStyleA"
            :map-style-b="mapBStyle"
            :map-layers-a="mapLayersA"
            :map-layers-b="mapLayersB"
            :compare-enabled="compareStore.isComparing"
            :camera="{
                center: mapStats.center,
                zoom: mapStats.zoom,
            }"
            :transform-request="transformRequest"
            :swiper-options="{
                orientation: compareStore.orientation,
                grabThickness: 20,
                lineColor: swiperColor.swiper,
                handleColor: swiperColor.swiper,
                arrowColor: swiperColor.arrow,
            }"
            layer-order="bottommost"
            :attribution-control="false"
            :preserve-drawing-buffer="true"
            @panend="compareStore.updateMapStats($event)"
            @zoomend="compareStore.updateMapStats($event)"
            @pitchend="compareStore.updateMapStats($event)"
            @rotateend="compareStore.updateMapStats($event)"
            @sliderend="compareStore.updateSlider($event)"
            @map-ready-a="handleMapReady($event, 'A')"
            @map-ready-b="handleMapReady($event, 'B')"
            class="map"
        />

        <div id="map-tooltip" ref="tooltip" class="tooltip">
        <MapTooltip />
        </div>
        <div id="map-tooltip" ref="compareTooltip" class="tooltip">
        <MapTooltip compare-map />
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
