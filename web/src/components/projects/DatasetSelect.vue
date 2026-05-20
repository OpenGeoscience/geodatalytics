<script setup lang="ts">
import { computed, ref } from "vue";
import DatasetList from "@/components/DatasetList.vue";
import DetailView from "@/components/DetailView.vue";
import type { Dataset } from "@/types";
import { deleteDataset } from "@/api/rest";

import {
  useLayerStore,
  useConversionStore,
  useAppStore,
  useProjectStore,
} from "@/store";
const layerStore = useLayerStore();
const conversionStore = useConversionStore();
const appStore = useAppStore();
const projectStore = useProjectStore();

const props = defineProps<{
  datasets: Dataset[] | undefined;
  savingId: number | undefined;
  addedIds?: number[] | undefined;
  buttonIcon: string;
  showDelete: boolean;
}>();
const emit = defineEmits(["buttonClick", "onDelete"]);
const datasetToDelete = ref<Dataset>();

const datasetsWithLayers = computed(() => {
  return props.datasets?.map((dataset) => {
    return {
      ...dataset,
      layers: layerStore.availableLayers.filter(
        (l) => l.dataset === dataset.id,
      ),
    };
  });
});

function expandDataset(expanded: any) {
  expanded.forEach((datasetId: number) => {
    if (!layerStore.availableLayers.some((l) => l.dataset === datasetId)) {
      layerStore.fetchAvailableLayersForDataset(datasetId);
    }
  });
}

function getDatasetProjects(datasetId: number) {
  return projectStore.availableProjects.filter((p) =>
    p.datasets.includes(datasetId),
  );
}

function submitDelete() {
  if (datasetToDelete.value) {
    deleteDataset(datasetToDelete.value.id).then(() => {
      datasetToDelete.value = undefined;
      projectStore.refreshAllDatasets();
      projectStore.fetchProjectDatasets();
      emit("onDelete");
    });
  }
}
</script>

<template>
  <DatasetList :datasets="datasetsWithLayers">
    <template v-slot:list="{ data }">
      <v-expansion-panels
        multiple
        variant="accordion"
        elevation="0"
        bg-color="transparent"
        @update:model-value="expandDataset"
      >
        <v-expansion-panel
          v-for="dataset in data"
          :key="dataset.id"
          :value="dataset.id"
        >
          <v-expansion-panel-title>
            <div
              style="display: flex; justify-content: space-between; width: 100%"
            >
              <div class="d-flex">
                <div style="min-width: 24px">
                  <v-icon
                    v-if="
                      showDelete &&
                      dataset.owner &&
                      dataset.owner.id === appStore.currentUser?.id
                    "
                    icon="mdi-delete-outline"
                    color="error"
                    @click.stop="datasetToDelete = dataset"
                  />
                </div>
                <div class="mr-2">
                  <div
                    v-if="
                      conversionStore.datasetConversionTasks[dataset.id] &&
                      !conversionStore.datasetConversionTasks[dataset.id]
                        .completed
                    "
                    style="display: inline-block"
                  >
                    <v-icon
                      v-if="
                        conversionStore.datasetConversionTasks[dataset.id].error
                      "
                      v-tooltip="
                        conversionStore.datasetConversionTasks[dataset.id].error
                      "
                      icon="mdi-alert-outline"
                      color="error"
                    />
                    <v-progress-circular
                      v-else
                      v-tooltip="
                        conversionStore.datasetConversionTasks[dataset.id]
                          .status
                      "
                      size="24"
                      indeterminate
                    />
                  </div>
                  <v-progress-circular
                    v-else-if="props.savingId === dataset.id"
                    size="24"
                    indeterminate
                  />
                  <v-icon
                    v-else-if="
                      !props.addedIds || !props.addedIds.includes(dataset.id)
                    "
                    :icon="props.buttonIcon"
                    color="primary"
                    class="icon-button"
                    @click.stop="emit('buttonClick', dataset)"
                  />
                  <v-icon v-else icon="mdi-check" color="success" @click.stop />
                </div>
                {{ dataset.name }}
              </div>
              <div
                v-if="dataset.layers"
                style="min-width: 75px; text-align: right"
              >
                <v-icon
                  icon="mdi-layers"
                  size="small"
                  v-tooltip="dataset.n_layers + ' layers'"
                  class="ml-2"
                ></v-icon>
                <span class="secondary-text">{{ dataset.n_layers }}</span>
                <v-icon
                  icon="mdi-information-outline"
                  size="small"
                  v-tooltip="dataset.description"
                  class="mx-1"
                ></v-icon>
                <DetailView
                  v-if="dataset"
                  :details="{ ...dataset, type: 'dataset' }"
                />
              </div>
            </div>
          </v-expansion-panel-title>
          <v-expansion-panel-text class="pb-2">
            <div class="mb-2 ml-2">
              <v-chip
                v-for="tag in dataset.tags"
                :key="tag"
                :text="tag"
                variant="outlined"
                size="small"
              />
            </div>
            <div
              v-for="layer in dataset.layers"
              :key="layer.id"
              class="item-title"
            >
              <div style="text-wrap: wrap; align-items: center; width: 100%">
                {{ layer.name }}
              </div>
              <div class="pr-5">
                <DetailView :details="{ ...layer, type: 'layer' }" />
              </div>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>

      <v-dialog :model-value="!!datasetToDelete" width="500">
        <v-card v-if="datasetToDelete">
          <v-card-title class="pa-3">
            Delete dataset
            <v-btn
              class="close-button transparent"
              variant="flat"
              icon
              @click="datasetToDelete = undefined"
            >
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </v-card-title>
          <v-card-text
            class="d-flex"
            style="flex-direction: column; row-gap: 5px"
          >
            <div>
              Are you sure you want to delete "{{ datasetToDelete.name }}"?
            </div>
            <div>This Dataset will be removed from the following projects:</div>
            <div>
              <v-chip
                v-for="project in getDatasetProjects(datasetToDelete.id)"
                :key="project.id"
                :text="project.name"
              />
            </div>
          </v-card-text>
          <v-card-actions style="text-align: right">
            <v-btn color="red" @click="submitDelete"> Delete </v-btn>
            <v-btn
              color="primary"
              @click="datasetToDelete = undefined"
              variant="tonal"
            >
              Cancel
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </template>
  </DatasetList>
</template>

<style>
.icon-button {
  background-color: rgb(var(--v-theme-secondary));
  border-radius: 4px;
}
</style>
