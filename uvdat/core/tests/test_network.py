from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytest_lazy_fixtures import lf

if TYPE_CHECKING:
    from uvdat.core.models import Dataset


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
