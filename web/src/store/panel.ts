import type {
  FloatingPanelConfig,
  TaskResult,
  Chart,
  Dataset,
  Layer,
  Network,
  RasterData,
  VectorData,
  Region,
} from "@/types";
import { defineStore } from "pinia";
import { ref } from "vue";
import { getChart, getDataset, getNetwork } from "@/api/rest";

import {
  useAppStore,
  useLayerStore,
  useAnalysisStore,
  useProjectStore,
  useMapStore,
  useNetworkStore,
} from ".";

const showableTypes = [
  "chart",
  "dataset",
  "network",
  "layer",
  "taskresult",
  "rasterdata",
  "vectordata",
  "region",
];

interface Showable {
  chart?: Chart;
  dataset?: Dataset;
  layer?: Layer;
  network?: Network;
  rasterdata?: RasterData;
  vectordata?: VectorData;
  taskresult?: TaskResult;
  region?: Region;
}

function defaultPanelArrangement(): FloatingPanelConfig[] {
  return [
    {
      id: "datasets",
      label: "Datasets",
      visible: true,
      closeable: false,
      dock: "left",
      order: 1,
    },
    {
      id: "layers",
      label: "Selected Layers",
      visible: true,
      closeable: false,
      dock: "left",
      order: 2,
    },
    {
      id: "legend",
      label: "Legend",
      visible: true,
      closeable: true,
      collapsed: true,
      dock: "right",
      order: 1,
    },
    {
      id: "charts",
      label: "Charts",
      visible: true,
      closeable: true,
      collapsed: true,
      dock: "right",
      order: 2,
    },
    {
      id: "networks",
      label: "Networks",
      visible: true,
      closeable: true,
      collapsed: true,
      dock: "right",
      order: 3,
    },
    {
      id: "analytics",
      label: "AI & Analytics",
      visible: true,
      closeable: true,
      collapsed: true,
      dock: "right",
      order: 4,
    },
  ];
}

export const usePanelStore = defineStore("panel", () => {
  const analysisStore = useAnalysisStore();
  const layerStore = useLayerStore();
  const appStore = useAppStore();
  const projectStore = useProjectStore();
  const mapStore = useMapStore();
  const networkStore = useNetworkStore();

  const panelArrangement = ref<FloatingPanelConfig[]>([]);
  const draggingPanel = ref<string | undefined>();
  const draggingFrom = ref<{ x: number; y: number } | undefined>();
  const dragModes = ref<("position" | "height" | "width")[]>();

  function resetPanels() {
    panelArrangement.value = defaultPanelArrangement();
  }

  function startDrag(
    event: MouseEvent,
    panel: FloatingPanelConfig | undefined,
    modes: ("position" | "width" | "height")[],
  ) {
    if (panel) {
      draggingPanel.value = panel.id;
    }
    draggingFrom.value = {
      x: event.clientX,
      y: event.clientY,
    };
    dragModes.value = modes;
  }

  function dragPanel(event: MouseEvent) {
    let offsetX = -5;
    const offsetY = 30;
    const minHeight = 175;
    const minWidth = 150;

    const panel = panelArrangement.value.find(
      (p) => p.id === draggingPanel.value,
    );
    if (!panel) return undefined;
    if (draggingFrom.value) {
      const from: { x: number; y: number } = { ...draggingFrom.value };

      if (panel.dock == "right") offsetX += document.body.clientWidth - 390;
      const position = {
        x: event.clientX - offsetX - (panel.element?.clientWidth || 0),
        y: event.clientY - offsetY,
      };
      if (dragModes.value?.includes("position")) {
        const allowDock =
          Math.abs(from.x - event.clientX) > 10 &&
          Math.abs(from.y - event.clientY) > 10;
        if (
          allowDock &&
          appStore.openSidebars.includes("left") &&
          event.clientX < 350
        ) {
          // dock left
          panel.dock = "left";
          panel.position = undefined;
          panel.width = undefined;
          panel.height = undefined;
          // determine order
          const currentDocked = panelArrangement.value.filter(
            (p) => p.dock === "left" && !p.position,
          );
          panel.order = Math.ceil(
            event.clientY / (document.body.clientHeight / currentDocked.length),
          );
        } else if (
          allowDock &&
          appStore.openSidebars.includes("right") &&
          event.clientX > document.body.clientWidth - 350
        ) {
          // dock right
          panel.dock = "right";
          panel.position = undefined;
          panel.width = undefined;
          panel.height = undefined;
          // determine order
          const currentDocked = panelArrangement.value.filter(
            (p) => p.dock === "right" && !p.position,
          );
          panel.order = Math.ceil(
            event.clientY / (document.body.clientHeight / currentDocked.length),
          );
        } else if (!panel.position) {
          // float
          panel.width = 300;
          panel.height = 200;
          panel.position = position;
        } else {
          panel.position = position;
        }
      }
      if (dragModes.value?.includes("height")) {
        if (!panel.height) {
          panel.height = panel.element?.clientHeight;
        }
        if (panel.height) {
          const heightDelta = event.clientY - draggingFrom.value.y;
          if (panel.height + heightDelta > minHeight) {
            panel.height = panel.height + heightDelta;
            from.y = event.clientY;
          }
        }
      }
      if (dragModes.value?.includes("width") && panel.width) {
        const widthDelta = event.clientX - draggingFrom.value.x;
        if (panel.width + widthDelta > minWidth) {
          panel.width = panel.width + widthDelta;
          from.x = event.clientX;
        }
      }
      draggingFrom.value = from;
    }
  }

  function stopDrag() {
    draggingPanel.value = undefined;
    draggingFrom.value = undefined;
    dragModes.value = [];
  }

  function isVisible(showable: Showable): boolean {
    if (showable.region) {
      return mapStore.regionShownId === showable.region.id;
    } else if (showable.chart) {
      const chartPanel = panelArrangement.value.find(
        (panel) => panel.id === "charts",
      );
      if (!chartPanel) return false;
      return (
        analysisStore.currentChart?.id == showable.chart.id &&
        chartPanel.visible
      );
    } else if (showable.dataset) {
      return layerStore.selectedLayers.some((layer) => {
        return layer.dataset === showable.dataset?.id && layer.visible;
      });
    } else if (showable.layer) {
      return layerStore.selectedLayers.some((layer) => {
        return layer.id === showable.layer?.id && layer.visible;
      });
    } else if (showable.network) {
      const dataset = projectStore.availableDatasets?.find(
        (d) => d.id === showable.network?.dataset,
      );
      return isVisible({ dataset });
    } else if (showable.taskresult) {
      const taskType = analysisStore.availableAnalysisTypes?.find(
        (t) => t.db_value === showable.taskresult?.task_type,
      );
      if (taskType) {
        const showableChildren: Record<string, any>[] = [];
        Object.entries(showable.taskresult.outputs).forEach(
          ([outputKey, outputValue]) => {
            const type = taskType?.output_types[outputKey].toLowerCase();
            if (showableTypes.includes(type)) {
              showableChildren.push({
                id: outputValue,
                type,
              });
            }
          },
        );
        Object.entries(showable.taskresult.inputs).forEach(
          ([inputKey, inputValue]) => {
            const type = taskType?.input_types[inputKey].toLowerCase();
            const value: Record<string, any> = taskType.input_options[
              inputKey
            ]?.find((o: any) => o.id === inputValue);
            if (showableTypes.includes(type)) {
              showableChildren.push({
                ...value,
                type,
              });
            }
          },
        );
        return showableChildren.every((o) => isVisible({ [o.type]: o }));
      }
    } else if (showable.rasterdata) {
      return isVisible({ dataset: { id: showable.rasterdata.dataset } });
    } else if (showable.vectordata) {
      return isVisible({ dataset: { id: showable.vectordata.dataset } });
    }
    return false;
  }

  async function setVisibility(showable: Showable, visible: boolean) {
    if (showable.region) {
      mapStore.showRegion(visible ? showable.region : undefined);
    } else if (showable.chart) {
      let chart = showable.chart;
      if (visible) {
        if (!chart.chart_data) {
          chart = await getChart(chart.id);
        }
        const chartPanel = panelArrangement.value.find(
          (panel) => panel.id === "charts",
        );
        if (chartPanel) {
          chartPanel.visible = true;
          chartPanel.collapsed = false;
        }
      }
      analysisStore.currentChart = visible ? chart : undefined;
    } else if (showable.dataset) {
      const id = showable.dataset.id;
      if (visible) await layerStore.fetchAvailableLayersForDataset(id);
      layerStore.availableLayers
        .filter((layer: Layer) => layer.dataset === id)
        .forEach((layer: Layer) => setVisibility({ layer }, visible));
    } else if (showable.layer) {
      let add = visible;
      layerStore.selectedLayers = layerStore.selectedLayers.map((layer) => {
        if (layer.id === showable.layer?.id) {
          layer.visible = visible;
          add = false;
        }
        return layer;
      });
      if (add) {
        layerStore.addLayer(showable.layer);
      }
    } else if (showable.network) {
      let network = showable.network;
      if (visible) {
        if (!network.nodes) {
          network = await getNetwork(network.id);
        }
        const networkPanel = panelArrangement.value.find(
          (panel) => panel.id === "networks",
        );
        if (networkPanel) {
          networkPanel.visible = true;
          networkPanel.collapsed = false;
        }
      }
      networkStore.currentNetwork = visible ? network : undefined;
      const dataset = projectStore.availableDatasets?.find(
        (d) => d.id === showable.network?.dataset,
      );
      return setVisibility({ dataset }, visible);
    } else if (showable.taskresult) {
      const taskType = analysisStore.availableAnalysisTypes?.find(
        (t) => t.db_value === showable.taskresult?.task_type,
      );
      if (taskType) {
        Object.entries(showable.taskresult.outputs).map(
          ([outputKey, outputValue]) => {
            const type = taskType.output_types[outputKey].toLowerCase();
            if (showableTypes.includes(type)) {
              setVisibility({ [type]: { id: outputValue } }, visible);
            }
          },
        );
        Object.entries(showable.taskresult.inputs).map(
          ([inputKey, inputValue]) => {
            const type = taskType.input_types[inputKey].toLowerCase();
            const value: Record<string, any> = taskType.input_options[
              inputKey
            ].find((o: any) => o.id === inputValue);
            if (showableTypes.includes(type)) {
              setVisibility({ [type]: value }, visible);
            }
          },
        );
      }
    } else if (showable.rasterdata && showable.rasterdata.dataset) {
      const dataset = await getDataset(showable.rasterdata.dataset);
      setVisibility({ dataset }, visible);
    } else if (showable.vectordata && showable.vectordata.dataset) {
      const dataset = await getDataset(showable.vectordata.dataset);
      setVisibility({ dataset }, visible);
    }
  }

  return {
    showableTypes,
    panelArrangement,
    draggingPanel,
    draggingFrom,
    dragModes,
    resetPanels,
    startDrag,
    dragPanel,
    stopDrag,
    isVisible,
    setVisibility,
  };
});
