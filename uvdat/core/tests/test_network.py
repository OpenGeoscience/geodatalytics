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
    assert len(data[0]["nodes"]) == 2


@pytest.mark.django_db
def test_rest_network_gcc_empty(authenticated_api_client, user, project: Project, network: Network):
    dataset = network.vector_data.dataset
    project.set_owner(user)
    project.datasets.add(dataset)
    resp = authenticated_api_client.get(f"/api/v1/networks/{network.id}/gcc/?exclude_nodes=1")

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.parametrize("group_sizes", [(3, 2), (20, 3)])
@pytest.mark.django_db
def test_rest_network_gcc(
    authenticated_api_client,
    user,
    project: Project,
    network: Network,
    network_edge_factory,
    network_node_factory,
    group_sizes,
):
    dataset = network.vector_data.dataset
    project.set_owner(user)
    project.datasets.add(dataset)
    group_a_size, group_b_size = group_sizes

    # Create two groups of nodes that fully connected
    group_a = [network_node_factory(network=network) for _ in range(group_a_size)]
    for from_node, to_node in itertools.combinations(group_a, 2):
        network_edge_factory(network=network, from_node=from_node, to_node=to_node)

    group_b = [network_node_factory(network=network) for _ in range(group_b_size)]
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

    resp = authenticated_api_client.get(
        f"/api/v1/networks/{network.id}/gcc/?exclude_nodes={connecting_node.id}"
    )

    larger_group: list[NetworkNode] = max(group_a, group_b, key=len)
    assert resp.status_code == 200
    assert sorted(resp.json()) == sorted([n.id for n in larger_group])
