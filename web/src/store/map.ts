import { defineStore } from "pinia";
import { ref, shallowRef, watch } from "vue";
import type {
  ClickedFeatureData,
  Project,
  RasterData,
  VectorData,
  LayerFrame,
  MapLibreLayerWithMetadata,
  MapLibreLayerMetadata,
  Layer,
  StyleFilter,
  Basemap,
} from "@/types";
import type {
  MapLayerMouseEvent,
  Source,
  LayerSpecification,
} from "maplibre-gl";
import { Map, Popup } from "maplibre-gl";
import { getBasemaps } from "@/api/rest";
import { baseURL } from "@/api/auth";
import proj4 from "proj4";
import {
  useStyleStore,
  useLayerStore,
  useAppStore,
  useProjectStore,
  useFramePreviewStore,
} from ".";
import { layerStyleKey } from "./style";
import {
  isPreviewMapLayerId,
  removeAllPreviewLayersForLayerKey,
} from "@/utils/framePreviewLayer";

function getLayerIsVisible(layer: MapLibreLayerWithMetadata) {
  // Since visibility must be 'visible' for a feature click to even be registered,
  // we know that if it's not multiFrame, then it is indeed visible
  if (!layer.metadata.multiFrame) {
    return true;
  }

  // Try to check opacity now
  if (layer.paint === undefined) {
    throw new Error("Layer paint property is undefined");
  }

  const opacityKeys = Object.keys(layer.paint).filter((key) =>
    key.endsWith("-opacity"),
  );
  const opaque = opacityKeys.every(
    (key) => layer.paint![key as keyof MapLibreLayerWithMetadata["paint"]] > 0,
  );

  return opaque;
}

function sourceIdFromMapLayerId(mapLayerId: string) {
  return mapLayerId.split(".").slice(0, -1).join(".");
}

/**
 * Note: Rasters also have an extra `bounds` source, which allows for
 * interaction with the raster layer. This is not considered in this
 * function, as it's rarely accessed directly.
 */
function sourceIdFromLayerFrame(layer: Layer, frame: LayerFrame) {
  const parts: (number | string)[] = [layerStyleKey(layer), frame.id];

  if (frame.vector) {
    parts.push("vector");
    parts.push(frame.vector.id);
  } else if (frame.raster) {
    parts.push("raster");
    parts.push(frame.raster.id);
  } else {
    throw new Error("Layer frame is neither raster nor vector!");
  }

  return parts.join(".");
}

type SourceType = "vector" | "raster" | "bounds";
interface SourceDescription {
  layerId: number;
  layerCopyId: number;
  frameId: number;
  type: SourceType;
  typeId: number;
}

/**
 * Source format is <layerId>.<layerCopyId>.<frameId>.<type>.<typeId>
 */
function parseSourceString(sourceId: string): SourceDescription {
  const parts = sourceId.split(".");
  if (parts.length !== 5) {
    throw new Error(`Source string incompatible: ${sourceId}`);
  }

  const [layerId, layerCopyId, frameId, type, typeId] = parts;
  return {
    layerId: parseInt(layerId),
    layerCopyId: parseInt(layerCopyId),
    frameId: parseInt(frameId),
    type: type as SourceType,
    typeId: parseInt(typeId),
  };
}

interface LayerDescription extends SourceDescription {
  layerType: LayerSpecification["type"];
}

/**
 * Map layer format is <layerId>.<layerCopyId>.<frameId>.<type>.<typeId>.<mapLayerType>
 *
 * "mapLayerType" is the maplibre layer type, e.g. raster, fill, etc.
 */
function parseLayerString(layerId: string): LayerDescription {
  const parts = layerId.split(".");
  if (parts.length !== 6) {
    throw new Error(`Layer string incompatible: ${layerId}`);
  }

  const layerType = parts[parts.length - 1] as LayerDescription["layerType"];
  const sourceDesc = parseSourceString(sourceIdFromMapLayerId(layerId));
  return {
    ...sourceDesc,
    layerType,
  };
}

export const useMapStore = defineStore("map", () => {
  const map = shallowRef<Map>();
  const compareMap = shallowRef<Map>();
  const availableBasemaps = ref<Basemap[]>([]);
  const currentBasemap = ref<Basemap>();
  const tooltipOverlay = ref<Popup>();
  const compareTooltipOverlay = ref<Popup>();
  const clickedFeature = ref<ClickedFeatureData>();
  const compareClickedFeature = ref<ClickedFeatureData>();
  const rasterSourceTileURLs = ref<Record<string, string>>({});

  const styleStore = useStyleStore();
  const layerStore = useLayerStore();
  const appStore = useAppStore();
  const projectStore = useProjectStore();

  async function fetchAvailableBasemaps() {
    availableBasemaps.value = [{ name: "None" }, ...(await getBasemaps())];
    setBasemapToDefault();
  }

  function setBasemapToDefault() {
    if (
      !currentBasemap.value ||
      currentBasemap.value.name.toLowerCase().includes("basic")
    ) {
      currentBasemap.value = availableBasemaps.value.find((basemap) => {
        return basemap.name.toLowerCase() === "basic " + appStore.theme;
      });
    }
  }

  function setBasemapVisibility(visible: boolean) {
    const map = getMap();
    const baseLayerSourceIds = getBaseLayerSourceIds();
    map.getLayersOrder().forEach((id) => {
      const layer = map.getLayer(id);
      if (layer && baseLayerSourceIds.includes(layer.source)) {
        map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
      }
    });
  }

  function handleBaseLayerClick(e: MapLayerMouseEvent) {
    handleLayerClick(e);
  }

  function handleCompareLayerClick(e: MapLayerMouseEvent) {
    handleLayerClick(e, true);
  }

  function handleLayerClick(e: MapLayerMouseEvent, compare = false) {
    const map = getMap(compare);
    const clickedFeatures = map
      .queryRenderedFeatures(e.point)
      .filter((feat) =>
        getLayerIsVisible(feat.layer as MapLibreLayerWithMetadata),
      );

    if (!clickedFeatures.length) {
      return;
    }

    // Sort features that were clicked on by their reverse layer ordering,
    // since the last element in the list (the top one) should be the first one clicked.
    const featQuery = clickedFeatures.toSorted((feat1, feat2) => {
      const order = map.getLayersOrder();
      return order.indexOf(feat2.layer.id) - order.indexOf(feat1.layer.id);
    });

    // Select the first feature in this ordering, since this is the one that should be clicked on
    const feature = featQuery[0];
    const clickedFeatureRef = compare ? compareClickedFeature : clickedFeature;
    // Perform this check to prevent unnecessary repeated assignment
    if (feature !== clickedFeatureRef.value?.feature) {
      clickedFeatureRef.value = {
        feature,
        pos: e.lngLat,
      };
    }
  }

  function getMap(compare = false) {
    if (compare) {
      if (compareMap.value === undefined) {
        throw new Error("Compare map not yet initialized!");
      }
      return compareMap.value;
    } else {
      if (map.value === undefined) {
        throw new Error("Map not yet initialized!");
      }
      return map.value;
    }
  }

  function getMapSources() {
    const map = getMap();
    return [
      ...new Set(
        map.getLayersOrder().map((layerId) => map.getLayer(layerId)!.source),
      ),
    ];
  }

  function getBaseLayerSourceIds() {
    return getMapSources().filter(
      (sourceId) =>
        !sourceId ||
        !(
          sourceId.includes(".vector.") ||
          sourceId.includes(".raster.") ||
          sourceId.includes(".bounds.")
        ),
    );
  }

  function getBaseLayerIds() {
    const map = getMap();
    return [
      ...new Set(
        map
          .getLayersOrder()
          .filter(
            (layerId) =>
              !layerId.includes(".vector.") && !layerId.includes(".raster."),
          ),
      ),
    ];
  }

  function getUserMapLayers() {
    const map = getMap();
    const baseLayerSourceIds = getBaseLayerSourceIds();
    return map.getLayersOrder().filter((id) => {
      if (id === "background") return false;
      const layer = map.getLayer(id);
      return layer && !baseLayerSourceIds.includes(layer.source);
    });
  }

  function getCurrentMapPosition() {
    const map = getMap();
    const { lat, lng } = map.getCenter();
    return {
      center: [lng, lat],
      zoom: map.getZoom(),
    };
  }

  function getTooltip(compare = false) {
    if (compare) {
      if (compareTooltipOverlay.value === undefined) {
        throw new Error("Compare tooltip not yet initialized!");
      }
      return compareTooltipOverlay.value;
    }
    if (tooltipOverlay.value === undefined) {
      throw new Error("Tooltip not yet initialized!");
    }
    return tooltipOverlay.value;
  }

  function setMapPosition(
    center: [number, number],
    zoom: number,
    jump = false,
  ) {
    const map = getMap();
    if (jump) {
      map.jumpTo({ center, zoom });
    } else {
      map.flyTo({ center, zoom, duration: 2000 });
    }
  }

  function resetMapPosition(
    project: Project | undefined = undefined,
    jump = false,
  ) {
    let center: [number, number] = [0, 30];
    let zoom = 1;
    if (project) {
      center = project.default_map_center;
      zoom = project.default_map_zoom;
    }
    setMapPosition(center, zoom, jump);
  }

  function clearMapLayers() {
    removeLayers(getUserMapLayers());
  }

  function removeLayers(layerIds: string[]) {
    const map = getMap();
    const framePreviewStore = useFramePreviewStore();
    const cleanedLayerKeys = new Set<string>();

    // Must collect all source Ids so they can be removed after all layers
    // have been removed, since multple layers may use the same source
    const sourceIdsToRemove = new Set<string>();
    const updatedLayerIds: string[] = [];
    layerIds.forEach((id) => {
      if (isPreviewMapLayerId(id)) {
        return;
      }
      const layerKey = id.split(".").slice(0, 2).join(".");
      if (layerKey.includes(".")) {
        cleanedLayerKeys.add(layerKey);
      }
      // Rasters have implicit bounds layers that also need to be removed
      if (id.includes(".raster.")) {
        updatedLayerIds.push(id.replace(".raster.", ".bounds."));
      }
      updatedLayerIds.push(id);
    });
    const layersToRemove = getUserMapLayers().filter((id) =>
      updatedLayerIds.includes(id),
    );
    layersToRemove.forEach((id) => {
      sourceIdsToRemove.add(map.getLayer(id)!.source);
      map.removeLayer(id);
    });

    // Now remove the sources
    sourceIdsToRemove.forEach((id) => {
      map.removeSource(id);
    });

    cleanedLayerKeys.forEach((layerKey) => {
      removeAllPreviewLayersForLayerKey(map, layerKey);
      const [layerId, copyId] = layerKey.split(".").map(Number);
      const layer = layerStore.selectedLayers.find(
        (candidate) => candidate.id === layerId && candidate.copy_id === copyId,
      );
      if (layer) {
        framePreviewStore.cleanupLayer(layer);
      }
    });
  }

  /**
   * Returns the description of the most recently added instance of a
   * layer to the map, or undefined if it's not on the map.
   */
  function getLatestLayerInstance(layer: Layer): LayerDescription | undefined {
    const matchingLayers = getUserMapLayers()
      .map((layerId) => parseLayerString(layerId))
      .filter((layerDesc) => layerDesc.layerId === layer.id);

    // Sort reverse, so the latest instance is first in the list;
    return matchingLayers.toSorted((a, b) => b.layerCopyId - a.layerCopyId)[0];
  }

  function createVectorFeatureMapLayers(source: Source, multiFrame: boolean) {
    const map = getMap();
    const { layerId, layerCopyId, frameId } = parseSourceString(source.id);
    const metadata: MapLibreLayerMetadata = {
      layer_id: layerId,
      layer_copy_id: layerCopyId,
      frame_id: frameId,
      multiFrame,
    };

    // Fill Layer
    map.addLayer({
      id: source.id + ".fill",
      type: "fill",
      source: source.id,
      metadata,
      "source-layer": "default",
      filter: [
        "match",
        ["geometry-type"],
        ["Polygon", "MultiPolygon"],
        true,
        false,
      ],
      layout: {
        visibility: "visible",
      },
      paint: {
        "fill-color": "black",
        "fill-opacity": 0.5,
      },
    });

    // Line Layer
    map.addLayer({
      id: source.id + ".line",
      type: "line",
      source: source.id,
      metadata,
      "source-layer": "default",
      layout: {
        "line-join": "round",
        "line-cap": "round",
        visibility: "visible",
      },
      paint: {
        "line-color": "black",
        "line-width": 2,
        "line-opacity": 1,
      },
    });

    // Circle Layer
    map.addLayer({
      id: source.id + ".circle",
      type: "circle",
      source: source.id,
      metadata,
      "source-layer": "default",
      filter: [
        "match",
        ["geometry-type"],
        ["Point", "MultiPoint"],
        true,
        false,
      ],
      paint: {
        "circle-color": "black",
        "circle-opacity": 1,
        "circle-stroke-color": "black",
        "circle-stroke-opacity": 1,
        "circle-stroke-width": 2,
        "circle-radius": 5,
      },
      layout: {
        visibility: "visible",
      },
    });
    setupVectorLayerClickHandlers(map, source.id, handleBaseLayerClick);
  }

  function setupVectorLayerClickHandlers(
    map: Map,
    sourceId: string,
    handler: (e: MapLayerMouseEvent) => void,
  ) {
    map.on("click", sourceId + ".fill", handler);
    map.on("click", sourceId + ".line", handler);
    map.on("click", sourceId + ".circle", handler);
  }

  function createRasterFeatureMapLayers(
    tileSource: Source,
    boundsSource: Source,
    multiFrame: boolean,
    rasterOpacity = 1,
  ) {
    const map = getMap();
    const { layerId, layerCopyId, frameId } = parseSourceString(tileSource.id);
    const metadata: MapLibreLayerMetadata = {
      layer_id: layerId,
      layer_copy_id: layerCopyId,
      frame_id: frameId,
      multiFrame,
    };

    // Tile Layer
    map.addLayer({
      id: tileSource.id + ".raster",
      type: "raster",
      source: tileSource.id,
      metadata,
      paint: {
        "raster-opacity": rasterOpacity,
      },
    });

    const boundsLayerId = boundsSource.id + ".fill";
    map.addLayer({
      id: boundsLayerId,
      type: "fill",
      source: boundsSource.id,
      paint: {
        "fill-opacity": 0,
      },

      // Must ensure multiFrame is always false for this layer, since
      // the opacity of will always be 0, but it must still be clickable
      metadata: { ...metadata, multiFrame: false },
    });

    map.on("click", boundsLayerId, handleLayerClick);
  }

  function createVectorTileSource(
    vector: VectorData,
    sourceId: string,
    multiFrame: boolean,
  ): Source | undefined {
    const map = getMap();
    map.addSource(sourceId, {
      type: "vector",
      tiles: [`${baseURL}vectors/${vector.id}/tiles/{z}/{x}/{y}/`],
    });
    const source = map.getSource(sourceId);
    if (source) {
      createVectorFeatureMapLayers(source, multiFrame);
      return source;
    }
  }

  function createRasterTileSource(
    raster: RasterData,
    sourceId: string,
    multiFrame: boolean,
    rasterOpacity = 1,
  ): Source | undefined {
    const map = getMap();

    const { layerId, layerCopyId } = parseSourceString(sourceId);
    const styleSpec =
      styleStore.selectedLayerStyles[`${layerId}.${layerCopyId}`].style_spec;
    let filters: StyleFilter[] = [];
    const layer = layerStore.selectedLayers.find(
      (l: Layer) => l.id === layerId,
    );
    if (layer) {
      const frames = layerStore.layerFrames(layer);
      const frame = frames.find(
        (f: LayerFrame) => f.index === layer.current_frame_index,
      );
      if (frame?.source_filters) {
        filters = styleStore.sourceFiltersToStyleFilters(frame.source_filters);
      }
    }
    const queryParams = styleStore.buildRasterTileQueryParams(
      styleSpec ?? styleStore.getDefaultStyleSpec(raster, layerId),
      filters,
      styleStore.colormaps,
    );
    const query = new URLSearchParams(queryParams);
    rasterSourceTileURLs.value[sourceId] =
      `${baseURL}rasters/${raster.id}/tiles/{z}/{x}/{y}.png/?${query}`;
    map.addSource(sourceId, {
      type: "raster",
      tiles: [rasterSourceTileURLs.value[sourceId]],
    });
    const tileSource = map.getSource(sourceId);

    const bounds = raster.metadata.bounds;
    const boundsSourceId = sourceId.replace("raster", "bounds");
    const { srs } = bounds;
    let { xmin, xmax, ymin, ymax } = bounds;
    [xmin, ymin] = proj4(srs, "EPSG:4326", [xmin, ymin]);
    [xmax, ymax] = proj4(srs, "EPSG:4326", [xmax, ymax]);
    map.addSource(boundsSourceId, {
      type: "geojson",
      data: {
        type: "Polygon",
        coordinates: [
          [
            [xmin, ymin],
            [xmin, ymax],
            [xmax, ymax],
            [xmax, ymin],
            [xmin, ymin],
          ],
        ],
      },
    });
    const boundsSource = map.getSource(boundsSourceId);

    if (tileSource && boundsSource) {
      createRasterFeatureMapLayers(
        tileSource,
        boundsSource,
        multiFrame,
        rasterOpacity,
      );
      return tileSource;
    }
  }

  function addLayerFrameToMap(
    frame: LayerFrame,
    sourceId: string,
    multiFrame: boolean,
    options?: { rasterOpacity?: number },
  ) {
    if (getMapSources().includes(sourceId)) {
      return;
    }

    if (frame.vector) {
      createVectorTileSource(frame.vector, sourceId, multiFrame);
    } else if (frame.raster) {
      createRasterTileSource(
        frame.raster,
        sourceId,
        multiFrame,
        options?.rasterOpacity,
      );
    } else {
      throw new Error("Layer Frame is neither raster nor vector!");
    }
  }

  watch(map, () => {
    // Once map is initialized, attempt to load URL view
    if (map.value) {
      projectStore.loadViewStateFromURL();
    }
  });

  return {
    // Data
    map,
    compareMap,
    availableBasemaps,
    currentBasemap,
    tooltipOverlay,
    compareTooltipOverlay,
    clickedFeature,
    compareClickedFeature,
    rasterSourceTileURLs,
    // Functions
    getBaseLayerSourceIds,
    getBaseLayerIds,
    fetchAvailableBasemaps,
    setBasemapToDefault,
    setBasemapVisibility,
    handleLayerClick,
    handleBaseLayerClick,
    handleCompareLayerClick,
    getMap,
    getMapSources,
    getCurrentMapPosition,
    getTooltip,
    setMapPosition,
    resetMapPosition,
    clearMapLayers,
    removeLayers,
    createVectorFeatureMapLayers,
    createRasterFeatureMapLayers,
    createVectorTileSource,
    createRasterTileSource,
    addLayerFrameToMap,
    sourceIdFromMapLayerId,
    parseSourceString,
    parseLayerString,
    sourceIdFromLayerFrame,
    getLatestLayerInstance,
    getUserMapLayers,
    setupVectorLayerClickHandlers,
  };
});
