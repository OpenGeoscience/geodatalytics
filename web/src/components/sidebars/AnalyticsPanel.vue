<script setup lang="ts">
import { ref, watch, computed } from "vue";
import {
  runAnalysis,
  getDataset,
  getChart,
  getTaskResult,
  getNetwork,
  subscribeToTaskResult,
} from "@/api/rest";
import NodeAnimation from "./NodeAnimation.vue";
import SliderNumericInput from "../SliderNumericInput.vue";

import {
  useLayerStore,
  useNetworkStore,
  usePanelStore,
  useAnalysisStore,
  useProjectStore,
  useAppStore,
} from "@/store";

const panelStore = usePanelStore();
const analysisStore = useAnalysisStore();
const projectStore = useProjectStore();
const networkStore = useNetworkStore();
const layerStore = useLayerStore();
const appStore = useAppStore();

const searchText = ref<string | undefined>();
const filteredAnalysisTypes = computed(() => {
  return analysisStore.availableAnalysisTypes?.filter((analysis_type) => {
    return !searchText.value ||
      analysis_type.name.toLowerCase().includes(searchText.value.toLowerCase())
  })
})
const newestFirstResults = computed(() => {
  return analysisStore.availableResults.toSorted((a, b) => {
    const aCreated = new Date(a.created);
    const bCreated = new Date(b.created);
    return bCreated.getTime() - aCreated.getTime();
  })
})
const fullInputs = ref<Record<string, any>>();
const fullOutputs = ref<Record<string, any>>();
const networkInput = computed(() => {
  if (!fullInputs.value) return undefined;
  let network = undefined;
  if (fullInputs.value['network_failure']) {
    const analysis = fullInputs.value['network_failure']
    const networkId = analysis.inputs.network
    network = networkStore.availableNetworks.find((n) => n.id === networkId)
    if (!network) {
      const analysisType = analysisStore.availableAnalysisTypes?.find((t) => t.db_value === analysis.task_type)
      network = analysisType?.input_options.network.find(
        (o: any) => o.id === networkId
      )
    }
    const visible = panelStore.isVisible({ network })
    network = {
      ...network,
      visible
    }
  } else {
    network = Object.values(fullInputs.value).find(
      (input) => input.type === 'network'
    )
  }
  if (network && !networkStore.availableNetworks.map((n) => n.id).includes(network.id)) {
    networkStore.availableNetworks = [
      ...networkStore.availableNetworks,
      network
    ]
  }
  return network;
})
const selectedInputs = ref<Record<string, any>>({});
const inputSelectionRules = [
  (v: any) => (v ? true : "Input required."),
];
const additionalAnimationLayers = ref();
const inputForm = ref();

function run() {
  inputForm.value.validate().then(({ valid }: { valid: boolean }) => {
    if (valid && projectStore.currentProject && analysisStore.currentAnalysisType) {
      runAnalysis(
        analysisStore.currentAnalysisType.db_value,
        projectStore.currentProject.id,
        selectedInputs.value,
      ).then((result) => {
        analysisStore.currentAnalysisTab = 'old';
        analysisStore.currentResult = result;
        fetchResults();
      })
    }
  });
}

async function fetchResults() {
  if (!projectStore.currentProject || !analysisStore.currentAnalysisType) return;
  await analysisStore.initResults(
    analysisStore.currentAnalysisType.db_value,
    projectStore.currentProject.id,
  )
  if (analysisStore.currentResult) {
    analysisStore.currentResult = analysisStore.availableResults.find(
      (r) => r.id === analysisStore.currentResult?.id
    );
  }
}

function inputIsNumeric(key: string) {
  return (
    analysisStore.currentAnalysisType &&
    analysisStore.currentAnalysisType.input_types[key] === 'number' &&
    analysisStore.currentAnalysisType.input_options[key].length == 1 &&
    analysisStore.currentAnalysisType.input_options[key][0].min !== undefined &&
    analysisStore.currentAnalysisType.input_options[key][0].max !== undefined &&
    analysisStore.currentAnalysisType.input_options[key][0].step !== undefined
  )
}

async function getFullObject(type: string, value: any) {
  if (type !== 'number' && typeof value === 'number') {
    value = { id: value }
  }
  if (type == 'dataset') {
    value = await getDataset(value.id)
  }
  if (type == 'chart') {
    value = await getChart(value.id)
  }
  if (type == 'network') {
    value = await getNetwork(value.id)
  }
  if (type == 'taskresult') {
    value = await getTaskResult(value.id)
  }
  if (typeof value === 'object') {
    value.type = type
    value.visible = panelStore.isVisible({ [type]: value })
    value.showable = panelStore.showableTypes.includes(value.type)
  } else {
    value = {
      name: value,
    }
  }
  return value
}

async function fillInputsAndOutputs() {
  if (!analysisStore.currentResult?.inputs) {
    fullInputs.value = undefined;
    additionalAnimationLayers.value = undefined;
  } else {
    fullInputs.value = Object.fromEntries(
      await Promise.all(
        Object.entries(analysisStore.currentResult.inputs).map(async ([key, value]) => {
          const fullValue = analysisStore.currentAnalysisType?.input_options[key]?.find(
            (o: any) => o.id == value
          );
          const type = analysisStore.currentAnalysisType?.input_types[key].toLowerCase()
          return [key, await getFullObject(type, fullValue || value)];
        })
      )
    );
    if (fullInputs.value?.flood_simulation && !additionalAnimationLayers.value) {
      const floodDataset = {
        id: fullInputs.value?.flood_simulation.outputs.flood as number
      }
      if (panelStore.isVisible({ dataset: floodDataset })) {
        layerStore.fetchAvailableLayersForDataset(floodDataset.id).then((layers) => {
          additionalAnimationLayers.value = layers
        })
      }
    }
  }
  if (!analysisStore.currentResult?.outputs) fullOutputs.value = undefined;
  else {
    fullOutputs.value = Object.fromEntries(
      await Promise.all(
        Object.entries(analysisStore.currentResult.outputs).map(async ([key, value]) => {
          const type = analysisStore.currentAnalysisType?.output_types[key].toLowerCase();
          return [key, await getFullObject(type, value)];
        })
      )
    );
  }
}

async function subscribe() {
  if (analysisStore.currentResult){
    analysisStore.currentResult.subscribers = (await subscribeToTaskResult(analysisStore.currentResult.id)).subscribers;
  }
}

watch(() => analysisStore.currentAnalysisType, () => {
  fetchResults()
  const type = analysisStore.currentAnalysisType
  selectedInputs.value = {}
  if (type) {
    Object.keys(type.input_types).forEach((key) => {
      if (inputIsNumeric(key)) {
        selectedInputs.value[key] = type.input_options[key][0].min
      }
    })
  }
})

watch(() => analysisStore.currentAnalysisTab, () => {
  if (analysisStore.currentAnalysisTab === "old") {
    fetchResults();
  }
});

watch(
  [
    () => analysisStore.currentResult,
    () => layerStore.selectedLayers,
    () => analysisStore.currentChart,
  ],
  fillInputsAndOutputs,
  { deep: true }
);
</script>

<template>
  <div :class="analysisStore.currentAnalysisType ? 'panel-content-outer' : 'panel-content-outer with-search'">
    <v-text-field v-if="!analysisStore.currentAnalysisType" v-model="searchText" label="Search Analytics"
      variant="outlined" density="compact" class="mb-2" append-inner-icon="mdi-magnify" hide-details />
    <v-card class="panel-content-inner">
      <div v-if="analysisStore.currentAnalysisType" style="height: 100%; overflow: auto">
        <v-card-title class="analysis-title">
          {{ analysisStore.currentAnalysisType.name }}
          <v-tooltip text="Close" location="bottom">
            <template v-slot:activator="{ props }">
              <v-btn v-bind="props" icon="mdi-close" variant="plain"
                @click="analysisStore.currentAnalysisType = undefined" />
            </template>
          </v-tooltip>
        </v-card-title>
        <v-expansion-panels v-if="analysisStore.currentAnalysisType.details">
          <v-expansion-panel bg-color="transparent">
            <v-expansion-panel-title class="py-3" style="min-height: 0">Details</v-expansion-panel-title>
            <v-expansion-panel-text class="px-3">
              {{ analysisStore.currentAnalysisType.details }}
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>

        <v-tabs v-model="analysisStore.currentAnalysisTab" align-tabs="center" fixed-tabs>
          <v-tab value="new">Run New</v-tab>
          <v-tab value="old">View Existing</v-tab>
        </v-tabs>

        <v-window v-model="analysisStore.currentAnalysisTab">
          <v-window-item value="new">
            <v-form class="pa-3" @submit.prevent ref="inputForm">
              <v-card-subtitle class="px-1">Select inputs</v-card-subtitle>
              <div v-for="[key, value] in Object.entries(analysisStore.currentAnalysisType.input_options)" :key="key">
                <div v-if="inputIsNumeric(key)">
                  {{ key.replaceAll('_', ' ') }}
                  <div class="px-2 mb-2">
                    <SliderNumericInput :model="selectedInputs[key]"
                      :min="analysisStore.currentAnalysisType.input_options[key][0].min"
                      :max="analysisStore.currentAnalysisType.input_options[key][0].max"
                      :step="analysisStore.currentAnalysisType.input_options[key][0].step"
                      @update="(v: number) => selectedInputs[key] = v" />
                  </div>
                </div>
                <v-text-field
                  v-else-if="analysisStore.currentAnalysisType.input_types[key] === 'string' && !analysisStore.currentAnalysisType.input_options[key].length"
                  v-model="selectedInputs[key]" :label="key.replaceAll('_', ' ')" :rules="inputSelectionRules"
                  density="compact" hide-details="auto" class="my-1" />
                <v-select v-else-if="value.length" v-model="selectedInputs[key]" :label="key.replaceAll('_', ' ')"
                  :items="value" :rules="inputSelectionRules" item-value="id" item-title="name" density="compact"
                  hide-details="auto" class="my-1">
                  <template #item="{ internalItem, props: itemProps }">
                    <v-list-item v-bind="itemProps" v-tooltip="internalItem.title" style="max-width: 400px;" />
                  </template>
                </v-select>
              </div>
              <v-btn @click="run" style="width: 100%" variant="tonal">
                Run Analysis
              </v-btn>
            </v-form>
          </v-window-item>
          <v-window-item value="old">
            <div v-if="analysisStore.availableResults && analysisStore.availableResults.length === 0"
              style="width: 100%; text-align: center" class="pa-3">
              No previous runs of this analysis type exist.
            </div>
            <v-expansion-panels v-else v-model="analysisStore.currentResult" variant="accordion">
              <v-expansion-panel v-for="result in newestFirstResults" :key="result.id" :value="result"
                :title="result.name" bg-color="background">
                <v-expansion-panel-text class="px-3 pb-5">
                  <v-card-subtitle>Inputs</v-card-subtitle>
                  <v-table class="bg-transparent">
                    <tbody v-if="fullInputs" style="width: 100%;">
                      <tr v-for="[key, value] in Object.entries(fullInputs)" :key="key">
                        <td>{{ key.replaceAll('_', ' ') }}</td>
                        <td v-if="value">
                          {{ value.name || value }}
                          <v-btn v-if="value.showable && !value.visible" density="compact" color="primary"
                            @click="() => panelStore.show({ [value.type]: value })">
                            Show
                          </v-btn>
                        </td>
                      </tr>
                    </tbody>
                  </v-table>
                  <div v-if="result.error" class="pa-2">
                    <span style="color:rgb(var(--v-theme-error))">Error: </span>
                    {{ result.error }}
                  </div>
                  <div v-else class="pa-3" style="width: 100%; text-align: center">
                    <v-progress-linear v-if="!result.completed" class="my-3 py-1" indeterminate />
                    {{ result.status }}
                  </div>
                  <div v-if="fullOutputs">
                    <v-card-subtitle>Outputs</v-card-subtitle>
                    <v-table class="bg-transparent">
                      <tbody>
                        <tr v-for="[key, value] in Object.entries(fullOutputs)" :key="key">
                          <template v-if="value?.type == 'network_animation'">
                            <td colspan="2">
                              <div v-if="value?.length === 0">
                                No nodes are affected in this scenario.
                              </div>
                              <node-animation v-else-if="networkInput?.visible"
                                :nodeFailures="key === 'failures' ? value : undefined"
                                :nodeRecoveries="key === 'recoveries' ? value : undefined" :network="networkInput"
                                :additionalAnimationLayers="additionalAnimationLayers" />
                              <div v-else>
                                Show network to view animation.
                              </div>
                            </td>
                          </template>
                          <template v-else>
                            <td>{{ key.replaceAll('_', ' ') }}</td>
                            <td>
                              {{ value?.name }}
                              <v-btn v-if="value && value.showable && !value.visible" color="primary" density="compact"
                                style="display: block" @click="() => panelStore.show({ [value.type]: value })">
                                Show
                              </v-btn>
                            </td>
                          </template>
                        </tr>
                      </tbody>
                    </v-table>
                  </div>
                  <div v-else>
                    <div
                      v-if="appStore.currentUser && analysisStore.currentResult?.subscribers.includes(appStore.currentUser.id)"
                      style="text-align: center;"
                    >
                      <v-icon icon="mdi-check" color="success" />
                      Subscribed
                      <v-icon
                        icon="mdi-information-outline"
                        v-tooltip="'An email will be sent to you when the task is completed.'"
                      />
                    </div>
                    <v-btn
                      v-else
                      @click="subscribe"
                      v-tooltip="'If subscribed, an email will be sent to you when the task is completed.'"
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
        <v-list-item v-for="simType in filteredAnalysisTypes" :key="simType.id"
          @click="analysisStore.currentAnalysisType = simType">
          {{ simType.name }}
          <template v-slot:append>
            <v-icon icon="mdi-information-outline" size="small" v-tooltip="simType.description"></v-icon>
            <v-icon icon="mdi-earth" size="small" class="ml-2"></v-icon>
          </template>
        </v-list-item>
      </v-list>
      <v-progress-linear v-else-if="analysisStore.loadingAnalysisTypes" indeterminate></v-progress-linear>
      <v-card-text v-else class="help-text">No available Analytics.</v-card-text>
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
</style>
