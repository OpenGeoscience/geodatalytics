import { apiClient, s3ffClient } from "./auth";
import type {
  User,
  Project,
  ProjectPatch,
  ProjectPermissions,
  Dataset,
  Layer,
  Chart,
  AnalysisType,
  Network,
  NetworkAnimation,
  NetworkState,
  RasterDataValues,
  FileItem,
  RasterData,
  VectorData,
  LayerStyle,
  VectorSummary,
  LayerFrame,
  TaskResult,
  Colormap,
  Basemap,
  Bookmark,
  Region,
} from "@/types";

export async function getUsers(): Promise<User[]> {
  return (await apiClient.get("users/")).data.results;
}

export async function getBasemaps(): Promise<Basemap[]> {
  return (await apiClient.get("basemaps/")).data.results;
}

export async function createBasemap(basemap: Basemap): Promise<Basemap> {
  return (await apiClient.post("basemaps/", basemap)).data;
}

export async function getProjects(): Promise<Project[]> {
  return (await apiClient.get("projects/")).data.results;
}

export async function createProject(
  name: string,
  default_map_center: number[],
  default_map_zoom: number,
): Promise<Project> {
  return (
    await apiClient.post("projects/", {
      name,
      default_map_center,
      default_map_zoom,
    })
  ).data;
}

export async function patchProject(
  projectId: number,
  data: ProjectPatch,
): Promise<Project> {
  return (await apiClient.patch(`projects/${projectId}/`, data)).data;
}

export async function updateProjectPermissions(
  projectId: number,
  data: ProjectPermissions,
): Promise<Project> {
  return (await apiClient.put(`projects/${projectId}/permissions/`, data)).data;
}

export async function deleteProject(projectId: number): Promise<Project> {
  return (await apiClient.delete(`projects/${projectId}/`)).data;
}

export async function getProjectDatasets(
  projectId: number,
): Promise<Dataset[]> {
  return (await apiClient.get(`datasets/?project=${projectId}`)).data.results;
}

export async function getChart(chartId: number): Promise<Chart> {
  return (await apiClient.get(`charts/${chartId}/`)).data;
}

export async function getChartFiles(chartId: number): Promise<FileItem[]> {
  return (await apiClient.get(`charts/${chartId}/files/`)).data;
}

export async function getProjectCharts(projectId: number): Promise<Chart[]> {
  return (await apiClient.get(`charts/?project=${projectId}`)).data.results;
}

export async function getProjectAnalysisTypes(
  projectId: number,
): Promise<AnalysisType[]> {
  return (await apiClient.get(`analytics/project/${projectId}/types/`)).data;
}

export async function getDatasets(): Promise<Dataset[]> {
  return (await apiClient.get("datasets/")).data.results;
}

export async function getDataset(datasetId: number): Promise<Dataset> {
  return (await apiClient.get(`datasets/${datasetId}/`)).data;
}

export async function createDataset(data: any): Promise<Dataset> {
  return (await apiClient.post("datasets/", data)).data;
}

export async function deleteDataset(datasetId: number): Promise<Dataset> {
  return (await apiClient.delete(`datasets/${datasetId}/`)).data;
}

export async function getDatasetTags(): Promise<string[]> {
  return (await apiClient.get("datasets/tags/")).data;
}

export async function spawnDatasetConversion(
  datasetId: number,
  options: any,
): Promise<Dataset> {
  return (await apiClient.post(`datasets/${datasetId}/convert/`, options || {}))
    .data;
}

export async function getDatasetLayers(
  datasetId: number,
  projectId: number,
): Promise<Layer[]> {
  return (
    await apiClient.get(`datasets/${datasetId}/layers/?project=${projectId}`)
  ).data;
}

export async function getLayer(
  layerId: number,
  projectId: number | undefined,
): Promise<Layer> {
  let url = `layers/${layerId}/`;
  if (projectId) url += `?project=${projectId}`;
  return (await apiClient.get(url)).data;
}

export async function getLayerFrames(layerId: number): Promise<LayerFrame[]> {
  return (await apiClient.get(`layers/${layerId}/frames/`)).data;
}

export async function getDatasetFiles(datasetId: number): Promise<FileItem[]> {
  return (await apiClient.get(`datasets/${datasetId}/files/`)).data;
}

export async function getFileDataObjects(
  fileId: number,
): Promise<(RasterData | VectorData)[]> {
  return (await apiClient.get(`files/${fileId}/data/`)).data;
}

export async function uploadFile(file: File): Promise<string> {
  return await s3ffClient.uploadFile(file, "core.FileItem.file");
}

export async function createFileItem(data: any): Promise<FileItem> {
  return (await apiClient.post("files/", data)).data;
}

export async function getDatasetNetworks(
  datasetId: number,
): Promise<Network[]> {
  return (await apiClient.get(`datasets/${datasetId}/networks/`)).data;
}

export async function getProjectNetworks(
  projectId: number,
): Promise<Network[]> {
  return (await apiClient.get(`networks/?project=${projectId}`)).data.results;
}

export async function getNetwork(networkId: number): Promise<Network> {
  return (await apiClient.get(`networks/${networkId}/`)).data;
}

export async function getNetworkAnimations(
  networkId: number,
  projectId: number,
): Promise<NetworkAnimation[]> {
  return (
    await apiClient.get(
      `network-animations/?network=${networkId}&project=${projectId}`,
    )
  ).data.results;
}

export async function getNetworkAnimation(
  animationId: number,
): Promise<NetworkAnimation> {
  return (await apiClient.get(`network-animations/${animationId}/`)).data;
}

export async function createNetworkAnimation(
  name: string,
  network: number,
  project: number,
): Promise<NetworkAnimation> {
  return (
    await apiClient.post(`network-animations/`, { name, network, project })
  ).data;
}

export async function deleteNetworkAnimation(
  animId: number,
): Promise<NetworkAnimation> {
  return (await apiClient.delete(`network-animations/${animId}/`)).data;
}

export async function getNetworkAnimationStates(
  animId: number,
): Promise<NetworkState[]> {
  return (await apiClient.get(`network-states/?animation=${animId}`)).data
    .results;
}

export async function createNetworkAnimationState(
  animation: number,
  index: number,
): Promise<NetworkState> {
  return (await apiClient.post(`network-states/`, { animation, index })).data;
}

export async function deleteNetworkAnimationState(
  stateId: number,
): Promise<NetworkState> {
  return (await apiClient.delete(`network-states/${stateId}/`)).data;
}

export async function updateNetworkAnimationState(
  state: NetworkState,
): Promise<NetworkState> {
  return (await apiClient.patch(`network-states/${state.id}/`, state)).data;
}

export async function getVectorSummary(
  vectorId: number,
): Promise<VectorSummary> {
  return (await apiClient.get(`vectors/${vectorId}/summary/`)).data;
}

export async function getRasterPixelValue(
  rasterId: number,
  position: { lat: number; lng: number },
): Promise<RasterDataValues> {
  return (
    await apiClient.get(`rasters/${rasterId}/pixel/`, {
      params: position,
    })
  ).data;
}

export async function runAnalysis(
  analysisType: string,
  projectId: number,
  args: object,
) {
  return (
    await apiClient.post(
      `analytics/project/${projectId}/types/${analysisType}/run/`,
      args,
    )
  ).data;
}

export async function getTaskInputOptions(
  analysisType: string,
  projectId: number,
) {
  return (
    await apiClient.get(
      `analytics/project/${projectId}/types/${analysisType}/input-options/`,
    )
  ).data;
}

export async function getTaskResults(analysisType: string, projectId: number) {
  return (
    await apiClient.get(
      `analytics/project/${projectId}/types/${analysisType}/results/`,
    )
  ).data;
}

export async function getTaskResult(resultId: number): Promise<TaskResult> {
  return (await apiClient.get(`analytics/${resultId}`)).data;
}

export async function subscribeToTaskResult(
  resultId: number,
): Promise<TaskResult> {
  return (
    await apiClient.post(`analytics/${resultId}/subscribe/`, undefined, {
      errorMsg:
        "Failed to subscribe to task result. Task may already be completed.",
    })
  ).data;
}

export async function getVectorDataBounds(vectorId: number): Promise<number[]> {
  return (await apiClient.get(`vectors/${vectorId}/bounds/`)).data;
}

export async function getLayerStyles(
  layerId: number,
  projectId: number | undefined,
): Promise<LayerStyle[]> {
  let url = `layer-styles/?layer=${layerId}`;
  if (projectId) url += `&project=${projectId}`;
  return (await apiClient.get(url)).data.results;
}

export async function getLayerStyle(styleId: number): Promise<LayerStyle> {
  return (await apiClient.get(`layer-styles/${styleId}/`)).data;
}

export async function createLayerStyle(data: LayerStyle): Promise<LayerStyle> {
  return (await apiClient.post("layer-styles/", data)).data;
}

export async function updateLayerStyle(
  styleId: number,
  data: LayerStyle,
): Promise<LayerStyle> {
  return (await apiClient.patch(`layer-styles/${styleId}/`, data)).data;
}

export async function deleteLayerStyle(styleId: number): Promise<LayerStyle> {
  return (await apiClient.delete(`layer-styles/${styleId}/`)).data;
}

export async function getProjectColormaps(
  projectId: number,
): Promise<Colormap[]> {
  return (await apiClient.get(`colormaps/?project=${projectId}`)).data.results;
}

export async function createColormap(colormap: Colormap): Promise<Colormap> {
  return (await apiClient.post(`colormaps/`, colormap)).data;
}

export async function updateColormap(colormap: Colormap): Promise<Colormap> {
  return (await apiClient.patch(`colormaps/${colormap.id}/`, colormap)).data;
}

export async function deleteColormap(colormapId: number): Promise<Colormap> {
  return (await apiClient.delete(`colormaps/${colormapId}/`)).data;
}

export async function getBookmark(bookmarkId: number): Promise<Bookmark> {
  return (
    await apiClient.get(`bookmarks/${bookmarkId}`, {
      errorMsg: "Could not load bookmark. Ensure that ID in URL is correct.",
    })
  ).data;
}

export async function getProjectBookmarks(
  projectId: number,
): Promise<Bookmark[]> {
  return (await apiClient.get(`bookmarks/?project=${projectId}`)).data.results;
}

export async function createBookmark(bookmark: Bookmark): Promise<any> {
  return (await apiClient.post("bookmarks/", bookmark)).data;
}

export async function deleteBookmark(bookmark: Bookmark): Promise<any> {
  return (await apiClient.delete(`bookmarks/${bookmark.id}/`)).data;
}

export async function getRegion(regionId: number): Promise<Region> {
  return (await apiClient.get(`regions/${regionId}/`)).data;
}

export async function createRegion(region: Region): Promise<Region> {
  return (await apiClient.post("regions/", region)).data;
}
