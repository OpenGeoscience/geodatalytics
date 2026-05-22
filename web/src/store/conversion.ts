import type { TaskResult } from "@/types";
import { defineStore } from "pinia";
import { ref } from "vue";
import { useProjectStore } from "./project";

const url = `${import.meta.env.VITE_API_ROOT}ws/conversion/`;

export const useConversionStore = defineStore("conversion", () => {
  const projectStore = useProjectStore();
  const ws = ref();
  const datasetConversionTasks = ref<Record<number, TaskResult>>({});

  function createWebSocket() {
    if (!ws.value) {
      ws.value = new WebSocket(url);
      ws.value.onmessage = (event: any) => {
        const result = JSON.parse(JSON.parse(event.data)) as TaskResult;
        const datasetId = result.inputs.dataset_id;
        if (datasetId !== undefined) {
          datasetConversionTasks.value[datasetId] = result;
          if (result.completed) projectStore.fetchProjectDatasets();
        }
      };
    }
  }

  return {
    datasetConversionTasks,
    createWebSocket,
  };
});
