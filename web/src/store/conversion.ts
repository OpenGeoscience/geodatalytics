import type { TaskResult } from "@/types";
import { defineStore } from "pinia";
import { ref } from "vue";
import { useFramePreviewStore } from "./framePreview";
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
        // Default frame-preview generation during dataset conversion has no
        // project, so it arrives on this channel rather than analytics_*.
        if (result.task_type === "frame_preview" && result.completed) {
          useFramePreviewStore().onPreviewTaskComplete(result);
        }
        const datasetId = result.inputs?.dataset_id;
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
