<script setup lang="ts">
import { ref, computed, watch } from "vue";
import DetailView from "../DetailView.vue";
import type { NetworkEdge, NetworkNode } from "@/types";

import { useNetworkStore, usePanelStore } from "@/store";
import { getNetworkEdges, getNetworkNodes } from "@/api/rest";
const networkStore = useNetworkStore();
const panelStore = usePanelStore();

const searchText = ref<string | undefined>();
const filteredNetworks = computed(() => {
  return networkStore.availableNetworks?.filter((network) => {
    return (
      !searchText.value ||
      network.name.toLowerCase().includes(searchText.value.toLowerCase())
    );
  });
});
const networkState = computed(() => {
  if (networkStore.currentNetwork) {
    return networkStore.networkStates[networkStore.currentNetwork.id];
  }
  return undefined;
});

const tab = ref();
const hoverNode = ref<NetworkNode>();
const hoverEdge = ref<NetworkEdge>();
const selectedNodes = ref<number[]>([]);
const limit = 100;

const currentNodes = computed(() =>
  networkStore.currentNetworkNodes.map((n) => ({
    ...n,
    active: !networkState.value?.deactivated?.nodes?.includes(n.id),
  })),
);

const currentEdges = computed(() =>
  networkStore.currentNetworkEdges.map((e) => ({
    ...e,
    active:
      !networkState.value?.deactivated?.nodes?.includes(e.from_node) &&
      !networkState.value?.deactivated?.nodes?.includes(e.to_node),
  })),
);

const headers = [
  { title: "", value: "active", sortable: true, width: 10 },
  { title: "Name", value: "name", sortable: true },
  { title: "", value: "metadata", sortable: false, width: 10 },
];

async function loadNodes({ done }: any) {
  if (networkStore.currentNetwork) {
    const response = await getNetworkNodes(
      networkStore.currentNetwork.id,
      limit,
      networkStore.currentNetworkNodes.length,
    );
    networkStore.currentNetworkNodes = [
      ...networkStore.currentNetworkNodes,
      ...response,
    ];
    if (response.length < limit) done("empty");
    else done("ok");
  }
}

async function loadEdges({ done }: any) {
  if (networkStore.currentNetwork) {
    const response = await getNetworkEdges(
      networkStore.currentNetwork.id,
      limit,
      networkStore.currentNetworkEdges.length,
    );
    networkStore.currentNetworkEdges = [
      ...networkStore.currentNetworkEdges,
      ...response,
    ];
    if (response.length < limit) done("empty");
    else done("ok");
  }
}

function showNetwork() {
  if (networkStore.currentNetwork) {
    panelStore.show({ network: networkStore.currentNetwork });
  }
}

function isNetworkVisible() {
  if (networkStore.currentNetwork) {
    return panelStore.isVisible({ network: networkStore.currentNetwork });
  }
  return true;
}

function resetNetwork() {
  if (networkStore.currentNetwork) {
    selectedNodes.value = [];
    networkStore.setNetworkDeactivatedNodes(networkStore.currentNetwork, []);
  }
}

function toggleSelected() {
  if (networkStore.currentNetwork && networkState.value) {
    if (!isNetworkVisible()) showNetwork();

    // Any selected nodes that are already deactivated should be removed
    // from both sets, since they now need to be activated, and both sets
    // are used to set the new deactivated value.
    let deactiveNodeSet = new Set(networkState.value.deactivated?.nodes);
    let selectedNodeSet = new Set(selectedNodes.value);
    const nodesToRemove = deactiveNodeSet.intersection(selectedNodeSet);
    deactiveNodeSet = deactiveNodeSet.difference(nodesToRemove);
    selectedNodeSet = selectedNodeSet.difference(nodesToRemove);

    const deactivated = Array.from(deactiveNodeSet.union(selectedNodeSet));
    networkStore.setNetworkDeactivatedNodes(
      networkStore.currentNetwork,
      deactivated,
    );
    selectedNodes.value = [];
  }
}

// Clear search text when network changes
watch(
  () => networkStore.currentNetwork,
  () => {
    searchText.value = "";
  },
);

watch(
  [selectedNodes, hoverNode, hoverEdge],
  () => {
    if (networkStore.currentNetwork && networkState.value) {
      if (!networkState.value.selected) {
        networkState.value.selected = { nodes: [], edges: [] };
      }
      if (hoverNode.value) {
        networkState.value.selected.nodes = [
          ...selectedNodes.value,
          hoverNode.value.id,
        ];
      } else if (hoverEdge.value) {
        networkState.value.selected.edges = [hoverEdge.value.id];
      } else {
        networkState.value.selected.nodes = selectedNodes.value;
      }
      networkStore.styleNetwork(networkStore.currentNetwork);
    }
  },
  { deep: true },
);
</script>

<template>
  <div
    :class="
      networkStore.currentNetwork
        ? 'panel-content-outer'
        : 'panel-content-outer with-search'
    "
  >
    <v-text-field
      v-if="!networkStore.currentNetwork"
      v-model="searchText"
      label="Search Networks"
      variant="outlined"
      density="compact"
      class="mb-2"
      append-inner-icon="mdi-magnify"
      hide-details
    />
    <v-card class="panel-content-inner">
      <div v-if="networkStore.currentNetwork">
        <div class="network-title">
          <div>
            <div>{{ networkStore.currentNetwork.name }}</div>
            <v-btn
              v-if="!isNetworkVisible()"
              density="compact"
              @click="showNetwork()"
            >
              Show
            </v-btn>
            <v-btn density="compact" @click="resetNetwork()"> Reset </v-btn>
          </div>
          <v-btn
            v-tooltip="'Close'"
            icon="mdi-close"
            variant="plain"
            @click="networkStore.currentNetwork = undefined"
          />
        </div>
        <v-text-field
          v-model="searchText"
          label="Search Nodes and Edges"
          variant="outlined"
          density="compact"
          class="mb-2"
          append-inner-icon="mdi-magnify"
          hide-details
        />
        <v-tabs v-model="tab" align-tabs="center" fixed-tabs>
          <v-tab value="nodes-tab">Nodes</v-tab>
          <v-tab value="edges-tab">Edges</v-tab>
        </v-tabs>

        <v-window v-model="tab">
          <v-window-item value="nodes-tab">
            <v-data-table
              v-model="selectedNodes"
              :items="currentNodes"
              :headers="headers"
              :search="searchText"
              items-per-page="-1"
              item-value="id"
              class="transparent"
              show-select
              hide-default-footer
              @mouseover:row="(e: Event, data: any) => (hoverNode = data.item)"
              @mouseleave:row="() => (hoverNode = undefined)"
            >
              <template #item.active="{ item }">
                <v-icon
                  :icon="item.active ? 'mdi-circle-outline' : 'mdi-close'"
                  :color="item.active ? 'green' : 'red'"
                />
              </template>
              <template #item.metadata="{ item }">
                <DetailView :details="{ ...item, type: 'networknode' }" />
              </template>
              <template #bottom>
                <v-infinite-scroll @load="loadNodes">
                  <template #loading>
                    <v-progress-linear indeterminate />
                  </template>
                  <template #empty />
                </v-infinite-scroll>
              </template>
            </v-data-table>
          </v-window-item>
          <v-window-item value="edges-tab">
            <v-data-table
              :items="currentEdges"
              :headers="headers"
              :search="searchText"
              items-per-page="-1"
              class="transparent"
              item-value="id"
              hide-default-footer
              @mouseover:row="(e: Event, data: any) => (hoverEdge = data.item)"
              @mouseleave:row="() => (hoverEdge = undefined)"
            >
              <template #item.active="{ item }">
                <v-icon
                  :icon="item.active ? 'mdi-circle-outline' : 'mdi-close'"
                  :color="item.active ? 'green' : 'red'"
                />
              </template>
              <template #item.metadata="{ item }">
                <DetailView :details="{ ...item, type: 'networkedge' }" />
              </template>
              <template #bottom>
                <v-infinite-scroll @load="loadEdges">
                  <template #loading>
                    <v-progress-linear indeterminate />
                  </template>
                  <template #empty />
                </v-infinite-scroll>
              </template>
            </v-data-table>
          </v-window-item>
        </v-window>
      </div>
      <div v-else-if="filteredNetworks?.length">
        <v-list density="compact">
          <v-list-item
            v-for="network in filteredNetworks"
            :key="network.id"
            @click="networkStore.currentNetwork = network"
          >
            {{ network.name }}
            <template #append>
              <v-icon
                icon="mdi-transit-connection-variant"
                size="small"
                class="ml-2"
              ></v-icon>
              <DetailView :details="{ ...network, type: 'network' }" />
            </template>
          </v-list-item>
        </v-list>
      </div>
      <v-progress-linear
        v-else-if="networkStore.loadingNetworks"
        indeterminate
      ></v-progress-linear>
      <v-card-text v-else class="help-text">No available Networks.</v-card-text>
    </v-card>
    <v-btn
      v-if="
        networkStore.currentNetwork &&
        tab == 'nodes-tab' &&
        selectedNodes.length
      "
      class="toggle-btn"
      @click="toggleSelected"
    >
      Toggle Selected
    </v-btn>
  </div>
</template>

<style>
.network-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
}
.toggle-btn {
  position: absolute !important;
  bottom: 20px;
  right: 15px;
  z-index: 1;
}
.v-data-table__td {
  padding: 0px 4px !important;
}
</style>
