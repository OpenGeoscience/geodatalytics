import { defineStore } from "pinia";
import { ref } from "vue";
import { RasterTileSource } from "maplibre-gl";
import type {
  AppliedColormap,
  Colormap,
  Layer,
  LayerFrame,
  LayerStyle,
  MapLibreLayerWithMetadata,
  PropertySummary,
  RasterData,
  StyleFilter,
  StyleSpec,
  VectorData,
} from "@/types";
import { getProjectColormaps } from "@/api/rest";
import chroma from "chroma-js";

import {
  useMapStore,
  useLayerStore,
  useProjectStore,
  useNetworkStore,
} from ".";

export interface MapLayerStyleRaw {
  paint: {
    "fill-opacity"?: any;
    "fill-color"?: any;
    "line-opacity"?: any;
    "line-color"?: any;
    "line-width"?: any;
    "circle-opacity"?: any;
    "circle-stroke-opacity"?: any;
    "circle-color"?: any;
    "circle-stroke-color"?: any;
    "circle-radius"?: any;
    "raster-opacity"?: any;
  };
  tileURL?: string;
  visibility: "visible" | "none";
}

// hues range 0-360, pick 8 distinct hues
const HUES = [0, 30, 60, 120, 180, 220, 270, 300];
// first iterate through all hues with 50% lightness, then pastels, then shades
const LIGHTNESSES = [0.5, 0.8, 0.3];

function getMidMarker(
  markerA: { color: string; value: number },
  markerB: { color: string; value: number },
) {
  const mid = chroma(markerA.color).mix(markerB.color, 0.5, "lab");
  return {
    color: mid.hex().toUpperCase(),
    value: (markerA.value + markerB.value) / 2,
  };
}

export function colormapMarkersSubsample(
  colormap: Colormap,
  appliedColormap: AppliedColormap,
  n: number | undefined = undefined,
) {
  let markers = colormap.markers;
  if (!n && appliedColormap.discrete && appliedColormap.n_colors && markers) {
    n = appliedColormap.n_colors;
  }
  if (n && markers) {
    while (n > markers.length) {
      const newMarkers = [];
      for (let i = 0; i < markers.length - 1; i++) {
        newMarkers.push(markers[i]);
        newMarkers.push(getMidMarker(markers[i], markers[i + 1]));
      }
      newMarkers.push(markers[markers.length - 1]);
      markers = newMarkers;
    }
    const elements = [markers[0]];
    const totalItems = markers.length - 1;
    const interval = Math.floor(totalItems / (n - 1));
    for (let i = 1; i < n - 1; i++) {
      elements.push(markers[i * interval]);
    }
    elements.push(markers[markers.length - 1]);
    return elements;
  }
  return markers;
}

// frame/band select which slice to read; they must be flat query params, not in style JSON
const RASTER_SOURCE_FILTER_KEYS = new Set(["frame", "band"]);

function sourceFiltersToStyleFilters(
  sourceFilters: Record<string, unknown> | undefined,
): StyleFilter[] {
  if (!sourceFilters || !Object.keys(sourceFilters).length) return [];
  return Object.entries(sourceFilters).map(([k, v]) => ({
    filter_by: k,
    list: [v],
    include: true,
    transparency: true,
    apply: true,
  }));
}

function getRasterSourceFilterParams(filters: StyleFilter[]) {
  const params: Record<string, string | number> = {};
  filters.forEach((f) => {
    if (
      f.apply &&
      f.filter_by &&
      f.include &&
      f.list?.length === 1 &&
      RASTER_SOURCE_FILTER_KEYS.has(f.filter_by)
    ) {
      params[f.filter_by] = f.list[0];
    }
  });
  return params;
}

function getRasterTilesQuery(styleSpec: StyleSpec, colormaps: Colormap[]) {
  let query: Record<string, any> = {};
  const colorSpecs = styleSpec.colors || [];
  colorSpecs.forEach((colorSpec) => {
    const colorQuery: Record<string, any> = {};
    const colormap = colorSpec.colormap?.id
      ? colormaps.find((cmap) => cmap.id === colorSpec.colormap?.id)
      : undefined;
    // Only send a style override when there is an actual palette. A colormap
    // object without a selected colormap (or Color mode "None") must omit
    // style so large-image renders native RGB / grayscale.
    if (colormap?.markers && colorSpec.colormap) {
      if (colorSpec.colormap.range) {
        colorQuery.min = colorSpec.colormap.range[0];
        colorQuery.max = colorSpec.colormap.range[1];
      }
      if (colorSpec.colormap.discrete) {
        colorQuery.scheme = "discrete";
      }
      if (colorSpec.colormap.clamp === false) {
        colorQuery.clamp = false;
      }
      colorQuery.palette = colormapMarkersSubsample(
        colormap,
        colorSpec.colormap,
      )?.map((marker) => marker.color);
    } else if (colorSpec.single_color) {
      colorQuery.palette = colorSpec.single_color;
    }
    if (colorSpec.name === "all") {
      if (colorSpec.visible) query = colorQuery;
    } else if (colorSpec.visible && Object.keys(colorQuery).length) {
      if (!query.bands) query.bands = [];
      colorQuery.band = colorSpec.name.replace("Band ", "");
      query.bands.push(colorQuery);
    }
  });
  styleSpec.filters.forEach((f) => {
    if (
      f.apply &&
      f.filter_by &&
      f.include &&
      f.list?.length === 1 &&
      !RASTER_SOURCE_FILTER_KEYS.has(f.filter_by)
    ) {
      query[f.filter_by] = f.list[0];
    }
  });
  return query;
}

function buildRasterTileQueryParams(
  styleSpec: StyleSpec,
  filters: StyleFilter[],
  colormaps: Colormap[],
) {
  const params: Record<string, string> = { projection: "epsg:3857" };
  Object.entries(getRasterSourceFilterParams(filters)).forEach(
    ([key, value]) => {
      params[key] = String(value);
    },
  );
  const styleQuery = getRasterTilesQuery({ ...styleSpec, filters }, colormaps);
  if (Object.keys(styleQuery).length) {
    params.style = JSON.stringify(styleQuery);
  }
  return params;
}

function getVectorColorPaintProperty(
  styleSpec: StyleSpec,
  groupName: string,
  propsSpec: Record<string, PropertySummary>,
  colormaps: Colormap[],
  stroke: boolean = false,
) {
  const colorSpecs = styleSpec.colors || [];
  const colorSpec = colorSpecs.find((c) => [groupName, "all"].includes(c.name));
  let baseColor: any = "#000";
  if (colorSpec?.single_color) {
    baseColor = colorSpec.single_color;
  } else if (colorSpec?.colormap?.color_by && propsSpec) {
    const colorByProp = propsSpec[colorSpec.colormap.color_by];
    if (!colorByProp) return undefined;
    const range = colorByProp.range;
    let nColors = colorSpec.colormap.n_colors;
    if (!nColors) return undefined;
    if (range && range[1] - range[0] < nColors) nColors = range[1] - range[0];
    const colormap = colormaps.find(
      (cmap) => cmap.id === colorSpec.colormap?.id,
    );
    if (!colormap) return undefined;
    const markers = colormapMarkersSubsample(
      colormap,
      colorSpec.colormap,
      nColors,
    );
    if (!markers) return undefined;
    if (range) {
      const [min, max] = range;
      const valueColors = markers.map((marker) => [
        Math.round(marker.value * (max - min) + min),
        marker.color,
      ]);
      if (colorSpec.colormap.discrete) {
        const cases: any[] = [];
        valueColors.forEach(([v, c]) => {
          cases.push(["<=", ["get", colorSpec.colormap?.color_by], v]);
          cases.push(c);
        });
        baseColor = ["case", ...cases, baseColor];
      } else {
        baseColor = [
          "interpolate",
          ["linear"],
          ["get", colorSpec.colormap.color_by],
          ...valueColors.flat(),
        ];
      }
    } else {
      const valueSet = Array.from(
        new Set(colorByProp.value_set.filter((v) => v)),
      );
      const sortedValues = valueSet.sort((a: any, b: any) => a - b);
      const valueColors = sortedValues
        .map((v, i) => {
          if (markers) {
            return [
              v,
              markers[
                Math.ceil(((i + 1) / sortedValues.length) * markers.length) - 1
              ]?.color,
            ];
          }
        })
        .flat();
      baseColor = [
        "match",
        ["get", colorSpec.colormap.color_by],
        ...valueColors,
        baseColor,
      ];
    }
    let nullColor = colorSpec.colormap.null_color;
    if (colorSpec.colormap.null_color === "transparent")
      nullColor = "#00000000";
    baseColor = [
      "case",
      ["==", ["get", colorSpec.colormap?.color_by], null],
      nullColor,
      ["==", ["get", colorSpec.colormap?.color_by], ""],
      nullColor,
      baseColor,
    ];
  }
  if (colorSpec?.use_feature_props) {
    const propName = stroke ? "stroke" : "fill";
    baseColor = ["coalesce", ["get", propName], baseColor];
  }
  return baseColor;
}

function getVectorSizePaintProperty(
  styleSpec: StyleSpec,
  groupName: string,
  propsSpec: Record<string, PropertySummary>,
) {
  const zoomScalingConstant = 500;
  const sizeSpec = styleSpec.sizes.find((c) =>
    [groupName, "all"].includes(c.name),
  );
  let baseSize: any = 5;
  let zoomedSize: any = undefined;
  if (sizeSpec?.single_size) {
    baseSize = sizeSpec.single_size;
    if (sizeSpec.zoom_scaling) zoomedSize = baseSize * zoomScalingConstant;
  } else if (sizeSpec?.size_range?.size_by && propsSpec) {
    const sizeByProp = propsSpec[sizeSpec.size_range.size_by];
    if (!sizeByProp?.range) return undefined;
    const [min, max] = sizeByProp.range;
    baseSize = [
      "interpolate",
      ["linear"],
      ["get", sizeSpec.size_range.size_by],
      min,
      sizeSpec.size_range.minimum,
      max,
      sizeSpec.size_range.maximum,
    ];
    if (sizeSpec.zoom_scaling) {
      zoomedSize = [...baseSize];
      zoomedSize[4] *= zoomScalingConstant;
      zoomedSize[6] *= zoomScalingConstant;
    }
    if (
      sizeSpec.size_range.null_size &&
      !sizeSpec.size_range.null_size.transparency
    ) {
      const nullSize = sizeSpec.size_range.null_size.size;
      baseSize = [
        "case",
        ["==", ["get", sizeSpec.size_range.size_by], null],
        nullSize,
        baseSize,
      ];
      zoomedSize = [
        "case",
        ["==", ["get", sizeSpec.size_range.size_by], null],
        nullSize,
        baseSize * zoomScalingConstant,
      ];
    }
  }
  if (zoomedSize) {
    return [
      "interpolate",
      ["exponential", 2],
      ["zoom"],
      12,
      baseSize,
      24,
      zoomedSize,
    ];
  } else return baseSize;
}

function getVectorVisibilityPaintProperty(
  styleSpec: StyleSpec,
  groupName: string,
) {
  const filters: any[] = [];
  const colorSpec = styleSpec.colors.find((c) =>
    [groupName, "all"].includes(c.name),
  );
  if (colorSpec && !colorSpec.visible) {
    return 0;
  }
  const sizeSpec = styleSpec.sizes.find((c) =>
    [groupName, "all"].includes(c.name),
  );
  if (
    sizeSpec?.size_range?.null_size?.transparency &&
    sizeSpec.size_range.size_by
  ) {
    filters.push(["==", ["get", sizeSpec.size_range.size_by], null]);
    filters.push(0);
  }
  styleSpec.filters.forEach((f) => {
    if (f.apply) {
      let filter;
      if (f.list) {
        filter = ["in", ["get", f.filter_by], ["literal", f.list]];
      } else if (f.range) {
        filter = [
          "all",
          [">=", ["get", f.filter_by], f.range[0]],
          ["<=", ["get", f.filter_by], f.range[1]],
        ];
      }

      if (filter) {
        if (f.include) filter = ["!", filter];
        filters.push(filter);
        filters.push(0);
      }
    }
  });
  const defaultOpacity = styleSpec.opacity;
  if (filters.length)
    return [
      "case",
      ...filters,
      groupName === "polygons" ? defaultOpacity / 2 : defaultOpacity,
    ];
}

export const useStyleStore = defineStore("style", () => {
  const selectedLayerStyles = ref<Record<string, LayerStyle>>({});
  const colormaps = ref<Colormap[]>([]);

  const mapStore = useMapStore();
  const projectStore = useProjectStore();
  const layerStore = useLayerStore();
  const networkStore = useNetworkStore();

  function getDefaultColor(layerId: number) {
    const color = chroma.hsl(
      HUES[layerId % HUES.length],
      1,
      LIGHTNESSES[Math.floor(layerId / HUES.length) % LIGHTNESSES.length],
    );
    return color.hex();
  }

  function fetchColormaps() {
    colormaps.value = [];
    if (projectStore.currentProject) {
      getProjectColormaps(projectStore.currentProject.id).then((results) => {
        colormaps.value = results;
        layerStore.updateLayersShown();
      });
    }
  }

  function getDefaultStyleSpec(
    raster: RasterData | null | undefined,
    layerId: number,
  ): StyleSpec {
    return {
      opacity: 1,
      default_frame: 0,
      colors: [
        {
          name: "all",
          visible: true,
          use_feature_props: true,
          single_color: raster ? undefined : getDefaultColor(layerId),
          colormap: undefined,
        },
      ],
      sizes: [{ name: "all", zoom_scaling: true, single_size: 5 }],
      filters: [],
    };
  }

  function updateLayerStyles(layer: Layer) {
    const map = mapStore.getMap();
    const frames = layerStore.layerFrames(layer);
    const currentFrame = frames.find(
      (f) => f.index === layer.current_frame_index,
    );
    if (!currentFrame) return;
    mapStore.getUserMapLayers().forEach((mapLayerId) => {
      const { layerId, layerCopyId, frameId } =
        mapStore.parseLayerString(mapLayerId);
      if (layerId === layer.id && layerCopyId === layer.copy_id) {
        if (frameId === currentFrame.id) {
          map.setLayoutProperty(
            mapLayerId,
            "visibility",
            layer.visible ? "visible" : "none",
          );
          const styleKey = `${layer.id}.${layer.copy_id}`;
          const currentStyleSpec: StyleSpec | undefined =
            selectedLayerStyles.value[styleKey].style_spec;
          if (currentStyleSpec) {
            setMapLayerStyle(
              mapLayerId,
              currentStyleSpec,
              currentFrame,
              currentFrame.vector,
            );
          }
        } else {
          map.setLayoutProperty(mapLayerId, "visibility", "none");
        }
      }
    });
    networkStore.styleVisibleNetworks();
  }

  type GeneratedLayerStyle = {
    paint: Record<string, any>;
    tileURL?: string;
  };

  function createMapLayerStyle(
    mapLayerId: string,
    styleSpec: StyleSpec,
    frame: LayerFrame | undefined,
    vector: VectorData | null,
  ): GeneratedLayerStyle | undefined {
    const map = mapStore.getMap();
    let filters: StyleFilter[] = styleSpec.filters || [];
    if (frame?.source_filters) {
      filters = [
        ...filters,
        ...sourceFiltersToStyleFilters(frame.source_filters),
      ];
    }
    const mapLayer = map.getLayer(mapLayerId) as
      | MapLibreLayerWithMetadata
      | undefined;
    if (mapLayer === undefined) {
      return;
    }
    let opacity = styleSpec.opacity;
    if (opacity === undefined) {
      opacity = 1;
    }
    const paint: Record<string, any> = {};
    const propsSpec = vector?.summary?.properties;

    // Ensure that all colormaps have been fetched from db
    styleSpec.colors.forEach((colorConfig) => {
      if (
        colorConfig.colormap?.id &&
        !colormaps.value
          .map((cmap) => cmap.id)
          .includes(colorConfig.colormap.id)
      ) {
        fetchColormaps();
      }
    });

    if (mapLayerId.includes("fill") && propsSpec) {
      paint["fill-opacity"] = opacity / 2;
      const color = getVectorColorPaintProperty(
        styleSpec,
        "polygons",
        propsSpec,
        colormaps.value,
      );
      if (color) paint["fill-color"] = color;
      const visibility = getVectorVisibilityPaintProperty(
        { ...styleSpec, filters },
        "polygons",
      );
      if (visibility !== undefined) paint["fill-opacity"] = visibility;
    } else if (mapLayerId.includes("line") && propsSpec) {
      paint["line-opacity"] = opacity;
      const color = getVectorColorPaintProperty(
        styleSpec,
        "lines",
        propsSpec,
        colormaps.value,
      );
      if (color) paint["line-color"] = color;
      const size = getVectorSizePaintProperty(styleSpec, "lines", propsSpec);
      if (size) paint["line-width"] = size;
      const visibility = getVectorVisibilityPaintProperty(
        { ...styleSpec, filters },
        "lines",
      );
      if (visibility !== undefined) paint["line-opacity"] = visibility;
    } else if (mapLayerId.includes("circle") && propsSpec) {
      paint["circle-opacity"] = opacity;
      paint["circle-stroke-opacity"] = opacity;
      const color = getVectorColorPaintProperty(
        styleSpec,
        "points",
        propsSpec,
        colormaps.value,
      );
      if (color) {
        paint["circle-color"] = color;
      }
      const strokeColor = getVectorColorPaintProperty(
        styleSpec,
        "points",
        propsSpec,
        colormaps.value,
        true,
      );
      if (strokeColor) {
        paint["circle-stroke-color"] = strokeColor;
        paint["circle-stroke-width"] = 3;
      }
      const size = getVectorSizePaintProperty(styleSpec, "points", propsSpec);
      if (size) paint["circle-radius"] = size;
      const visibility = getVectorVisibilityPaintProperty(
        { ...styleSpec, filters },
        "points",
      );
      if (visibility !== undefined) {
        paint["circle-opacity"] = visibility;
        paint["circle-stroke-opacity"] = visibility;
      }
    } else if (mapLayerId.includes("raster")) {
      const rasterTilesQuery = getRasterTilesQuery(
        { ...styleSpec, filters },
        colormaps.value,
      );
      if (rasterTilesQuery?.bands && !rasterTilesQuery.bands.length)
        opacity = 0;
      paint["raster-opacity"] = opacity;
      let tileURL: string | undefined = undefined;
      const source = map.getSource(mapLayer.source) as RasterTileSource;
      const sourceURL = mapStore.rasterSourceTileURLs[mapLayer.source];
      if (source && sourceURL) {
        const newQuery = new URLSearchParams(
          buildRasterTileQueryParams(
            { ...styleSpec, filters },
            filters,
            colormaps.value,
          ),
        );
        tileURL = sourceURL.split("?")[0] + "?" + newQuery.toString();
        return { paint, tileURL };
      }
    }
    return { paint };
  }

  function setMapLayerStyle(
    mapLayerId: string,
    styleSpec: StyleSpec,
    frame: LayerFrame | undefined,
    vector: VectorData | null,
  ) {
    const map = mapStore.getMap();
    const result = createMapLayerStyle(mapLayerId, styleSpec, frame, vector);
    if (!result) return;

    for (const [key, value] of Object.entries(result.paint)) {
      map.setPaintProperty(mapLayerId, key, value);
    }

    if (result.tileURL) {
      const mapLayer = map.getLayer(mapLayerId) as MapLibreLayerWithMetadata;
      const source = map.getSource(mapLayer.source) as RasterTileSource;
      source?.setTiles([result.tileURL]);
      if (mapLayer.source) {
        mapStore.rasterSourceTileURLs[mapLayer.source] = result.tileURL;
      }
    }
  }

  function returnMapLayerStyle(
    mapLayerId: string,
    styleSpec: StyleSpec,
    frame: LayerFrame | undefined,
    vector: VectorData | null,
    visibility: "visible" | "none" = "visible",
  ) {
    const result = createMapLayerStyle(mapLayerId, styleSpec, frame, vector);
    if (!result) return;

    return {
      paint: result.paint,
      visibility,
      tileURL: result.tileURL,
    } as MapLayerStyleRaw;
  }

  return {
    colormaps,
    selectedLayerStyles,
    fetchColormaps,
    getRasterTilesQuery,
    getRasterSourceFilterParams,
    buildRasterTileQueryParams,
    sourceFiltersToStyleFilters,
    colormapMarkersSubsample,
    getDefaultColor,
    getDefaultStyleSpec,
    getVectorColorPaintProperty,
    updateLayerStyles,
    setMapLayerStyle,
    returnMapLayerStyle,
  };
});
