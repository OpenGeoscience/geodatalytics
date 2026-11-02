import type {
  FloatingPanelConfig,
  TaskResult,
  Chart,
  Dataset,
  Layer,
  Network,
  NetworkAnimation,
  RasterData,
  VectorData,
  Region,
} from "@/types";
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { getChart, getDataset, getNetwork } from "@/api/rest";

import {
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
  "network_animation",
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
  network_animation?: NetworkAnimation;
  rasterdata?: RasterData;
  vectordata?: VectorData;
  taskresult?: TaskResult;
  region?: Region;
}

const defaultPanelArrangement: FloatingPanelConfig[] = [
  {
    id: "datasets",
    label: "Datasets",
    visible: true,
    closeable: true,
    dock: "left",
  },
  {
    id: "layers",
    label: "Selected Layers",
    visible: true,
    closeable: true,
    dock: "left",
  },
  {
    id: "legend",
    label: "Legend",
    visible: true,
    closeable: true,
    collapsed: true,
    dock: "right",
  },
  {
    id: "charts",
    label: "Charts",
    visible: true,
    closeable: true,
    collapsed: true,
    dock: "right",
  },
  {
    id: "networks",
    label: "Networks",
    visible: true,
    closeable: true,
    collapsed: true,
    dock: "right",
  },
  {
    id: "analytics",
    label: "AI & Analytics",
    visible: true,
    closeable: true,
    collapsed: true,
    dock: "right",
  },
];

export const usePanelStore = defineStore("panel", () => {
  const analysisStore = useAnalysisStore();
  const layerStore = useLayerStore();
  const projectStore = useProjectStore();
  const mapStore = useMapStore();
  const networkStore = useNetworkStore();

  const leftPanels = ref<FloatingPanelConfig[]>([]);
  const rightPanels = ref<FloatingPanelConfig[]>([]);
  const floatingPanels = ref<FloatingPanelConfig[]>([]);
  const allPanels = computed<FloatingPanelConfig[]>(() => {
    return [
      ...leftPanels.value.map((p) => ({ ...p, dock: "left" })),
      ...rightPanels.value.map((p) => ({ ...p, dock: "right" })),
      ...floatingPanels.value.map((p) => ({ ...p, dock: undefined })),
    ] as FloatingPanelConfig[];
  });
  const dragPoint = ref<{ x: number; y: number }>();

  function resetPanels() {
    initPanelsFromArrangement(defaultPanelArrangement);
  }

  function initPanelsFromArrangement(arrangement: FloatingPanelConfig[]) {
    leftPanels.value = arrangement.filter((p) => p.dock === "left");
    rightPanels.value = arrangement.filter((p) => p.dock === "right");
    const floatingArea = document
      .getElementById("floating-panel-set")
      ?.getBoundingClientRect();
    floatingPanels.value = arrangement
      .filter((p) => p.dock === undefined)
      .map((p) => {
        // apply position and dimension proportions
        if (p.position && floatingArea) {
          // floating panel positions are relative to floating area
          p.position = {
            x: p.position.x * window.innerWidth - floatingArea.left,
            y: p.position.y * window.innerHeight - floatingArea.top,
          };
        }
        if (p.width) p.width *= window.innerWidth;
        if (p.height) p.height *= window.innerHeight;
        return p;
      });
  }

  function getCurrentPanelArrangement() {
    return allPanels.value.map((p) => {
      if (p.dock === undefined) {
        const rect = p.element?.getBoundingClientRect();
        if (rect) {
          // use proportions instead of coordinates
          // so that bookmarks look good with other window sizes
          const position = {
            x: rect.x / window.innerWidth,
            y: rect.y / window.innerHeight,
          };
          const width = rect.width / window.innerWidth;
          const height = rect.height / window.innerHeight;
          return { ...p, position, width, height };
        }
      }
      return p;
    });
  }

  function getPanel(panelId: string) {
    return allPanels.value.find((p) => p.id === panelId);
  }

  function updatePanel(panel: any) {
    const panelLists = [
      leftPanels.value,
      rightPanels.value,
      floatingPanels.value,
    ];
    panelLists.forEach((panelList) => {
      panelList.forEach((p) => {
        if (p.id === panel.id) {
          Object.assign(p, panel);
        }
      });
    });
  }

  function dragEnd(e: any) {
    if (dragPoint.value && e.to?.id === "floating-panel-set") {
      const panel = floatingPanels.value[e.newIndex];
      panel.position = {
        x: e.originalEvent.offsetX - dragPoint.value.x,
        y: e.originalEvent.offsetY - dragPoint.value.y,
      };
      updatePanel(panel);
    }
    dragPoint.value = undefined;
  }

  function dragFloating(x: number, y: number, panelId: string) {
    const floatingArea = document
      .getElementById("floating-panel-set")
      ?.getBoundingClientRect();
    const panel = getPanel(panelId);
    if (floatingArea && panel && dragPoint.value) {
      const width = floatingArea.width;
      const dockMargin = 20;
      x += dragPoint.value.x;
      if (x + dockMargin < 0) {
        const panelsAbove = leftPanels.value.filter((p) => {
          const box = p.element?.getBoundingClientRect();
          return box && box.bottom < y;
        });
        leftPanels.value.splice(panelsAbove.length, 0, panel);
        floatingPanels.value = floatingPanels.value.filter(
          (p) => p.id !== panelId,
        );
      }
      if (x - dockMargin > width) {
        const panelsAbove = rightPanels.value.filter((p) => {
          const box = p.element?.getBoundingClientRect();
          return box && box.bottom < y;
        });
        rightPanels.value.splice(panelsAbove.length, 0, panel);
        floatingPanels.value = floatingPanels.value.filter(
          (p) => p.id !== panelId,
        );
      }
    }
  }

  function isVisible(showable: Showable, nested: boolean = true): boolean {
    if (showable.region) {
      return mapStore.regionShownId === showable.region.id;
    } else if (showable.chart) {
      const chartPanel = getPanel("charts");
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
    } else if (showable.network_animation) {
      return (
        networkStore.currentAnimation?.id === showable.network_animation.id
      );
    } else if (showable.taskresult) {
      const taskType = analysisStore.availableAnalysisTypes?.find(
        (t) => t.db_value === showable.taskresult?.task_type,
      );
      if (taskType) {
        if (nested) {
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
        } else {
          return (
            analysisStore.currentAnalysisTab === "old" &&
            analysisStore.currentAnalysisType?.db_value ===
              showable.taskresult.task_type &&
            analysisStore.currentResult?.id === showable.taskresult.id
          );
        }
      }
    } else if (showable.rasterdata) {
      return isVisible({ dataset: { id: showable.rasterdata.dataset } });
    } else if (showable.vectordata) {
      return isVisible({ dataset: { id: showable.vectordata.dataset } });
    }
    return false;
  }

  async function setVisibility(
    showable: Showable,
    visible: boolean,
    frame: number | undefined = undefined,
    nested: boolean = true,
  ) {
    if (showable.region) {
      mapStore.showRegion(visible ? showable.region : undefined);
    } else if (showable.chart) {
      let chart = showable.chart;
      if (visible) {
        if (!chart.chart_data) {
          chart = await getChart(chart.id);
        }
        updatePanel({
          id: "charts",
          visible: true,
          collapsed: false,
        });
      }
      analysisStore.currentChart = visible ? chart : undefined;
    } else if (showable.dataset) {
      const id = showable.dataset.id;
      if (visible) await layerStore.fetchAvailableLayersForDataset(id);
      if (nested) {
        const layersList = visible
          ? layerStore.availableLayers
          : layerStore.selectedLayers;
        layersList
          .filter((layer: Layer) => layer.dataset === id)
          .forEach((layer: Layer) => setVisibility({ layer }, visible, frame));
      }
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
        await layerStore.addLayer(showable.layer, undefined, frame);
      }
    } else if (showable.network) {
      if (visible && networkStore.currentNetwork?.id !== showable.network.id) {
        let network = showable.network;
        if (!network.nodes) {
          network = await getNetwork(network.id);
        }
        updatePanel({
          id: "networks",
          visible: true,
          collapsed: false,
        });
      }
      if (nested) {
        const dataset = projectStore.availableDatasets?.find(
          (d) => d.id === showable.network?.dataset,
        );
        return setVisibility({ dataset }, visible, frame);
      }
    } else if (showable.network_animation) {
      if (nested) {
        const network = await getNetwork(showable.network_animation.network);
        await setVisibility({ network }, visible);
      }
      await networkStore.fetchAnimations();
      networkStore.currentAnimation = visible
        ? networkStore.availableAnimations.find(
            (anim) => anim.id === showable.network_animation?.id,
          )
        : undefined;
    } else if (showable.taskresult) {
      const taskType = analysisStore.availableAnalysisTypes?.find(
        (t) => t.db_value === showable.taskresult?.task_type,
      );
      if (nested) {
        if (taskType && showable.taskresult.outputs) {
          Object.entries(showable.taskresult.outputs).map(
            ([outputKey, outputValue]) => {
              const type = taskType.output_types[outputKey].toLowerCase();
              if (showableTypes.includes(type)) {
                setVisibility({ [type]: { id: outputValue } }, visible, frame);
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
                setVisibility({ [type]: value }, visible, frame);
              }
            },
          );
        }
      } else {
        if (visible) {
          updatePanel({
            id: "analytics",
            visible: true,
            collapsed: false,
          });
          analysisStore.currentAnalysisTab = "old";
          analysisStore.currentAnalysisType = taskType;
          await analysisStore.fetchResults();
          analysisStore.currentResult = analysisStore.availableResults.find(
            (result) => result.id === showable.taskresult?.id,
          );
        } else {
          analysisStore.currentResult = undefined;
        }
      }
    } else if (showable.rasterdata && showable.rasterdata.dataset && nested) {
      const dataset = await getDataset(showable.rasterdata.dataset);
      setVisibility({ dataset }, visible, frame);
    } else if (showable.vectordata && showable.vectordata.dataset && nested) {
      const dataset = await getDataset(showable.vectordata.dataset);
      setVisibility({ dataset }, visible, frame);
    }
  }

  return {
    showableTypes,
    leftPanels,
    rightPanels,
    floatingPanels,
    allPanels,
    resetPanels,
    initPanelsFromArrangement,
    getCurrentPanelArrangement,
    getPanel,
    updatePanel,
    dragPoint,
    dragEnd,
    dragFloating,
    isVisible,
    setVisibility,
  };
});
