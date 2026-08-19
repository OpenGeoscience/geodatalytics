import {
  createRegion,
  getProjectAnalysisTypes,
  getProjectCharts,
  getTaskResults,
} from "@/api/rest";
import type { Chart, AnalysisType, TaskResult } from "@/types";
import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { useProjectStore, useMapStore } from ".";
import { TerraDraw, TerraDrawPolygonMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";

export const useAnalysisStore = defineStore("analysis", () => {
  const projectStore = useProjectStore();
  const mapStore = useMapStore();

  const loadingCharts = ref<boolean>(false);
  const availableCharts = ref<Chart[]>();
  const currentChart = ref<Chart>();
  const currentAnalysisTab = ref<"old" | "new">("new");
  const loadingAnalysisTypes = ref<boolean>(false);
  const availableAnalysisTypes = ref<AnalysisType[]>();
  const currentAnalysisType = ref<AnalysisType>();
  const availableResults = ref<TaskResult[]>([]);
  const currentResult = ref<TaskResult>();
  const selectedInputs = ref<Record<string, any>>({});
  const terradraw = ref<TerraDraw | undefined>(undefined);
  const drawingRegion = ref<boolean>(false);
  const drawingRegionForInput = ref<undefined | string>();
  const drawnRegionCoords = ref<number[][][] | undefined>();
  const newRegionName = ref<string | undefined>();
  const ws = ref();

  async function initCharts(projectId: number) {
    loadingCharts.value = true;
    const charts = await getProjectCharts(projectId);
    availableCharts.value = charts;
    currentChart.value = undefined;
    loadingCharts.value = false;
  }

  async function initAnalysisTypes(projectId: number) {
    loadingAnalysisTypes.value = true;
    const types = await getProjectAnalysisTypes(projectId);
    availableAnalysisTypes.value = types;
    currentAnalysisType.value = undefined;
    loadingAnalysisTypes.value = false;
  }

  async function initResults(analysisType: string, projectId: number) {
    availableResults.value = await getTaskResults(analysisType, projectId);
  }

  function cancelDraw() {
    if (terradraw.value) {
      terradraw.value?.setMode("static");
      terradraw.value.clear();
    }
    drawingRegion.value = false;
    drawingRegionForInput.value = undefined;
    drawnRegionCoords.value = undefined;
    newRegionName.value = undefined;
  }

  function drawNewRegion(inputName: string) {
    drawingRegion.value = true;
    drawingRegionForInput.value = inputName;
    const map = mapStore.getMap();
    if (!terradraw.value) {
      terradraw.value = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map }),
        modes: [new TerraDrawPolygonMode()],
      });
      terradraw.value.on("finish", () => {
        terradraw.value?.setMode("static");
        const snapshot = terradraw.value?.getSnapshot();
        if (snapshot?.length) {
          drawnRegionCoords.value = snapshot[0].geometry
            .coordinates as number[][][];
        }
        // Only unset drawingRegion after click callbacks have completed
        setTimeout(() => (drawingRegion.value = false), 1);
      });
    }
    terradraw.value.start();
    // Ensure that terradraw layers are on top
    map.getStyle().layers.forEach((layer) => {
      if (layer.id.startsWith("td-")) {
        map.moveLayer(layer.id);
      }
    });
    terradraw.value.clear();
    terradraw.value.setMode("polygon");
  }

  function saveNewRegion() {
    if (
      !newRegionName.value ||
      !drawnRegionCoords.value ||
      !projectStore.currentProject
    )
      return;
    createRegion({
      name: newRegionName.value,
      project_id: projectStore.currentProject.id,
      boundary: [drawnRegionCoords.value],
      metadata: {
        source: "Drawn on map via UI",
      },
    }).then(async (region) => {
      if (!projectStore.currentProject || !drawingRegionForInput.value) return;
      availableAnalysisTypes.value = await getProjectAnalysisTypes(
        projectStore.currentProject.id,
      );
      const matchingAnalysisType = availableAnalysisTypes.value.find(
        (analysisType) =>
          analysisType.db_value === currentAnalysisType.value?.db_value,
      );
      if (currentAnalysisType.value && matchingAnalysisType)
        currentAnalysisType.value.input_options =
          matchingAnalysisType.input_options;
      selectedInputs.value[drawingRegionForInput.value] = region.id;
      drawingRegionForInput.value = undefined;
      newRegionName.value = undefined;
      drawnRegionCoords.value = undefined;
      terradraw.value?.clear();
    });
  }

  function createWebSocket() {
    if (ws.value) ws.value.close();
    if (projectStore.currentProject) {
      const urlBase = `${import.meta.env.VITE_API_ROOT}ws/`;
      const url = `${urlBase}analytics/project/${projectStore.currentProject.id}/results/`;
      ws.value = new WebSocket(url);
      ws.value.onmessage = (event: any) => {
        const data = JSON.parse(JSON.parse(event.data));
        if (currentResult.value && data.id === currentResult.value.id) {
          // only overwrite attributes expecting updates
          // overwriting the whole currentResult object will cause
          // the expansion panel to collapse
          currentResult.value.error = data.error;
          currentResult.value.outputs = data.outputs;
          currentResult.value.status = data.status;
          currentResult.value.completed = data.completed;
          currentResult.value.name = data.name;
          availableResults.value = availableResults.value.map((result) =>
            result.id === data.id ? data : result,
          );
        }
        if (data.completed && projectStore.currentProject) {
          // completed result object may become an input option
          // for another analysis type, refresh available types
          getProjectAnalysisTypes(projectStore.currentProject.id).then(
            (types) => {
              availableAnalysisTypes.value = types;
            },
          );
        }
      };
    }
  }

  watch(() => projectStore.currentProject, createWebSocket);

  return {
    loadingCharts,
    availableCharts,
    currentChart,
    currentAnalysisTab,
    loadingAnalysisTypes,
    availableAnalysisTypes,
    currentAnalysisType,
    availableResults,
    currentResult,
    selectedInputs,
    initCharts,
    initAnalysisTypes,
    initResults,
    drawingRegion,
    drawingRegionForInput,
    drawnRegionCoords,
    newRegionName,
    cancelDraw,
    drawNewRegion,
    saveNewRegion,
  };
});
