from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

import pytest
from pytest_lazy_fixtures import lf

if TYPE_CHECKING:
    from uvdat.core.models import Dataset, Network, NetworkNode, Project


@pytest.mark.parametrize(
    "client",
    [lf("api_client"), lf("authenticated_api_client")],
)
@pytest.mark.django_db
def test_rest_dataset_networks_no_network(client, dataset: Dataset, project_factory):
    project = project_factory(allow_unauthenticated=True)
    project.datasets.add(dataset)
    resp = client.get(f"/api/v1/datasets/{dataset.id}/networks/")
    assert resp.status_code == 200
    assert not resp.json()


@pytest.mark.parametrize(
    "client",
    [lf("api_client"), lf("authenticated_api_client")],
)
@pytest.mark.django_db
def test_rest_dataset_networks(client, project_factory, network_edge):
    network = network_edge.network
    dataset = network.vector_data.dataset
    project = project_factory(allow_unauthenticated=True)
    project.datasets.add(dataset)
    assert network_edge.from_node != network_edge.to_node

    resp = client.get(f"/api/v1/datasets/{dataset.id}/networks/")
    assert resp.status_code == 200

    data: list[dict] = resp.json()
    assert len(data) == 1
    assert data[0]["counts"]["nodes"] == 2


@pytest.mark.django_db
def test_create_network_animation(
    authenticated_api_client,
    user,
    project: Project,
    network: Network,
    network_edge_factory,
    network_node_factory,
):
    dataset = network.vector_data.dataset
    project.set_owner(user)
    project.datasets.add(dataset)

    # Create two groups of nodes that fully connected
    group_a = [network_node_factory(network=network) for _ in range(3)]
    for from_node, to_node in itertools.combinations(group_a, 2):
        network_edge_factory(network=network, from_node=from_node, to_node=to_node)

    group_b = [network_node_factory(network=network) for _ in range(2)]
    for from_node, to_node in itertools.combinations(group_b, 2):
        network_edge_factory(network=network, from_node=from_node, to_node=to_node)

    # Join these two groups by a single node
    connecting_node: NetworkNode = network_node_factory(network=network)
    network_edge_factory(network=network, from_node=group_a[0], to_node=connecting_node)
    network_edge_factory(network=network, from_node=group_b[0], to_node=connecting_node)

    # Network should look like this
    #  *             *
    #  |             |
    #  * ---- * ---- *
    #  |
    #  *

    # Create animation
    resp_1 = authenticated_api_client.post(
        "/api/v1/network-animations/",
        {
            "name": "Test Anim",
            "network": network.id,
            "project": project.id,
        },
    )
    assert resp_1.status_code == 201
    anim = resp_1.json()

    # First state in animation should be created by default
    resp_2 = authenticated_api_client.get(f"/api/v1/network-states/?animation={anim.get('id')}")
    assert resp_2.status_code == 200
    states = resp_2.json().get("results")
    assert len(states) == 1
    state = states[0]

    # State should have no deactivated nodes and one component with all nodes
    assert len(state.get("deactivated_nodes")) == 0
    assert len(state.get("components")) == 1
    assert len(state.get("components")[0].get("nodes")) == 6

    # Update deactivated nodes for first state
    resp_3 = authenticated_api_client.patch(
        f"/api/v1/network-states/{state.get('id')}/", {"deactivated_nodes": [connecting_node.id]}
    )
    assert resp_3.status_code == 200
    state = resp_3.json()

    # Now state should have one deactivated node and two components
    assert len(state.get("deactivated_nodes")) == 1
    assert len(state.get("components")) == 2
    # Components should be sorted by their sizes
    assert len(state.get("components")[0].get("nodes")) == 3
    assert len(state.get("components")[1].get("nodes")) == 2
