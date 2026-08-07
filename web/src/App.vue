<script setup lang="ts">
import { watch, ref, onMounted, computed } from "vue";
import { useTheme } from "vuetify";

import ToggleCompareMap from "./components/map/ToggleCompareMap.vue";
import SideBars from "./components/sidebars/SideBars.vue";
import ControlsBar from "./components/ControlsBar.vue";
import SplashPage from "./components/SplashPage.vue";

import {
  useAppStore,
  usePanelStore,
  useProjectStore,
  useConversionStore,
  useLayerStore,
  useAnalysisStore,
  useNetworkStore,
} from "@/store";
const appStore = useAppStore();
const panelStore = usePanelStore();
const projectStore = useProjectStore();
const conversionStore = useConversionStore();
const layerStore = useLayerStore();
const analysisStore = useAnalysisStore();
const networkStore = useNetworkStore();

const showError = computed(() => appStore.currentError !== undefined);
const showWelcomeMessage = ref(true);
const showTutorialStep = ref(0);
const tutorialSteps = [
  {
    message:
      "Projects are the top level of organization in GeoDatalytics. Selecting a project will populate the sidebar panels with related objects.",
    position: ["70px", "370px"],
    proceed: () => {
      if (!projectStore.currentProject)
        projectStore.currentProject = projectStore.availableProjects[0];
    },
  },
  {
    message:
      "The Datasets panel displays all the datasets added to the selected project, organized by category. You can search datasets by name or filter by tag. Expanding a dataset shows its layers, which can be added to the map with the plus button.",
    position: ["180px", "370px"],
    proceed: () => {
      if (
        !layerStore.selectedLayers.length &&
        projectStore.availableDatasets?.length
      ) {
        layerStore
          .fetchAvailableLayersForDataset(projectStore.availableDatasets[0].id)
          .then(() => {
            if (layerStore.availableLayers.length) {
              layerStore.addLayer(layerStore.availableLayers[0]);
            }
          });
      }
    },
  },
  {
    message:
      "The Selected Layers panel shows the layers added to the map. You can reorder layers by dragging them in this list, toggle layer visibility with the checkboxes, and open the layer style menu with the gear icon.",
    position: ["60%", "370px"],
    proceed: () => {
      panelStore.panelArrangement = panelStore.panelArrangement.map((p) => {
        if (p.id === "legend") p.collapsed = false;
        return p;
      });
    },
  },
  {
    message:
      "The Legend panel is a visual summary of the layer configuration applied in the Selected Layers panel. This can be helpful to include in saved views and screenshots.",
    position: ["100px", "calc(100% - 570px)"],
    proceed: () => {
      panelStore.panelArrangement = panelStore.panelArrangement.map((p) => {
        if (p.id === "legend") p.collapsed = true;
        if (p.id === "charts") p.collapsed = false;
        return p;
      });
      if (
        analysisStore.availableCharts?.length &&
        !analysisStore.currentChart
      ) {
        analysisStore.currentChart = analysisStore.availableCharts[0];
      }
    },
  },
  {
    message:
      "The Charts panel allows you to view relevant tabular data as line charts.",
    position: ["200px", "calc(100% - 570px)"],
    proceed: () => {
      analysisStore.currentChart = undefined;
      panelStore.panelArrangement = panelStore.panelArrangement.map((p) => {
        if (p.id === "charts") p.collapsed = true;
        if (p.id === "networks") p.collapsed = false;
        return p;
      });
      if (
        networkStore.availableNetworks?.length &&
        !networkStore.currentNetwork
      ) {
        networkStore.currentNetwork = networkStore.availableNetworks[0];
      }
    },
  },
  {
    message:
      "The Networks panel allows you to view the nodes and edges of a network. You can deactivate/reactivate nodes to assess network connectivity.",
    position: ["300px", "calc(100% - 570px)"],
    proceed: () => {
      networkStore.currentNetwork = undefined;
      panelStore.panelArrangement = panelStore.panelArrangement.map((p) => {
        if (p.id === "networks") p.collapsed = true;
        if (p.id === "analytics") p.collapsed = false;
        return p;
      });
      if (
        analysisStore.availableAnalysisTypes?.length &&
        !analysisStore.currentAnalysisType
      ) {
        analysisStore.currentAnalysisType =
          analysisStore.availableAnalysisTypes[0];
      }
    },
  },
  {
    message:
      "The Analytics panel allows you view the results of tasks run on the data. These tasks can be simulations, AI inferences, or computational analytics. Contact Kitware to implement a custom task. You must be logged in to run new tasks.",
    position: ["400px", "calc(100% - 570px)"],
    proceed: () => {
      panelStore.panelArrangement = panelStore.panelArrangement.map((p) => {
        if (p.id === "analytics") p.collapsed = true;
        return p;
      });
    },
  },
  {
    message:
      "The controls bar has a set of additional tools: basemap configuration, fitting to visible layers, screenshots, saved views, and map controls.",
    position: ["70px", "400px"],
    proceed: () => {},
  },
];
const currentTutorialStep = computed(() => {
  if (
    showTutorialStep.value == 0 ||
    showTutorialStep.value > tutorialSteps.length
  )
    return undefined;
  return tutorialSteps[showTutorialStep.value - 1];
});

// useTheme must be called within a setup function
appStore.themeManager = useTheme();

function onReady() {
  if (appStore.currentUser) {
    projectStore.clearState();
    projectStore.loadProjects();
    conversionStore.createWebSocket();
  }
}

function tutorialProceed() {
  currentTutorialStep.value?.proceed();
  showTutorialStep.value += 1;
}

onMounted(onReady);
watch(() => appStore.currentUser, onReady);
</script>

<template>
  <v-app>
    <SplashPage v-if="!appStore.currentUser" />
    <div v-else>
      <v-dialog
        v-if="!appStore.authenticated"
        v-model="showWelcomeMessage"
        width="400"
      >
        <v-card>
          <v-card-title class="pa-3"> Welcome to GeoDatalytics </v-card-title>
          <v-card-text>
            <div>
              While not logged in, you can use a limited version of the
              application to explore the available features.
            </div>
            <div class="py-2">
              You can view any projects that allow unauthenticated access, but
              you cannot make changes or create new objects.
            </div>
            <div>
              To access the full version of the application, you must log in.
            </div>
          </v-card-text>
          <v-card-actions
            class="px-4 d-flex"
            style="justify-content: space-between"
          >
            <v-btn
              color="primary"
              @click="
                showTutorialStep = 1;
                showWelcomeMessage = false;
              "
              >Show me a tutorial</v-btn
            >
            <v-btn color="primary" @click="showWelcomeMessage = false"
              >Explore without tutorial</v-btn
            >
          </v-card-actions>
        </v-card>
      </v-dialog>
      <div
        v-if="currentTutorialStep"
        class="tutorial-message"
        :style="{
          top: currentTutorialStep.position[0],
          left: currentTutorialStep.position[1],
        }"
      >
        <div class="d-flex" style="width: 100%; justify-content: space-between">
          Step {{ showTutorialStep }} of {{ tutorialSteps.length }}
          <v-btn
            v-if="showTutorialStep < tutorialSteps.length"
            variant="text"
            icon="mdi-arrow-right"
            size="sm"
            @click="tutorialProceed"
          ></v-btn>
        </div>
        {{ currentTutorialStep?.message }}
        <v-btn
          v-if="showTutorialStep == tutorialSteps.length"
          color="primary"
          @click="showTutorialStep = 0"
          >Exit Tutorial</v-btn
        >
      </div>
      <v-overlay
        v-if="appStore.currentUser"
        :model-value="showError"
        absolute
        :opacity="0.8"
        class="align-center justify-center"
      >
        <v-card class="pa-3">
          <v-btn
            icon
            variant="flat"
            class="pa-3"
            style="float: right"
            @click.stop="appStore.currentError = undefined"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
          <v-card-title> Error: </v-card-title>
          <v-card-text>
            {{ appStore.currentError }}
          </v-card-text>
        </v-card>
      </v-overlay>
      <div>
        <div
          :class="
            panelStore.draggingPanel ? 'main-area no-select' : 'main-area'
          "
          @mousemove="panelStore.dragPanel"
          @mouseup="panelStore.stopDrag"
        >
          <ToggleCompareMap />
          <SideBars />
          <ControlsBar />
        </div>
      </div>
    </div>
  </v-app>
</template>

<style>
* {
  font-family: "Inter", serif;
  font-optical-sizing: auto;
  font-weight: 400;
  font-style: normal;
}
.main-area {
  position: absolute;
  height: 100%;
  width: 100%;
}
.no-select * {
  /* Prevent text highlighting during drag events */
  -webkit-user-select: none;
  -ms-user-select: none;
  user-select: none;
}
/* Chrome - Hides track and width/height set for vertical/horizontal scrollbars */
::-webkit-scrollbar {
  background-color: transparent;
  width: 4px;
}

/* Chrome - Changes thumb color and rounds scrollbar edges, in Chrome any
scrollbar changes disables default styling and rounding so corners appear squared */
::-webkit-scrollbar-thumb {
  background-color: rgb(var(--v-theme-border));
  border-radius: 4px;
}

.v-btn.bg-transparent {
  color: rgb(var(--v-theme-secondary-text));
}

.v-number-input .v-field__field {
  flex-direction: column;
}

.v-input {
  --v-input-control-height: 32px;
}

.tutorial-message {
  position: absolute;
  z-index: 2000;
  padding: 8px;
  border-radius: 4px;
  width: 200px;
  background-color: rgb(var(--v-theme-on-surface-variant));
  color: rgb(var(--v-theme-surface-variant));
}
</style>
