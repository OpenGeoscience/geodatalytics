from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from django.core.files.base import File
from django.core.files.storage import default_storage
import pytest
from pytest_lazy_fixtures import lf

from uvdat.core.models import VectorData, VectorFeature

if TYPE_CHECKING:
    from collections.abc import Callable

SAMPLE_GEOJSON = Path(__file__).parent / "data" / "sample_geo.json"


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [(lf("api_client"), 401), (lf("authenticated_api_client"), 201)],
)
@pytest.mark.django_db
def test_create_vector_data(
    dataset,
    client,
    expected_status,
    s3ff_field_value_factory: Callable[[File[bytes]], str],
):
    with SAMPLE_GEOJSON.open("rb") as f:
        key = default_storage.save("sample_geo.json", File(file=f, name="sample_geo.json"))
    with default_storage.open(key) as stored:
        s3ff_value = s3ff_field_value_factory(stored)

    expected = {
        "dataset": dataset.id,
        "name": "Sample vector",
        "geojson_data": s3ff_value,
    }
    resp = client.post("/api/v1/vectors/", expected)
    assert resp.status_code == expected_status
    if expected_status == 201:
        data = resp.json()
        assert data["dataset"] == dataset.id
        assert data["name"] == "Sample vector"
        assert "sample_geo" in data["geojson_data"]
        vector = VectorData.objects.get(id=data["id"])
        assert VectorFeature.objects.filter(vector_data=vector).count() == 3
