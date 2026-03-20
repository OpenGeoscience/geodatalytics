import type { MapGeoJSONFeature, StyleSpecification } from "maplibre-gl";

export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_superuser: boolean;
}

export interface Basemap {
  id?: number;
  name: string;
  style?: string | StyleSpecification;
}

export interface Dataset {
  id: number;
  name?: string;
  description?: string;
  category?: string;
  tags?: string[];
  processing?: boolean;
  layers?: Layer[];
  metadata?: Record<string, any>;
  owner?: User;
  n_layers?: number;
}

export interface Layer {
  id: number;
  copy_id: number;
  name: string;
  dataset: number;
  frames?: LayerFrame[];
  metadata: Record<string, any>;
  visible: boolean;
  current_frame_index: number;
  default_style: LayerStyle | null;
}

export interface LayerFrame {
  id: number;
  name: string;
  index: number;
  layer: Layer;
  vector: VectorData | null;
  raster: RasterData | null;
  source_filters: Record<string, any>;
}

export interface VectorSummary {
  feature_types: string[];
  properties: Record<string, PropertySummary>;
  color_props_coverage: 'full' | 'partial' | 'none';
}

export interface PropertySummary {
  value_set: (number | string | null)[],
  count: number;
  types: string[],
  range?: [number, number],
  sample_label: string,
}

export interface Colormap {
  id?: number;
  project?: number | null;
  name?: string;
  markers?: {
    color: string;
    value: number;
  }[]
}

export interface AppliedColormap {
  id?: number;
  discrete?: boolean;
  n_colors?: number;
  color_by?: string;
  range?: [number, number],
  clamp?: boolean,
  null_color?: string;
}

export interface StyleFilter {
  id?: number;
  filter_by?: string;
  include: boolean;
  transparency: boolean;
  apply?: boolean;
  list?: any[];
  range?: number[];
}

export interface StyleSpec {
  default_frame: number;
  opacity: number;
  colors: {
    name: string;
    visible: boolean;
    use_feature_props: boolean;
    single_color?: string;
    colormap?: AppliedColormap,
  }[],
  sizes: {
    name: string;
    zoom_scaling: boolean;
    single_size?: number;
    size_range?: {
      size_by?: string;
      null_size?: {
        transparency: boolean,
        size: number,
      };
      minimum: number;
      maximum: number;
    }
  }[],
  filters: StyleFilter[]
}

export interface LayerStyle {
  id?: number;
  name: string;
  layer?: number;
  project?: number;
  is_default: boolean;
  style_spec?: StyleSpec;
}

export interface VectorData {
  id: number;
  name: string;
  dataset: number;
  geojson_data: string | null;
  source_file: null | number;
  file_size: number;
  summary?: VectorSummary,
  metadata?: Record<string, any>;

}

export interface RasterData {
  id: number;
  name: string;
  cloud_optimized_geotiff: string | null;
  dataset: number;
  source_file: null | number;
  file_size: number;
  metadata: RasterMetadata;
}

export interface RasterMetadata {
  bandCount: number;
  bands: Record<number, {
    interpretation: string;
    max: number;
    min: number;
    mean: number;
    stdev: number;
  }>;
  bounds: {
    srs: string;
    ll: {x: number; y: number};
    lr: {x: number; y: number};
    ul: {x: number; y: number};
    ur: {x: number; y: number};
    xmin: number;
    xmax: number;
    ymin: number;
    ymax: number;
  };
  sourceBounds: {
    srs: string;
    ll: {x: number; y: number};
    lr: {x: number; y: number};
    ul: {x: number; y: number};
    ur: {x: number; y: number};
    xmin: number;
    xmax: number;
    ymin: number;
    ymax: number;
  };
  dtype: string;
  geospatial: boolean;
  levels: number;
  sourceLevels: number;
  magnification: number | null;
  mm_x: number;
  mm_y: number;
  projection: string | null;
  sizeX: number;
  sizeY: number;
  sourceSizeX: number;
  sourceSizeY: number;
  tileWidth: number;
  tileHeight: number;
  source_filenames: string[];
  uploaded: string;
}

export interface RasterDataValues {
  sourceBounds: {
    xmax: number;
    xmin: number;
    ymax: number;
    ymin: number;
  };
  data: number[][];
}

export interface SourceRegion {
  id: number;
  name?: string;
  dataset_id?: number;
  metadata?: object;
  boundary?: object;
}

export interface Project {
  id: number;
  name: string;
  default_map_center: [number, number];
  default_map_zoom: number;
  datasets: number[];
  created: string;
  modified: string;
  owner: User;
  collaborators: User[];
  followers: User[];
  item_counts: {
    datasets: number;
    regions: number;
    charts: number;
    analyses: number;
  };
}

export interface ProjectPatch {
  name?: string;
  datasets?: number[];
  default_map_center?: number[];
  default_map_zoom?: number;
}

export interface ProjectPermissions {
  owner_id: number;
  collaborator_ids: number[];
  follower_ids: number[];
}

export interface Feature {
  type: string;
  geometry: {
    [key: string]: string | object;
  };
  properties: {
    [key: string]: string | object;
  };
}

export interface ClickedFeatureData {
  pos: { lng: number; lat: number; };
  feature: MapGeoJSONFeature;
}

export interface MapLibreLayerMetadata {
  layer_id: number;
  layer_copy_id: number;
  frame_id: number;
  multiFrame: boolean;
}

export type MapLibreLayerWithMetadata = MapGeoJSONFeature["layer"] & {
  metadata: MapLibreLayerMetadata;
}

export interface Network {
  id: number;
  name: string;
  dataset: number;
  category: string;
  nodes: number[];
  metadata: Record<string, any>;
  vector_data: number;
}

export interface NetworkNode {
  id: number;
  name: string;
  network: number;
  metadata: object;
  capacity: number | null;
  location: number[];
  active?: boolean;
}

export interface NetworkEdge {
  id: number;
  name: string;
  network: number;
  metadata: object;
  capacity: number | null;
  line_geometry: object;
  directed: boolean;
  from_node: number;
  to_node: number;
  active: boolean;
}

export interface NetworkStyle {
  opacity: {
    inactive: number,
  },
  color: {
    inactive: string,
    deactivate: string,
    activate: string,
    gcc: string,
    selected: string,
  }
}

export interface NetworkState {
  selected?: {
    nodes: number[];
    edges: number[];
  },
  deactivated?: {
    nodes: number[];
    edges: number[];
  };
  changes?: {
    deactivate_nodes: number[];
    activate_nodes: number[];
  }
  gcc: number[] | null;
}

export interface GCCResult {
  deactivatedNodes: number[];
  gcc: number[];
}

export interface VectorTile {
  id: number;
  map_layer: number;
  geojson_data: object;
  x: number;
  y: number;
  z: number;
}

export interface Chart {
  id: number;
  name: string;
  description: string;
  project: number;
  metadata: object;
  chart_data: {
    labels: string[];
    datasets: {
      data: number[];
    }[];
  };
  chart_options: {
    chart_title: string;
    x_title: string;
    y_title: string;
    x_range: number[];
    y_range: number[];
  };
  editable: boolean;
}

export interface ChartOptions {
  plugins: {
    title?: object;
  };
  scales: {
    x?: {
      min?: number;
      max?: number;
      title?: {
        display?: boolean;
        text: string;
      };
    };
    y?: {
      min?: number;
      max?: number;
      title?: {
        display?: boolean;
        text: string;
      };
    };
  };
}

export interface AnalysisType {
  id: number;
  name: string;
  db_value: string;
  description: string;
  details: string;
  attribution: string;
  input_options: Record<string, any>;
  input_types: Record<string, any>;
  output_types: Record<string, any>;
}

export interface TaskResult {
  id: number;
  name: string;
  task_type: string;
  project: number;
  inputs: Record<string, any>;
  outputs: Record<string, any>;
  status: string;
  error: string;
  created: string;
  completed: string;
  subscribers: number[];
}

export interface FloatingPanelConfig {
  id: string;
  label: string;
  visible: boolean;
  closeable: boolean;
  collapsed?: boolean;
  dock: 'left' | 'right';
  order: number;
  position?: { x: number; y: number } | undefined;
  width?: number | undefined;
  height?: number | undefined;
  element?: HTMLElement;
}

export interface FileItem {
  id: number;
  name: string;
  chart?: Chart;
  dataset?: Dataset;
  created: string;
  modified: string;
  file: string;
  file_size: number;
  file_type: string;
  index: number;
  metadata: Record<string, any>;
}

export interface ViewState {
  id?: number;
  name?: string;
  project: number;
  thumbnail?: string;
  current_analysis_type: string | undefined,
  current_result: number | undefined,
  current_chart: number | undefined,
  current_basemap: number | undefined,
  current_network: number | undefined,
  selected_layers: (number | undefined)[],
  selected_layer_current_frames: Record<string, number>,
  selected_layer_order: string[],
  selected_layer_styles: Record<string, LayerStyle>,
  left_sidebar_open: boolean,
  right_sidebar_open: boolean,
  panel_arrangement: FloatingPanelConfig[],
  theme: "dark" | "light",
  map_center: number[],
  map_zoom: number,
}
