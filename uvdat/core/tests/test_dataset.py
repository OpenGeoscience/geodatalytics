from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.files.base import File
import pytest
from pytest_lazy_fixtures import lf

if TYPE_CHECKING:
    from uvdat.core.models.project import Dataset


@pytest.mark.parametrize(
    "client",
    [lf("api_client"), lf("authenticated_api_client")],
)
@pytest.mark.django_db
def test_rest_dataset_list_retrieve(client, dataset: Dataset, project_factory):
    project = project_factory(allow_unauthenticated=True)
    project.datasets.add(dataset)
    resp = client.get("/api/v1/datasets/")
    assert len(resp.json()["results"]) == 1
    assert resp.json()["results"][0]["id"] == dataset.id

    resp = client.get(f"/api/v1/datasets/{dataset.id}/")
    assert resp.json()["id"] == dataset.id


@pytest.mark.parametrize(
    "client",
    [lf("api_client"), lf("authenticated_api_client")],
)
@pytest.mark.django_db
def test_rest_dataset_layers(client, dataset_factory, layer_factory, project_factory):
    dataset = dataset_factory()
    project = project_factory(allow_unauthenticated=True)
    project.datasets.add(dataset)
    layers = [layer_factory(dataset=dataset) for _ in range(3)]

    resp = client.get(f"/api/v1/datasets/{dataset.id}/layers/")
    assert resp.status_code == 200

    data: list[dict] = resp.json()
    assert len(data) == 3

    # Assert these lists are the same objects
    assert sorted([x["id"] for x in data]) == sorted([x.id for x in layers])


@pytest.mark.parametrize(
    "client",
    [lf("api_client"), lf("authenticated_api_client")],
)
@pytest.mark.django_db
def test_rest_dataset_data_objects(
    client, dataset_factory, vector_data_factory, raster_data_factory, project_factory
):
    dataset = dataset_factory()
    project = project_factory(allow_unauthenticated=True)
    project.datasets.add(dataset)
    data_objects = [
        *[vector_data_factory(dataset=dataset) for _ in range(3)],
        *[raster_data_factory(dataset=dataset) for _ in range(3)],
    ]

    resp = client.get(f"/api/v1/datasets/{dataset.id}/data/")
    assert resp.status_code == 200

    data: list[dict] = resp.json()
    assert len(data) == 6

    # Assert these lists are the same objects
    assert sorted([x["id"] for x in data]) == sorted([x.id for x in data_objects])


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [(lf("api_client"), 401), (lf("authenticated_api_client"), 201)],
)
@pytest.mark.django_db
def test_rest_create_dataset(client, expected_status, user):
    dataset_expected = {
        "name": "My Test Dataset",
        "description": "created to test dataset uploads",
        "category": "test",
        "tags": ["boston", "flood", "simulation"],
        "metadata": {"source": "pytest"},
    }
    resp = client.post("/api/v1/datasets/", dataset_expected)
    assert resp.status_code == expected_status
    if expected_status == 201:
        serialized_dataset = resp.json()
        for key, value in dataset_expected.items():
            assert serialized_dataset[key] == value
        assert "id" in serialized_dataset
        assert serialized_dataset["owner"]["id"] == user.id


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [(lf("api_client"), 401), (lf("authenticated_api_client"), 200)],
)
@pytest.mark.django_db
def test_rest_convert_dataset(
    file_item_factory, multiframe_vector_file, client, expected_status, project, user
):
    with multiframe_vector_file["path"].open("rb") as f:
        file_item = file_item_factory(
            file=File(f),
            name=multiframe_vector_file["name"],
            file_type=multiframe_vector_file["file_type"],
        )
    dataset = file_item.dataset
    project.set_collaborators([user])
    project.datasets.set([dataset])

    result_expected = {
        "task_type": "conversion",
        "inputs": {
            "dataset_id": dataset.id,
            "layer_options": [{"name": "Multiframe Vector Test", "frame_property": "frame"}],
            "network_options": None,
            "region_options": None,
        },
        "status": "Initializing task...",
        "outputs": None,
        "error": "",
        "completed": None,
        "project": None,
    }
    resp = client.post(f"/api/v1/datasets/{dataset.id}/convert/", result_expected.get("inputs"))
    assert resp.status_code == expected_status
    if expected_status == 200:
        serialized_result = resp.json()
        for key, value in result_expected.items():
            assert serialized_result[key] == value
        assert "id" in serialized_result

        # Check that one Layer was created
        resp = client.get(f"/api/v1/datasets/{dataset.id}/layers/")
        serialized_layers = resp.json()
        assert len(serialized_layers) == 1
        assert "id" in serialized_layers[0]
        layer_id = serialized_layers[0]["id"]

        # Check that 39 LayerFrames were created
        resp = client.get(f"/api/v1/layers/{layer_id}/frames/")
        serialized_frames = resp.json()
        assert len(serialized_frames) == 39


@pytest.mark.django_db
def test_dataset_set_owner(dataset, user):
    owner = dataset.owner()
    assert owner.id != user.id

    dataset.set_owner(user)
    assert dataset.owner().id == user.id


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [(lf("api_client"), 401), (lf("authenticated_api_client"), 403)],
)
@pytest.mark.django_db
def test_rest_dataset_edit(client, expected_status, user, dataset: Dataset):
    patch = {"name": "New Name"}
    resp = client.patch(f"/api/v1/datasets/{dataset.id}/", patch)
    assert resp.status_code == expected_status

    if expected_status == 403:
        dataset.set_owner(user)
        resp = client.patch(f"/api/v1/datasets/{dataset.id}/", patch)
        assert resp.status_code == 200

        dataset.refresh_from_db()
        assert dataset.name == patch["name"]


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [(lf("api_client"), 401), (lf("authenticated_api_client"), 403)],
)
@pytest.mark.django_db
def test_rest_dataset_delete(client, expected_status, user, dataset: Dataset):
    resp = client.delete(f"/api/v1/datasets/{dataset.id}/")
    assert resp.status_code == expected_status

    if expected_status == 403:
        dataset.set_owner(user)
        resp = client.delete(f"/api/v1/datasets/{dataset.id}/")
        assert resp.status_code == 204


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [(lf("api_client"), 401), (lf("authenticated_api_client"), 400)],
)
@pytest.mark.django_db
def test_rest_dataset_invalid_tags(client, expected_status):
    dataset_expected = {
        "name": "My Test Dataset",
        "description": "created to test dataset uploads",
        "category": "test",
        "tags": "invalid",
        "metadata": {"source": "pytest"},
    }
    resp = client.post("/api/v1/datasets/", dataset_expected)
    assert resp.status_code == expected_status
    if expected_status == 400:
        assert resp.json() == {"tags": ["Dataset tags must be expressed as a list of strings."]}
