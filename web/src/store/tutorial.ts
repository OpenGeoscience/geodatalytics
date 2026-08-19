import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  usePanelStore,
  useProjectStore,
  useLayerStore,
  useAnalysisStore,
  useNetworkStore,
} from "@/store";

export const useTutorialStore = defineStore("tutorial", () => {
  // Sibling store imports
  const panelStore = usePanelStore();
  const projectStore = useProjectStore();
  const layerStore = useLayerStore();
  const analysisStore = useAnalysisStore();
  const networkStore = useNetworkStore();

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
            .fetchAvailableLayersForDataset(
              projectStore.availableDatasets[0].id,
            )
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
        "The controls bar has a set of additional tools: basemap configuration, fitting to visible layers, screenshots, saved views, map controls, and a help menu. You can restart this tutorial from the help menu at any time.",
      position: ["70px", "400px"],
      proceed: () => {},
    },
  ];
  const numTutorialSteps = computed(() => {
    return tutorialSteps.length;
  });
  const currentTutorialStep = computed(() => {
    if (
      showTutorialStep.value == 0 ||
      showTutorialStep.value > tutorialSteps.length
    )
      return undefined;
    return tutorialSteps[showTutorialStep.value - 1];
  });

  function tutorialProceed() {
    currentTutorialStep.value?.proceed();
    showTutorialStep.value += 1;
  }

  return {
    showWelcomeMessage,
    showTutorialStep,
    numTutorialSteps,
    currentTutorialStep,
    tutorialProceed,
  };
});
