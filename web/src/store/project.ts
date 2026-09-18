import {
  getProjects,
  getProjectDatasets,
  getDatasetTags,
  getDatasets,
  getBookmark,
  getProjectBookmarks,
  getLayer,
} from "@/api/rest";
import type { Dataset, Project, Bookmark } from "@/types";
import { defineStore } from "pinia";
import { ref, computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import {
  useNetworkStore,
  useMapStore,
  useLayerStore,
  useAnalysisStore,
  usePanelStore,
  useAppStore,
  useStyleStore,
  useFramePreviewStore,
  useTutorialStore,
} from ".";
import { clearFramePreviewCache } from "@/utils/framePreviewCache";

export const useProjectStore = defineStore("project", () => {
  const networkStore = useNetworkStore();
  const analysisStore = useAnalysisStore();
  const mapStore = useMapStore();
  const layerStore = useLayerStore();
  const panelStore = usePanelStore();
  const appStore = useAppStore();
  const styleStore = useStyleStore();
  const tutorialStore = useTutorialStore();

  const route = useRoute();
  const router = useRouter();

  const loadingProjects = ref<boolean>(true);
  const availableProjects = ref<Project[]>([]);
  const currentProject = ref<Project>();
  const projectConfigMode = ref<"new" | "existing">();
  const loadingDatasets = ref<boolean>(false);
  const allDatasets = ref<Dataset[]>();
  const availableDatasets = ref<Dataset[]>();
  const availableDatasetTags = ref<string[]>([]);
  const availableBookmarks = ref<Bookmark[]>([]);
  const currentBookmark = ref<Bookmark>();
  const currentBookmarkLoaded = ref<boolean>(false);

  const permissions = computed(() => {
    const ret = Object.fromEntries(
      availableProjects.value.map((p) => {
        let perm = "";
        if (
          p.owner?.id === appStore.currentUser?.id ||
          appStore.currentUser?.is_superuser
        ) {
          perm = "owner";
        } else if (
          appStore.currentUser &&
          p.collaborators.map((u) => u.id).includes(appStore.currentUser.id)
        ) {
          perm = "collaborator";
        } else if (
          appStore.currentUser &&
          (p.followers.map((u) => u.id).includes(appStore.currentUser.id) ||
            p.allow_unauthenticated)
        ) {
          perm = "follower";
        }
        return [p.id, perm];
      }),
    );
    return ret;
  });

  async function fetchProjectDatasets() {
    if (!currentProject.value) {
      return;
    }

    loadingDatasets.value = true;
    availableDatasets.value = await getProjectDatasets(currentProject.value.id);
    loadingDatasets.value = false;
  }

  async function fetchAvailableDatasetTags() {
    availableDatasetTags.value = await getDatasetTags();
  }

  async function fetchProjectBookmarks() {
    if (!currentProject.value) {
      return;
    }
    availableBookmarks.value = await getProjectBookmarks(
      currentProject.value.id,
    );
  }

  function getCurrentBookmark(): Bookmark | undefined {
    if (!currentProject.value) return undefined;
    const mapPosition = mapStore.getCurrentMapPosition();
    // use proportions instead of coordinates
    // so that the bookmark looks good with other window sizes
    const panelArrangement = panelStore.panelArrangement.map((panelConfig) => {
      const copyConfig = { ...panelConfig };
      delete copyConfig.element;
      if (copyConfig.position) {
        copyConfig.position = {
          x: copyConfig.position.x / window.innerWidth,
          y: copyConfig.position.y / window.innerHeight,
        };
      }
      return copyConfig;
    });
    const includeLayers = layerStore.selectedLayers.filter(
      (layer) => layer.visible,
    );
    const styleKeysToCurrentFrames = Object.fromEntries(
      includeLayers.map((layer) => [
        styleStore.layerStyleKey(layer),
        layer.current_frame_index,
      ]),
    );
    const bookmark: Bookmark = {
      project: currentProject.value.id,
      current_analysis_type: analysisStore.currentAnalysisType?.db_value,
      current_result: analysisStore.currentResult?.id,
      current_chart: analysisStore.currentChart?.id,
      current_basemap: mapStore.currentBasemap?.id,
      current_network: networkStore.currentNetwork?.id,
      selected_layers: includeLayers.map((layer) => layer.id),
      selected_layer_current_frames: styleKeysToCurrentFrames,
      selected_layer_order: Object.keys(styleKeysToCurrentFrames),
      selected_layer_styles: Object.fromEntries(
        Object.entries(styleStore.selectedLayerStyles).filter(([styleKey]) => {
          return Object.keys(styleKeysToCurrentFrames).includes(styleKey);
        }),
      ),
      left_sidebar_open: appStore.openSidebars.includes("left"),
      right_sidebar_open: appStore.openSidebars.includes("right"),
      panel_arrangement: panelArrangement,
      theme: appStore.theme,
      map_center: mapPosition.center,
      map_zoom: Math.round(mapPosition.zoom),
    };
    return bookmark;
  }

  function navigateNoBookmark() {
    router.push("/");
  }

  function navigateToBookmark(bookmark: Bookmark) {
    currentBookmarkLoaded.value = false;
    router.push(`/bookmark/${bookmark.id}`);
  }

  watch(() => route?.fullPath, loadBookmarkFromURL);
  async function loadBookmarkFromURL() {
    if (
      !appStore.authenticated &&
      (tutorialStore.showWelcomeMessage || tutorialStore.showTutorialStep > 1)
    ) {
      // Don't load bookmark until after exiting tutorial
      return;
    }
    if (!route.path.includes("/bookmark/")) {
      currentBookmark.value = undefined;
      return;
    }
    const bookmarkId = parseInt(route.path.split("/bookmark/")[1]);
    const bookmark = await getBookmark(bookmarkId);
    if (bookmark) {
      currentBookmark.value = bookmark;
      // Set some state attrs that don't require the project to be loaded first
      panelStore.panelArrangement = bookmark.panel_arrangement.map(
        (panelConfig) => {
          if (panelConfig.position) {
            panelConfig.position = {
              x: panelConfig.position.x * window.innerWidth,
              y: panelConfig.position.y * window.innerHeight,
            };
          }
          return panelConfig;
        },
      );
      appStore.openSidebars = [];
      if (bookmark.left_sidebar_open) appStore.openSidebars.push("left");
      if (bookmark.right_sidebar_open) appStore.openSidebars.push("right");

      const selectedProject = availableProjects.value.find(
        (p) => p.id === bookmark.project,
      );
      if (currentProject.value?.id !== selectedProject?.id) {
        currentProject.value = selectedProject;
        // Remaining state attrs that depend on project loading will be set by the currentProject watcher
      } else {
        if (mapStore.map) mapStore.clearMapLayers();
        finishLoadingBookmark();
      }
    }
  }
  async function finishLoadingBookmark() {
    const bookmark = currentBookmark.value;
    if (bookmark && !currentBookmarkLoaded.value && mapStore.map) {
      appStore.theme = bookmark.theme;
      analysisStore.currentChart = analysisStore.availableCharts?.find(
        (c) => c.id === bookmark.current_chart,
      );
      networkStore.currentNetwork = networkStore.availableNetworks.find(
        (n) => n.id === bookmark.current_network,
      );

      // @ts-ignore "Type instantiation is excessively deep and possibly infinite"
      mapStore.currentBasemap = mapStore.availableBasemaps?.find(
        (b) => b.id === bookmark.current_basemap,
      );
      mapStore.setMapPosition(
        bookmark.map_center as [number, number],
        bookmark.map_zoom,
      );

      // Add layers with copy ids from selected_layer_styles
      layerStore.selectedLayers = [];
      await Promise.all(
        Object.keys(bookmark.selected_layer_styles).map(async (styleKey) => {
          // Parse the style key to get layer id and copy_id
          const [layerIdStr, copyIdStr] = styleKey.split(".");
          const layerId = parseInt(layerIdStr);
          const copyId = parseInt(copyIdStr);
          const layer = await getLayer(layerId);
          await layerStore.addLayer(layer, copyId);
        }),
      );
      // Ensure correct layer order
      layerStore.selectedLayers = layerStore.selectedLayers.sort(
        (layer1, layer2) => {
          const key1 = styleStore.layerStyleKey(layer1);
          const key2 = styleStore.layerStyleKey(layer2);
          return (
            bookmark.selected_layer_order.indexOf(key1) -
            bookmark.selected_layer_order.indexOf(key2)
          );
        },
      );
      // Ensure correct current frames
      layerStore.selectedLayers = layerStore.selectedLayers.map((layer) => {
        const styleKey = styleStore.layerStyleKey(layer);
        if (bookmark.selected_layer_current_frames[styleKey]) {
          layer.current_frame_index =
            bookmark.selected_layer_current_frames[styleKey];
        }
        return layer;
      });
      styleStore.selectedLayerStyles = bookmark.selected_layer_styles;

      analysisStore.currentAnalysisType =
        analysisStore.availableAnalysisTypes?.find(
          (a) => a.db_value === bookmark.current_analysis_type,
        );
      analysisStore.initSelectedInputs();
      if (analysisStore.currentAnalysisType && currentProject.value) {
        await analysisStore.initResults(
          analysisStore.currentAnalysisType.db_value,
          currentProject.value.id,
        );
        analysisStore.currentResult = analysisStore.availableResults?.find(
          (c) => c.id === bookmark.current_result,
        );
        if (analysisStore.currentResult) {
          analysisStore.currentAnalysisTab = "old";
        }
      }
      currentBookmarkLoaded.value = true;
    }
  }

  watch(currentProject, async () => {
    clearProjectState();

    if (currentBookmark.value) {
      mapStore.setMapPosition(
        currentBookmark.value.map_center as [number, number],
        currentBookmark.value.map_zoom,
        true,
      );
    } else {
      mapStore.resetMapPosition(currentProject.value);
    }

    mapStore.clearMapLayers();
    styleStore.fetchColormaps();

    if (currentProject.value) {
      await fetchProjectDatasets();
      await fetchProjectBookmarks();
      await analysisStore.initCharts(currentProject.value.id);
      await analysisStore.initAnalysisTypes(currentProject.value.id);
      await networkStore.initNetworks(currentProject.value.id);
      finishLoadingBookmark();
    }
  });

  function clearState() {
    clearProjectState();
    mapStore.setBasemapToDefault();
    appStore.currentError = undefined;

    panelStore.resetPanels();
    panelStore.draggingPanel = undefined;
    panelStore.draggingFrom = undefined;
    panelStore.dragModes = [];
  }

  function clearProjectState() {
    availableDatasets.value = undefined;
    availableBookmarks.value = [];

    layerStore.selectedLayers = [];
    styleStore.selectedLayerStyles = {};
    styleStore.clearStyleEditing();
    useFramePreviewStore().clearAll();
    clearFramePreviewCache();

    mapStore.clickedFeature = undefined;

    networkStore.availableNetworks = [];

    analysisStore.availableCharts = undefined;
    analysisStore.currentChart = undefined;
    analysisStore.availableAnalysisTypes = undefined;
    analysisStore.currentAnalysisType = undefined;
  }

  async function refreshAllDatasets() {
    loadingDatasets.value = true;
    allDatasets.value = await getDatasets();
    loadingDatasets.value = false;
  }

  async function loadProjects() {
    clearState();
    availableProjects.value = await getProjects();
    loadingProjects.value = false;
  }

  return {
    loadingProjects,
    availableProjects,
    currentProject,
    projectConfigMode,
    loadingDatasets,
    allDatasets,
    availableDatasets,
    availableDatasetTags,
    availableBookmarks,
    currentBookmark,
    currentBookmarkLoaded,
    permissions,
    fetchProjectDatasets,
    fetchAvailableDatasetTags,
    fetchProjectBookmarks,
    getCurrentBookmark,
    navigateNoBookmark,
    navigateToBookmark,
    loadBookmarkFromURL,
    clearState,
    clearProjectState,
    refreshAllDatasets,
    loadProjects,
  };
});
