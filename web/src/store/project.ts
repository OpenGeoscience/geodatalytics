import {
    getProjects,
    getProjectDatasets,
    getDatasetTags,
    getDatasets,
    getViewState,
    getProjectViewStates,
    getLayer,
} from '@/api/rest';
import type { Dataset, Project, ViewState } from '@/types';
import { defineStore } from 'pinia';
import { ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import {
    useNetworkStore,
    useMapStore,
    useLayerStore,
    useAnalysisStore,
    usePanelStore,
    useAppStore,
    useStyleStore,
} from '.';

export const useProjectStore = defineStore('project', () => {
    const networkStore = useNetworkStore();
    const analysisStore = useAnalysisStore();
    const mapStore = useMapStore();
    const layerStore = useLayerStore();
    const panelStore = usePanelStore();
    const appStore = useAppStore();
    const styleStore = useStyleStore();

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
    const availableViewStates = ref<ViewState[]>([]);
    const currentViewState = ref<ViewState>();
    const currentViewStateLoaded = ref<boolean>(false);

    async function fetchProjectDatasets() {
        if (!currentProject.value) { return; }

        loadingDatasets.value = true;
        availableDatasets.value = await getProjectDatasets(currentProject.value.id)
        loadingDatasets.value = false;
    }

    async function fetchAvailableDatasetTags() {
        availableDatasetTags.value = await getDatasetTags()
    }

    async function fetchProjectViewStates() {
        if (!currentProject.value) { return; }
        availableViewStates.value = await getProjectViewStates(currentProject.value.id)
    }

    function getCurrentViewState(): ViewState | undefined {
        if (!currentProject.value) return undefined;
        const mapPosition = mapStore.getCurrentMapPosition();
        // use proportions instead of coordinates
        // so that the view state looks good with other window sizes
        const panelArrangement = panelStore.panelArrangement.map((panelConfig => {
            const copyConfig = { ...panelConfig }
            delete copyConfig.element
            if (copyConfig.position) {
              copyConfig.position = {
                x: copyConfig.position.x / window.innerWidth,
                y: copyConfig.position.y / window.innerHeight,
              }
            }
            return copyConfig
        }))
        const includeLayers = layerStore.selectedLayers.filter((layer) => layer.visible)
        const styleKeysToCurrentFrames = Object.fromEntries(
          includeLayers.map((layer) => [mapStore.uniqueLayerIdFromLayer(layer), layer.current_frame_index])
        )
        const viewState: ViewState = {
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
              return Object.keys(styleKeysToCurrentFrames).includes(styleKey)
            })
          ),
          left_sidebar_open: appStore.openSidebars.includes('left'),
          right_sidebar_open: appStore.openSidebars.includes('right'),
          panel_arrangement: panelArrangement,
          theme: appStore.theme,
          map_center: mapPosition.center,
          map_zoom: Math.round(mapPosition.zoom),
        }
        return viewState;
    }

    function navigateToViewState(viewState: ViewState) {
        currentViewStateLoaded.value = false;
        router.push(`/view/${viewState.id}`);
    }

    watch(() => route?.fullPath, loadViewStateFromURL);
    async function loadViewStateFromURL() {
        if (!route.path.includes('/view/')) {
            currentViewState.value = undefined;
            return;
        };
        const viewStateId = parseInt(route.path.split('/view/')[1]);
        const viewState = await getViewState(viewStateId)
        if (viewState) {
            currentViewState.value = viewState;
            // Set some state attrs that don't require the project to be loaded first
            panelStore.panelArrangement = viewState.panel_arrangement.map((panelConfig) => {
              if (panelConfig.position) {
                panelConfig.position = {
                  x: panelConfig.position.x * window.innerWidth,
                  y: panelConfig.position.y * window.innerHeight,
                }
              }
              return panelConfig;
            });
            appStore.openSidebars = []
            if (viewState.left_sidebar_open) appStore.openSidebars.push('left');
            if (viewState.right_sidebar_open) appStore.openSidebars.push('right');

            const selectedProject = availableProjects.value.find((p) => p.id === viewState.project);
            if (currentProject.value?.id !== selectedProject?.id) {
                currentProject.value = selectedProject;
                // Remaining state attrs that depend on project loading will be set by the currentProject watcher
            } else {
                if (mapStore.map) mapStore.clearMapLayers();
                finishLoadingViewState();
            }
        }
    }
    async function finishLoadingViewState() {
        const viewState = currentViewState.value;
        if (viewState && !currentViewStateLoaded.value && mapStore.map) {
            appStore.theme = viewState.theme;
            analysisStore.currentAnalysisType = analysisStore.availableAnalysisTypes?.find((a) => a.db_value === viewState.current_analysis_type);
            if (analysisStore.currentAnalysisType && currentProject.value) {
              await analysisStore.initResults(
                analysisStore.currentAnalysisType.db_value, currentProject.value.id,
              )
              analysisStore.currentResult = analysisStore.availableResults?.find((c) => c.id === viewState.current_result);
              if (analysisStore.currentResult) {
                analysisStore.currentAnalysisTab = 'old'
              }
            }
            analysisStore.currentChart = analysisStore.availableCharts?.find((c) => c.id === viewState.current_chart);
            networkStore.currentNetwork = networkStore.availableNetworks.find((n) => n.id === viewState.current_network);

            // @ts-expect-error for "Type instantiation is excessively deep and possibly infinite"
            mapStore.currentBasemap = mapStore.availableBasemaps?.find((b) => b.id === viewState.current_basemap);
            mapStore.setMapPosition(viewState.map_center as [number, number], viewState.map_zoom)

            // Add layers with copy ids from selected_layer_styles
            layerStore.selectedLayers = []
            await Promise.all(Object.keys(viewState.selected_layer_styles).map(async (styleKey) => {
                // Parse the style key to get layer id and copy_id
                const [layerIdStr, copyIdStr] = styleKey.split('.');
                const layerId = parseInt(layerIdStr);
                const copyId = parseInt(copyIdStr);
                const layer = await getLayer(layerId);
                await layerStore.addLayer(layer, copyId);
            }))
            // Ensure correct layer order
            layerStore.selectedLayers = layerStore.selectedLayers.sort((layer1, layer2) => {
              const key1 = mapStore.uniqueLayerIdFromLayer(layer1);
              const key2 = mapStore.uniqueLayerIdFromLayer(layer2);
              return viewState.selected_layer_order.indexOf(key1) - viewState.selected_layer_order.indexOf(key2)
            })
            // Ensure correct current frames
            layerStore.selectedLayers = layerStore.selectedLayers.map((layer) => {
              const styleKey = mapStore.uniqueLayerIdFromLayer(layer);
              if (viewState.selected_layer_current_frames[styleKey]) {
                layer.current_frame_index = viewState.selected_layer_current_frames[styleKey];
              }
              return layer;
            })
            styleStore.selectedLayerStyles = viewState.selected_layer_styles;
            currentViewStateLoaded.value = true;
        }
    }

    watch(currentProject, async () => {
        clearProjectState();

        if (currentViewState.value) {
          mapStore.setMapPosition(
            currentViewState.value.map_center as [number, number],
            currentViewState.value.map_zoom,
            true,
          )
        } else {
          mapStore.resetMapPosition(currentProject.value);
        }

        mapStore.clearMapLayers();
        styleStore.fetchColormaps();

        if (currentProject.value) {
            await fetchProjectDatasets();
            await fetchProjectViewStates();
            await analysisStore.initCharts(currentProject.value.id);
            await analysisStore.initAnalysisTypes(currentProject.value.id);
            await networkStore.initNetworks(currentProject.value.id);
            finishLoadingViewState();
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
        availableViewStates.value = [];

        layerStore.selectedLayers = [];
        styleStore.selectedLayerStyles = {};

        mapStore.clickedFeature = undefined;

        networkStore.availableNetworks = [];

        analysisStore.availableCharts = undefined;
        analysisStore.currentChart = undefined;
        analysisStore.availableAnalysisTypes = undefined;
        analysisStore.currentAnalysisType = undefined;
    }

    async function refreshAllDatasets() {
      loadingDatasets.value = true;
      allDatasets.value = await getDatasets()
      loadingDatasets.value = false;
    }

    watch(projectConfigMode, loadProjects);
    async function loadProjects() {
        clearState();
        availableProjects.value = await getProjects()
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
        availableViewStates,
        currentViewState,
        currentViewStateLoaded,
        fetchProjectDatasets,
        fetchAvailableDatasetTags,
        fetchProjectViewStates,
        getCurrentViewState,
        navigateToViewState,
        loadViewStateFromURL,
        clearState,
        clearProjectState,
        refreshAllDatasets,
        loadProjects,
    }
});
