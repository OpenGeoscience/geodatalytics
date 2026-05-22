import {
  getProjectAnalysisTypes,
  getProjectCharts,
  getTaskResults,
} from "@/api/rest";
import type { Chart, AnalysisType, TaskResult } from "@/types";
import { defineStore } from "pinia";
import { ref, watch } from "vue";
import { useProjectStore } from "./project";

export const useAnalysisStore = defineStore("analysis", () => {
  const projectStore = useProjectStore();

  const loadingCharts = ref<boolean>(false);
  const availableCharts = ref<Chart[]>();
  const currentChart = ref<Chart>();
  const currentAnalysisTab = ref<"old" | "new">("new");
  const loadingAnalysisTypes = ref<boolean>(false);
  const availableAnalysisTypes = ref<AnalysisType[]>();
  const currentAnalysisType = ref<AnalysisType>();
  const availableResults = ref<TaskResult[]>([]);
  const currentResult = ref<TaskResult>();
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
    initCharts,
    initAnalysisTypes,
    initResults,
  };
});
