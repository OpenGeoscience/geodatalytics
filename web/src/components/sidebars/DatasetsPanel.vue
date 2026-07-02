<script setup lang="ts">
import { computed } from "vue";
import DatasetList from "@/components/DatasetList.vue";
import DetailView from "@/components/DetailView.vue";
import type { Dataset, Layer } from "@/types";

import { useLayerStore, useConversionStore } from "@/store";
const layerStore = useLayerStore();
const conversionStore = useConversionStore();

const props = defineProps<{
  datasets: Dataset[] | undefined;
}>();

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

function toggleSelected(items: Layer[]) {
  items.forEach((item) => {
    const layer = item as Layer;
    layerStore.addLayer(layer);
  });
}
</script>

<template>
  <DatasetList :datasets="datasetsWithLayers">
    <template #list="{ data }">
      <v-expansion-panels
        multiple
        flat
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
              <div class="item-title" style="margin-left: 12px">
                <div>
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
                      class="mr-2"
                    />
                    <v-progress-circular
                      v-else
                      v-tooltip="
                        conversionStore.datasetConversionTasks[dataset.id]
                          .status
                      "
                      size="18"
                      class="mr-2"
                      indeterminate
                    />
                  </div>
                  {{ dataset.name }}
                </div>
                <div
                  v-if="dataset.layers"
                  style="min-width: 75px; text-align: right"
                >
                  <v-icon
                    v-tooltip="
                      dataset.n_layers +
                      ' layer' +
                      (dataset.n_layers > 1 ? 's' : '')
                    "
                    icon="mdi-layers-outline"
                    size="small"
                    class="ml-2"
                  ></v-icon>
                  <span class="secondary-text">{{ dataset.n_layers }}</span>
                  <v-icon
                    v-tooltip="dataset.description"
                    icon="mdi-information-outline"
                    size="small"
                    class="mx-1"
                  ></v-icon>
                </div>
              </div>
              <DetailView :details="{ ...dataset, type: 'dataset' }" />
            </div>
          </v-expansion-panel-title>
          <v-expansion-panel-text class="pb-2">
            <div>
              <v-chip
                v-for="tag in dataset.tags"
                :key="tag"
                :text="tag"
                variant="outlined"
                size="small"
                class="ml-3 mb-2"
              />
            </div>
            <div
              v-for="layer in dataset.layers"
              :key="layer.id"
              class="item-title"
            >
              <div
                style="
                  text-wrap: wrap;
                  align-items: center;
                  width: 90%;
                  cursor: pointer;
                "
                @click.stop="() => toggleSelected([layer])"
              >
                <span>
                  <v-icon
                    icon="mdi-plus"
                    size="small"
                    color="primary"
                    class="secondary-button"
                  >
                  </v-icon>
                  <v-tooltip activator="parent" location="bottom">
                    Add to Selected Layers
                  </v-tooltip>
                </span>
                {{ layer.name }}
              </div>
              <div class="pr-5">
                <DetailView :details="{ ...layer, type: 'layer' }" />
              </div>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </template>
  </DatasetList>
</template>
