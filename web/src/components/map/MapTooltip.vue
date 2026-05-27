<script setup lang="ts">
import { computed, ref, watch } from "vue";
import * as turf from "@turf/turf";
import proj4 from "proj4";

import RecursiveTable from "../RecursiveTable.vue";
import { useMapStore, useLayerStore, useNetworkStore } from "@/store";
import { useMapCompareStore } from "@/store/compare";

const layerStore = useLayerStore();
const networkStore = useNetworkStore();
const mapStore = useMapStore();
const compareStore = useMapCompareStore();

const props = defineProps({
  compareMap: {
    type: Boolean,
    default: false,
  },
});

const clickedFeature = computed({
  get() {
    return props.compareMap
      ? mapStore.compareClickedFeature
      : mapStore.clickedFeature;
  },
  set(value) {
    if (props.compareMap) {
      mapStore.compareClickedFeature = value;
    } else {
      mapStore.clickedFeature = value;
    }
  },
});

const clickedFeatureIsDeactivatedNode = ref(false);

const clickedFeatureProperties = computed(() => {
  if (clickedFeature.value === undefined) {
    return {};
  }
  const unwantedKeys = new Set([
    "colors",
    "geometry",
    "type",
    "id",
    "node_id",
    "edge_id",
    "to_node_id",
    "from_node_id",
  ]);
  return Object.fromEntries(
    Object.entries(clickedFeature.value.feature.properties).filter(
      ([k, v]: [string, unknown]) => k && !unwantedKeys.has(k) && v,
    ),
  );
});

const clickedFeatureSourceType = computed(() => {
  if (clickedFeature.value) {
    const feature = clickedFeature.value.feature;
    if (feature.source.includes(".vector")) return "vector";
    if (feature.source.includes(".bounds")) return "raster";
  }
  return undefined;
});

const rasterValue = computed(() => {
  if (clickedFeature.value && clickedFeatureSourceType.value === "raster") {
    const feature = clickedFeature.value.feature;
    const { raster } = layerStore.getDBObjectsForSourceID(feature.source);
    if (raster?.id) {
      const data = mapStore.rasterTooltipDataCache[raster.id]?.data;
      if (data) {
        const { lng, lat } = clickedFeature.value.pos;
        const { srs } = raster.metadata.bounds;
        let { xmin, xmax, ymin, ymax } = raster.metadata.bounds;
        [xmin, ymin] = proj4(srs, "EPSG:4326", [xmin, ymin]);
        [xmax, ymax] = proj4(srs, "EPSG:4326", [xmax, ymax]);
        // Convert lat/lng to array indices
        const x = Math.floor(((lng - xmin) / (xmax - xmin)) * data[0].length);
        const y = Math.floor((1 - (lat - ymin) / (ymax - ymin)) * data.length);
        return data[y][x];
      }
    }
  }
  return undefined;
});

function zoomToFeature() {
  if (clickedFeature.value === undefined) {
    return;
  }
  // Set map zoom to match bounding box of region
  const map = mapStore.getMap(props.compareMap);
  const buffered = turf.buffer(clickedFeature.value.feature, 0.5, {
    units: "kilometers",
  });
  if (!buffered) return;
  const bbox = turf.bbox(buffered);
  if (bbox.length !== 4) {
    throw new Error("Returned bbox should have 4 elements!");
  }
  map.fitBounds(bbox, { maxZoom: map.getZoom() });
}

// Check if the layer associated with the clicked feature is still selected and visible
watch(
  () => layerStore.selectedLayers,
  () => {
    if (clickedFeature.value === undefined) {
      return;
    }
    const feature = clickedFeature.value.feature;
    const sourceId = feature.source;
    const { layer } = layerStore.getDBObjectsForSourceID(sourceId);
    if (!layer?.visible) {
      clickedFeature.value = undefined;
    }
  },
);

// Handle clicked features and raster tooltip behavior.
// Feature clicks are given tooltip priority.
watch(clickedFeature, () => {
  const tooltip = mapStore.getTooltip(props.compareMap);
  if (clickedFeature.value === undefined) {
    tooltip.remove();
    return;
  }
  // Set tooltip position. Give feature clicks priority
  const centroid = turf.centroid(clickedFeature.value.feature);
  const center = centroid.geometry.coordinates as [number, number];
  tooltip.setLngLat(center);
  // This makes the tooltip visible
  tooltip.addTo(mapStore.getMap(props.compareMap));
  // Don't zoom to feature if comparing maps
  if (!compareStore.isComparing) {
    zoomToFeature();
  }
});

async function updateClickedFeatureIsDeactivatedNode() {
  if (clickedFeature.value) {
    const feature = clickedFeature.value.feature;
    const sourceId = feature.source;
    const nodeId = clickedFeature.value.feature.properties.node_id;
    const { dataset } = layerStore.getDBObjectsForSourceID(sourceId);
    if (dataset) {
      const active = await networkStore.isNodeActive(nodeId, dataset);
      clickedFeatureIsDeactivatedNode.value = !active;
    } else {
      clickedFeatureIsDeactivatedNode.value = false;
    }
  }
}

watch(clickedFeature, updateClickedFeatureIsDeactivatedNode);

function toggleNodeHandler() {
  if (clickedFeature.value === undefined) {
    throw new Error("Clicked node is undefined!");
  }
  const feature = clickedFeature.value.feature;
  const sourceId = feature.source;
  const nodeId = clickedFeature.value.feature.properties.node_id;
  const { dataset, layer } = layerStore.getDBObjectsForSourceID(sourceId);
  if (nodeId && dataset && layer) {
    networkStore.toggleNodeActive(nodeId, dataset);
  }
  updateClickedFeatureIsDeactivatedNode();
}
</script>

<template>
  <div
    v-if="clickedFeature && clickedFeatureSourceType === 'vector'"
    style="max-height: 40vh; overflow: auto"
  >
    <RecursiveTable :data="clickedFeatureProperties" />

    <!-- Render for Network Nodes -->
    <!-- TODO: Eventually allow deactivating Network Edges -->
    <v-btn
      v-if="clickedFeature.feature.properties.node_id"
      block
      variant="outlined"
      @click="toggleNodeHandler"
      :text="
        clickedFeatureIsDeactivatedNode ? 'Reactivate Node' : 'Deactivate Node'
      "
    />
  </div>

  <!-- Check for raster tooltip data after, to give clicked features priority -->
  <div v-else-if="clickedFeatureSourceType === 'raster'">
    <div v-if="rasterValue === undefined">
      <span>fetching raster data...</span>
    </div>
    <div v-else class="mr-3">Value: {{ rasterValue }}</div>
  </div>
</template>

<style>
.maplibregl-popup-content {
  background-color: rgb(var(--v-theme-surface)) !important;
  border-top-color: rgb(var(--v-theme-surface)) !important;
}

.maplibregl-popup-tip {
  border-top-color: rgb(var(--v-theme-surface)) !important;
}

.maplibregl-popup-close-button {
  font-size: 24px;
  margin-right: 5px;
}
</style>
