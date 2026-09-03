<script setup lang="ts">
import { ref, watch, computed } from "vue";
import {
  runAnalysis,
  getDataset,
  getChart,
  getTaskResult,
  getNetwork,
  getRegion,
  subscribeToTaskResult,
} from "@/api/rest";
import VueMarkdown from "vue-markdown-render";
import NodeAnimation from "./NodeAnimation.vue";
import SliderNumericInput from "../SliderNumericInput.vue";

import {
  useLayerStore,
  useNetworkStore,
  usePanelStore,
  useAnalysisStore,
  useProjectStore,
  useAppStore,
  useMapStore,
} from "@/store";

const panelStore = usePanelStore();
const analysisStore = useAnalysisStore();
const projectStore = useProjectStore();
const networkStore = useNetworkStore();
const layerStore = useLayerStore();
const appStore = useAppStore();
const mapStore = useMapStore();

const searchText = ref<string | undefined>();
const filteredAnalysisTypes = computed(() => {
  return analysisStore.availableAnalysisTypes?.filter((analysis_type) => {
    return (
      !searchText.value ||
      analysis_type.name.toLowerCase().includes(searchText.value.toLowerCase())
    );
  });
});
const newestFirstResults = computed(() => {
  return analysisStore.availableResults.toSorted((a, b) => {
    const aCreated = new Date(a.created);
    const bCreated = new Date(b.created);
    return bCreated.getTime() - aCreated.getTime();
  });
});
const fullInputs = ref<Record<string, any>>();
const fullOutputs = ref<Record<string, any>>();
const networkInput = computed(() => {
  if (!fullInputs.value) return undefined;
  let network = undefined;
  if (fullInputs.value["network_failure"]) {
    const analysis = fullInputs.value["network_failure"];
    const networkId = analysis.inputs.network;
    network = networkStore.availableNetworks.find((n) => n.id === networkId);
    if (!network) {
      const analysisType = analysisStore.availableAnalysisTypes?.find(
        (t) => t.db_value === analysis.task_type,
      );
      network = analysisType?.input_options.network.find(
        (o: any) => o.id === networkId,
      );
    }
    const visible = panelStore.isVisible({ network });
    network = {
      ...network,
      visible,
    };
  } else {
    network = Object.values(fullInputs.value).find(
      (input) => input.type === "network",
    );
  }
  return network;
});
const additionalAnimationLayers = ref();
const inputForm = ref();
const runAllowed = computed(() => {
  if (!projectStore.currentProject || !appStore.authenticated) return false;
  return ["owner", "collaborator"].includes(
    projectStore.permissions[projectStore.currentProject.id],
  );
});

function getInputSelectionRules(key: string) {
  return [
    (v: any) => {
      const options = analysisStore.currentAnalysisType?.input_options[key];
      return v
        ? !options.length || options.map((opt: any) => opt.id).includes(v)
          ? true
          : "Must select from options"
        : analysisStore.currentAnalysisType?.optional_inputs?.includes(key)
          ? true
          : "Input required.";
    },
  ];
}

function getInputOptionalLabel(key: string) {
  return analysisStore.currentAnalysisType?.optional_inputs?.includes(key)
    ? " (optional)"
    : "";
}

function run() {
  if (!runAllowed.value) return;
  inputForm.value.validate().then(({ valid }: { valid: boolean }) => {
    if (
      valid &&
      projectStore.currentProject &&
      analysisStore.currentAnalysisType
    ) {
      runAnalysis(
        analysisStore.currentAnalysisType.db_value,
        projectStore.currentProject.id,
        analysisStore.selectedInputs,
      ).then((result) => {
        analysisStore.currentAnalysisTab = "old";
        analysisStore.currentResult = result;
        analysisStore.fetchResults();
      });
    }
  });
}

function inputOptionHover(type: string, option: any) {
  if (type.toLocaleLowerCase() === "region") {
    mapStore.showRegion(option);
  }
}

async function getFullObject(type: string, value: any) {
  if (type !== "number" && typeof value === "number") {
    value = { id: value };
  }
  if (type == "dataset") {
    value = await getDataset(value.id);
  }
  if (type == "chart") {
    value = await getChart(value.id);
  }
  if (type == "network") {
    value = await getNetwork(value.id);
  }
  if (type == "taskresult") {
    value = await getTaskResult(value.id);
  }
  if (type == "region") {
    value = await getRegion(value.id);
  }
  if (typeof value === "object") {
    value.type = type;
    value.visible = panelStore.isVisible({ [type]: value });
    value.showable = panelStore.showableTypes.includes(value.type);
  } else {
    value = {
      name: value,
      type: type,
    };
  }
  return value;
}

async function fillInputsAndOutputs() {
  if (!analysisStore.currentResult?.inputs) {
    fullInputs.value = undefined;
    additionalAnimationLayers.value = undefined;
  } else {
    fullInputs.value = Object.fromEntries(
      await Promise.all(
        Object.entries(analysisStore.currentResult.inputs).map(
          async ([key, value]) => {
            const fullValue = analysisStore.currentAnalysisType?.input_options[
              key
            ]?.find((o: any) => o.id == value);
            const type = key.endsWith("_frame")
              ? "number"
              : analysisStore.currentAnalysisType?.input_types[
                  key
                ].toLowerCase();
            return [key, await getFullObject(type, fullValue || value)];
          },
        ),
      ),
    );
    if (
      fullInputs.value?.flood_simulation &&
      !additionalAnimationLayers.value
    ) {
      const floodDataset = {
        id: fullInputs.value?.flood_simulation.outputs.flood as number,
      };
      if (panelStore.isVisible({ dataset: floodDataset })) {
        layerStore
          .fetchAvailableLayersForDataset(floodDataset.id)
          .then((layers) => {
            additionalAnimationLayers.value = layers;
          });
      }
    }
  }
  if (!analysisStore.currentResult?.outputs) fullOutputs.value = undefined;
  else {
    fullOutputs.value = Object.fromEntries(
      await Promise.all(
        Object.entries(analysisStore.currentResult.outputs).map(
          async ([key, value]) => {
            const type =
              analysisStore.currentAnalysisType?.output_types[
                key
              ].toLowerCase();
            return [key, await getFullObject(type, value)];
          },
        ),
      ),
    );
  }
}

async function subscribe() {
  if (appStore.authenticated && analysisStore.currentResult) {
    analysisStore.currentResult.subscribers = (
      await subscribeToTaskResult(analysisStore.currentResult.id)
    ).subscribers;
  }
}

watch(networkInput, (network) => {
  if (
    network &&
    !networkStore.availableNetworks.map((n) => n.id).includes(network.id)
  ) {
    networkStore.availableNetworks = [
      ...networkStore.availableNetworks,
      network,
    ];
  }
});

watch(
  () => analysisStore.currentAnalysisTab,
  () => {
    if (analysisStore.currentAnalysisTab === "old") {
      analysisStore.fetchResults();
    }
  },
);

watch(
  [
    () => analysisStore.currentResult,
    () => layerStore.selectedLayers,
    () => analysisStore.currentChart,
    () => mapStore.regionShownId,
  ],
  fillInputsAndOutputs,
  { deep: true },
);
</script>

<template>
  <div
    :class="
      analysisStore.currentAnalysisType
        ? 'panel-content-outer'
        : 'panel-content-outer with-search'
    "
  >
    <v-text-field
      v-if="!analysisStore.currentAnalysisType"
      v-model="searchText"
      label="Search Analytics"
      variant="outlined"
      density="compact"
      class="mb-2"
      append-inner-icon="mdi-magnify"
      hide-details
    />
    <v-card class="panel-content-inner">
      <div
        v-if="analysisStore.currentAnalysisType"
        style="height: 100%; overflow: auto"
      >
        <v-card-title class="analysis-title">
          <span>{{ analysisStore.currentAnalysisType.name }}</span>
          <v-tooltip text="Close" location="bottom">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                icon="mdi-close"
                variant="plain"
                @click="analysisStore.currentAnalysisType = undefined"
              />
            </template>
          </v-tooltip>
        </v-card-title>
        <v-expansion-panels v-if="analysisStore.currentAnalysisType.details">
          <v-expansion-panel bg-color="transparent">
            <v-expansion-panel-title class="py-3" style="min-height: 0"
              >Details</v-expansion-panel-title
            >
            <v-expansion-panel-text class="px-3">
              {{ analysisStore.currentAnalysisType.details }}
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>

        <v-tabs
          v-if="runAllowed"
          v-model="analysisStore.currentAnalysisTab"
          align-tabs="center"
          fixed-tabs
        >
          <v-tab value="new">Run New</v-tab>
          <v-tab value="old">View Existing</v-tab>
        </v-tabs>

        <v-window v-model="analysisStore.currentAnalysisTab">
          <v-window-item v-if="runAllowed" value="new">
            <v-form ref="inputForm" class="pa-3" @submit.prevent>
              <v-card-subtitle class="px-1">Select inputs</v-card-subtitle>
              <div
                v-for="[key, value] in Object.entries(
                  analysisStore.currentAnalysisType.input_options,
                )"
                :key="key"
              >
                <div v-if="analysisStore.inputIsNumeric(key)">
                  {{ key.replaceAll("_", " ") }}
                  {{ getInputOptionalLabel(key) }}
                  <div class="px-2 mb-2">
                    <SliderNumericInput
                      :model="analysisStore.selectedInputs[key]"
                      :min="
                        analysisStore.currentAnalysisType.input_options[key][0]
                          .min
                      "
                      :max="
                        analysisStore.currentAnalysisType.input_options[key][0]
                          .max
                      "
                      :step="
                        analysisStore.currentAnalysisType.input_options[key][0]
                          .step
                      "
                      @update="
                        (v: number) => (analysisStore.selectedInputs[key] = v)
                      "
                    />
                  </div>
                </div>
                <v-text-field
                  v-else-if="
                    analysisStore.currentAnalysisType.input_types[key] ===
                      'string' &&
                    !analysisStore.currentAnalysisType.input_options[key].length
                  "
                  v-model="analysisStore.selectedInputs[key]"
                  :label="key.replaceAll('_', ' ') + getInputOptionalLabel(key)"
                  :rules="getInputSelectionRules(key)"
                  density="compact"
                  hide-details="auto"
                  class="my-1"
                />
                <v-combobox
                  v-else-if="value"
                  :model-value="analysisStore.selectedInputs[key]"
                  :label="key.replaceAll('_', ' ') + getInputOptionalLabel(key)"
                  :items="value"
                  :rules="getInputSelectionRules(key)"
                  :clearable="
                    analysisStore.currentAnalysisType.optional_inputs?.includes(
                      key,
                    )
                  "
                  item-value="id"
                  item-title="name"
                  density="compact"
                  hide-details="auto"
                  class="my-1"
                  @update:model-value="
                    (v) => (analysisStore.selectedInputs[key] = v?.id)
                  "
                >
                  <template #item="{ props, item }">
                    <v-list-item
                      v-tooltip="`${(item as any).name}`"
                      v-bind="props"
                      style="max-width: 400px"
                      @mouseover="
                        inputOptionHover(
                          analysisStore.currentAnalysisType.input_types[key],
                          item,
                        )
                      "
                      @mouseleave="
                        inputOptionHover(
                          analysisStore.currentAnalysisType.input_types[key],
                          undefined,
                        )
                      "
                    />
                  </template>
                  <template #append>
                    <div
                      v-if="
                        analysisStore.currentAnalysisType.input_types[key] ===
                        'Region'
                      "
                    >
                      <v-icon
                        v-if="
                          analysisStore.drawingRegion ||
                          analysisStore.drawnRegionCoords
                        "
                        v-tooltip="'Cancel Draw'"
                        icon="mdi-close"
                        @click="analysisStore.cancelDraw()"
                      />
                      <v-icon
                        v-else
                        v-tooltip="'Draw New Region'"
                        icon="mdi-shape-polygon-plus"
                        @click="analysisStore.drawNewRegion(key)"
                      />
                    </div>
                  </template>
                </v-combobox>
                <div
                  v-if="
                    analysisStore.currentAnalysisType.input_types[key] ===
                    'RasterData'
                  "
                >
                  <div
                    v-for="selectedValue in analysisStore.currentAnalysisType.input_options[
                      key
                    ].filter(
                      (option: any) =>
                        option.id === analysisStore.selectedInputs[key],
                    )"
                    :key="selectedValue.id"
                  >
                    <div v-if="selectedValue.metadata?.frames?.length">
                      {{ key }} frame
                      <SliderNumericInput
                        :model="
                          analysisStore.selectedInputs[`${key}_frame`] || 0
                        "
                        :min="0"
                        :max="selectedValue.metadata.frames.length - 1"
                        :step="1"
                        @update="
                          (v) =>
                            (analysisStore.selectedInputs[`${key}_frame`] = v)
                        "
                      />
                    </div>
                  </div>
                </div>
                <div
                  v-if="
                    analysisStore.currentAnalysisType.input_types[key] ===
                    'Region'
                  "
                >
                  <span
                    v-if="
                      analysisStore.drawingRegion &&
                      analysisStore.drawingRegionForInput === key
                    "
                    >Click anywhere on the map to place points and draw a closed
                    polygon.</span
                  >
                  <div
                    v-else-if="analysisStore.drawnRegionCoords"
                    class="d-flex"
                  >
                    <v-text-field
                      v-model="analysisStore.newRegionName"
                      label="Region Name"
                      density="compact"
                      autofocus
                      @keydown.enter="analysisStore.saveNewRegion"
                    />
                    <v-btn
                      color="primary"
                      variant="flat"
                      style="min-width: 40px; min-height: 40px"
                      :disabled="!analysisStore.newRegionName"
                      @click="analysisStore.saveNewRegion"
                    >
                      <v-icon icon="mdi-arrow-right" />
                    </v-btn>
                  </div>
                </div>
              </div>
              <v-btn style="width: 100%" variant="tonal" @click="run">
                Run Analysis
              </v-btn>
            </v-form>
          </v-window-item>
          <v-window-item value="old">
            <div
              v-if="
                analysisStore.availableResults &&
                analysisStore.availableResults.length === 0
              "
              style="width: 100%; text-align: center"
              class="pa-3"
            >
              No previous runs of this analysis type exist.
            </div>
            <v-expansion-panels
              v-else
              v-model="analysisStore.currentResult"
              variant="accordion"
            >
              <v-expansion-panel
                v-for="result in newestFirstResults"
                :key="result.id"
                :value="result"
                :title="result.name"
                bg-color="background"
              >
                <v-expansion-panel-text class="px-3 pb-5">
                  <v-card-subtitle>Inputs</v-card-subtitle>
                  <v-table class="bg-transparent">
                    <tbody v-if="fullInputs" style="width: 100%">
                      <tr
                        v-for="[key, value] in Object.entries(fullInputs)"
                        :key="key"
                      >
                        <td>{{ key.replaceAll("_", " ") }}</td>
                        <td v-if="value">
                          {{ value.name || value }}
                          <v-btn
                            v-if="value.showable"
                            density="compact"
                            color="primary"
                            @click="
                              () =>
                                panelStore.setVisibility(
                                  { [value.type]: value },
                                  !value.visible,
                                  fullInputs
                                    ? fullInputs[`${key}_frame`]?.name
                                    : undefined,
                                )
                            "
                          >
                            {{ value.visible ? "Hide" : "Show" }}
                          </v-btn>
                        </td>
                      </tr>
                    </tbody>
                  </v-table>
                  <div v-if="result.error" class="pa-2">
                    <span style="color: rgb(var(--v-theme-error))"
                      >Error:
                    </span>
                    {{ result.error }}
                  </div>
                  <div
                    v-else
                    class="pa-3"
                    style="width: 100%; text-align: center"
                  >
                    <v-progress-linear
                      v-if="!result.completed"
                      class="my-3 py-1"
                      indeterminate
                    />
                    {{ result.status }}
                  </div>
                  <div v-if="fullOutputs">
                    <v-card-subtitle>Outputs</v-card-subtitle>
                    <v-table class="bg-transparent">
                      <tbody>
                        <tr
                          v-for="[key, value] in Object.entries(fullOutputs)"
                          :key="key"
                        >
                          <template v-if="value?.type == 'network_animation'">
                            <td colspan="2">
                              <div v-if="value?.length === 0">
                                No nodes are affected in this scenario.
                              </div>
                              <node-animation
                                v-else-if="networkInput?.visible"
                                :node-failures="
                                  key === 'failures' ? value : undefined
                                "
                                :node-recoveries="
                                  key === 'recoveries' ? value : undefined
                                "
                                :network="networkInput"
                                :additional-animation-layers="
                                  additionalAnimationLayers
                                "
                              />
                              <div v-else>Show network to view animation.</div>
                            </td>
                          </template>
                          <template v-else-if="value?.type == 'markdown'">
                            <td colspan="2">
                              <vue-markdown :source="value?.name" />
                            </td>
                          </template>
                          <template v-else>
                            <td>{{ key.replaceAll("_", " ") }}</td>
                            <td>
                              {{ value?.name }}
                              <v-btn
                                v-if="value && value.showable"
                                color="primary"
                                density="compact"
                                style="display: block"
                                @click="
                                  () =>
                                    panelStore.setVisibility(
                                      { [value.type]: value },
                                      !value.visible,
                                      fullOutputs
                                        ? fullOutputs[`${key}_frame`]?.name
                                        : undefined,
                                    )
                                "
                              >
                                {{ value.visible ? "Hide" : "Show" }}
                              </v-btn>
                            </td>
                          </template>
                        </tr>
                      </tbody>
                    </v-table>
                  </div>
                  <div
                    v-else-if="appStore.authenticated"
                    style="text-align: center"
                  >
                    <div
                      v-if="
                        appStore.currentUser?.id &&
                        analysisStore.currentResult?.subscribers.includes(
                          appStore.currentUser.id,
                        )
                      "
                    >
                      <v-icon icon="mdi-check" color="success" />
                      Subscribed
                      <v-icon
                        v-tooltip="
                          'An email will be sent to you when the task is completed.'
                        "
                        icon="mdi-information-outline"
                      />
                    </div>
                    <v-btn
                      v-else
                      v-tooltip="
                        'If subscribed, an email will be sent to you when the task is completed.'
                      "
                      @click="subscribe"
                    >
                      Notify Me Once Completed
                    </v-btn>
                  </div>
                </v-expansion-panel-text>
              </v-expansion-panel>
            </v-expansion-panels>
          </v-window-item>
        </v-window>
      </div>
      <v-list v-else-if="filteredAnalysisTypes?.length" density="compact">
        <v-list-item
          v-for="simType in filteredAnalysisTypes"
          :key="simType.db_value"
          @click="analysisStore.currentAnalysisType = simType"
        >
          {{ simType.name }}
          <template #append>
            <v-icon
              v-tooltip="simType.description"
              icon="mdi-information-outline"
              size="small"
            ></v-icon>
          </template>
        </v-list-item>
      </v-list>
      <v-progress-linear
        v-else-if="analysisStore.loadingAnalysisTypes"
        indeterminate
      ></v-progress-linear>
      <v-card-text v-else class="help-text"
        >No available Analytics.</v-card-text
      >
    </v-card>
  </div>
</template>

<style scoped>
.analysis-title {
  display: flex;
  width: 100%;
  justify-content: space-between;
  align-items: center;
}
.analysis-title > span:first-child {
  flex-shrink: 1;
  min-width: 100px;
  overflow-x: hidden;
  text-overflow: ellipsis;
}
</style>
