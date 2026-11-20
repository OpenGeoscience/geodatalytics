from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from django.core.files.base import File
from django.core.files.storage import default_storage
import pytest
from pytest_lazy_fixtures import lf

from uvdat.core.models import RasterData

if TYPE_CHECKING:
    from collections.abc import Callable

SAMPLE_COG = Path(__file__).parent / "data" / "sample_cog.tif"


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [(lf("api_client"), 401), (lf("authenticated_api_client"), 201)],
)
@pytest.mark.django_db
def test_create_raster_data(
    dataset,
    client,
    expected_status,
    s3ff_field_value_factory: Callable[[File[bytes]], str],
):
    with SAMPLE_COG.open("rb") as f:
        key = default_storage.save("sample_cog.tif", File(file=f, name="sample_cog.tif"))
    with default_storage.open(key) as stored:
        s3ff_value = s3ff_field_value_factory(stored)

    expected = {
        "dataset": dataset.id,
        "name": "Sample raster",
        "cloud_optimized_geotiff": s3ff_value,
    }
    resp = client.post("/api/v1/rasters/", expected)
    assert resp.status_code == expected_status
    if expected_status == 201:
        data = resp.json()
        assert data["dataset"] == dataset.id
        assert data["name"] == "Sample raster"
        assert "sample_cog" in data["cloud_optimized_geotiff"]
        raster = RasterData.objects.get(id=data["id"])
        assert raster.cloud_optimized_geotiff.size > 0
