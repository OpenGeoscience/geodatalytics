import { defineStore } from "pinia";
import { ref, watch } from "vue";
import {
  getDatasetNetworks,
  getNetworkGCC,
  getProjectNetworks,
} from "@/api/rest";
import type {
  Dataset,
  GCCResult,
  Network,
  NetworkEdge,
  NetworkNode,
  NetworkStyle,
  NetworkState,
} from "@/types";

import { usePanelStore, useMapStore, useStyleStore, useLayerStore } from ".";

const GCCcache: GCCResult[] = [];
const networkStyle: NetworkStyle = {
  color: {
    selected: "#ffffff",
    deactivate: "#f54242",
    activate: "#008837",
    inactive: "#000000",
    gcc: "#f7e059",
  },
  opacity: {
    inactive: 0.5,
  },
};
const networkPaintProperties = [
  "circle-opacity",
  "circle-stroke-opacity",
  "line-opacity",
  "circle-color",
  "circle-stroke-color",
  "line-color",
];

function getNetworkPaintPropertyValue(
  paintProperty: string,
  networkState: NetworkState,
  defaultPropValue: any,
) {
  const deactivate = networkState.changes?.deactivate_nodes || [];
  const activate = networkState.changes?.activate_nodes || [];
  const inactive =
    networkState.deactivated?.nodes.filter(
      (n) => !deactivate.includes(n) && !activate.includes(n),
    ) || [];
  let gcc = networkState.gcc || [];
  if (!inactive.length && !deactivate.length && !activate.length) {
    gcc = []; // Network default state; don't show GCC
  }

  if (paintProperty.includes("opacity")) {
    return [
      "case",
      [
        "any",
        ["in", ["get", "node_id"], ["literal", inactive]],
        ["in", ["get", "from_node_id"], ["literal", inactive]],
        ["in", ["get", "to_node_id"], ["literal", inactive]],
      ],
      networkStyle.opacity.inactive,
      defaultPropValue,
    ];
  }

  return [
    "case",
    [
      "any",
      [
        "in",
        ["get", "node_id"],
        ["literal", networkState.selected?.nodes || []],
      ],
      [
        "in",
        ["get", "edge_id"],
        ["literal", networkState.selected?.edges || []],
      ],
    ],
    networkStyle.color.selected,
    [
      "any",
      ["in", ["get", "node_id"], ["literal", deactivate]],
      ["in", ["get", "from_node_id"], ["literal", deactivate]],
      ["in", ["get", "to_node_id"], ["literal", deactivate]],
    ],
    networkStyle.color.deactivate,
    [
      "any",
      ["in", ["get", "node_id"], ["literal", activate]],
      ["in", ["get", "from_node_id"], ["literal", activate]],
      ["in", ["get", "to_node_id"], ["literal", activate]],
    ],
    networkStyle.color.activate,
    [
      "any",
      ["in", ["get", "node_id"], ["literal", inactive]],
      ["in", ["get", "from_node_id"], ["literal", inactive]],
      ["in", ["get", "to_node_id"], ["literal", inactive]],
    ],
    networkStyle.color.inactive,
    [
      "any",
      ["in", ["get", "node_id"], ["literal", gcc]],
      ["in", ["get", "from_node_id"], ["literal", gcc]],
      ["in", ["get", "to_node_id"], ["literal", gcc]],
    ],
    networkStyle.color.gcc,
    defaultPropValue,
  ];
}

export const useNetworkStore = defineStore("network", () => {
  const panelStore = usePanelStore();
  const mapStore = useMapStore();
  const styleStore = useStyleStore();
  const layerStore = useLayerStore();

  const loadingNetworks = ref<boolean>(false);
  const availableNetworks = ref<Network[]>([]);
  const currentNetwork = ref<Network>();
  const networkStates = ref<Record<number, NetworkState>>({});

  // These are only used in NetworksPanel.vue, but must be here
  // so the state persists when the panel is moved around
  const currentNetworkNodes = ref<NetworkNode[]>([]);
  const currentNetworkEdges = ref<NetworkEdge[]>([]);

  watch(currentNetwork, () => {
    currentNetworkNodes.value = [];
    currentNetworkEdges.value = [];
    if (currentNetwork.value) {
      resetNetworkState(currentNetwork.value.id);
    }
  });

  // Actions
  async function initNetworks(projectId: number) {
    loadingNetworks.value = true;
    const networks = await getProjectNetworks(projectId);
    availableNetworks.value = networks;
    currentNetwork.value = undefined;
    loadingNetworks.value = false;
    networks.forEach((n) => resetNetworkState(n.id));
  }

  function resetNetworkState(networkId: number) {
    networkStates.value[networkId] = {
      selected: { nodes: [], edges: [] },
      deactivated: { nodes: [], edges: [] },
      changes: {
        deactivate_nodes: [],
        activate_nodes: [],
      },
      gcc: null,
    };
  }

  async function getNetwork(
    nodeId: number,
    dataset: Dataset,
  ): Promise<Network | undefined> {
    let network: Network | undefined;
    availableNetworks.value.forEach((net) => {
      if (net.nodes.includes(nodeId)) {
        network = net;
      }
    });
    if (!network) {
      availableNetworks.value = [
        ...availableNetworks.value,
        ...(await getDatasetNetworks(dataset.id)).filter((net) => {
          return !availableNetworks.value.map((n) => n.id).includes(net.id);
        }),
      ];
    }
    availableNetworks.value.forEach((net) => {
      if (net.nodes.includes(nodeId)) {
        network = net;
      }
    });
    if (availableNetworks.value.length) {
      panelStore.panelArrangement = panelStore.panelArrangement.map((panel) => {
        if (panel.id === "networks") panel.visible = true;
        return panel;
      });
    }
    currentNetwork.value = network;
    return network;
  }

  async function isNodeActive(nodeId: number, dataset: Dataset) {
    const network = await getNetwork(nodeId, dataset);
    if (network) {
      const deactivated = Array.from(
        networkStates.value[network.id]?.deactivated?.nodes || [],
      );
      return !deactivated.includes(nodeId);
    }
  }

  async function toggleNodeActive(nodeId: number, dataset: Dataset) {
    const network = await getNetwork(nodeId, dataset);
    if (network) {
      let deactivated = Array.from(
        networkStates.value[network.id]?.deactivated?.nodes || [],
      );
      if (!deactivated.includes(nodeId)) {
        deactivated.push(nodeId);
      } else {
        deactivated = deactivated.filter((id) => id !== nodeId);
      }
      await setNetworkDeactivatedNodes(network, deactivated);
    }
  }

  async function setNetworkDeactivatedNodes(
    network: Network,
    nodeIds: number[],
    animation = false,
  ) {
    if (!networkStates.value[network.id]) resetNetworkState(network.id);
    const networkState = networkStates.value[network.id];
    if (!networkState.deactivated)
      networkState.deactivated = { nodes: [], edges: [] };
    if (animation) {
      networkState.changes = {
        deactivate_nodes: nodeIds.filter(
          (n) => !networkState.deactivated?.nodes.includes(n),
        ),
        activate_nodes: networkState.deactivated.nodes.filter(
          (n) => !nodeIds.includes(n),
        ),
      };
    }
    networkState.deactivated.nodes = Array.from(nodeIds);
    if (nodeIds.length && nodeIds.length < 1000) {
      const cachedResult = GCCcache.find(
        (result) =>
          JSON.stringify(result.deactivatedNodes.toSorted()) ===
          JSON.stringify(nodeIds.toSorted()),
      );
      if (cachedResult) networkState.gcc = cachedResult.gcc;
      else {
        networkState.gcc = await getNetworkGCC(
          network.id,
          networkState.deactivated.nodes,
        );
        GCCcache.push({
          deactivatedNodes: nodeIds,
          gcc: networkState.gcc,
        });
      }
    } else {
      networkState.gcc = [];
    }
    networkStates.value[network.id] = networkState;
    styleNetwork(network);
  }

  function styleVisibleNetworks() {
    const visibleVectorIds = new Set(
      mapStore
        .getUserMapLayers()
        .map((id) => mapStore.parseLayerString(id))
        .filter((info) => info.type === "vector")
        .map((info) => info.typeId),
    );
    availableNetworks.value.forEach((network) => {
      if (visibleVectorIds.has(network.vector_data)) {
        styleNetwork(network);
      }
    });
  }

  function styleNetwork(network: Network) {
    const networkState = networkStates.value[network.id];
    const map = mapStore.getMap();
    mapStore.getUserMapLayers().forEach((mapLayerId) => {
      const layerInfo = mapStore.parseLayerString(mapLayerId);
      if (!(
        layerInfo.type === "vector" && layerInfo.typeId === network.vector_data
      )) {
        // No-op for map layers that do not correspond to the Network's VectorData object
        return;
      }
      const currentStyleSpec =
        styleStore.selectedLayerStyles[
          `${layerInfo.layerId}.${layerInfo.layerCopyId}`
        ].style_spec;
      const frames = layerStore.framesByLayerId[layerInfo.layerId];
      const currentFrame = frames.find((f) => f.id === layerInfo.frameId);
      if (!(currentStyleSpec && currentFrame)) {
        // Must have current style to use as default and current frame to get vector feature properties
        return;
      }
      networkPaintProperties.forEach((paintProperty) => {
        if (!paintProperty.includes(layerInfo.layerType)) {
          // No-op for paint properties that do not match the current layer's type (i.e. line-color for point layer)
          return;
        }
        let defaultPropValue: any = currentStyleSpec?.opacity;
        if (paintProperty.includes("color")) {
          const groupName = layerInfo.layerType === "line" ? "lines" : "points";
          const propsSpec = currentFrame.vector?.summary?.properties;
          if (propsSpec) {
            defaultPropValue = styleStore.getVectorColorPaintProperty(
              currentStyleSpec,
              groupName,
              propsSpec,
              styleStore.colormaps,
              paintProperty.includes("stroke"),
            );
          } else {
            defaultPropValue = "black";
          }
        }
        const paintPropertyValue = getNetworkPaintPropertyValue(
          paintProperty,
          networkState,
          defaultPropValue,
        );
        map.setPaintProperty(mapLayerId, paintProperty, paintPropertyValue);
      });
    });
  }

  return {
    availableNetworks,
    currentNetwork,
    networkStates,
    loadingNetworks,
    currentNetworkNodes,
    currentNetworkEdges,
    initNetworks,
    getNetwork,
    isNodeActive,
    toggleNodeActive,
    setNetworkDeactivatedNodes,
    styleVisibleNetworks,
    styleNetwork,
  };
});
