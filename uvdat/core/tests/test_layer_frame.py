from __future__ import annotations

import pytest
from pytest_lazy_fixtures import lf

from uvdat.core.models import LayerFrame


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [(lf("api_client"), 401), (lf("authenticated_api_client"), 201)],
)
@pytest.mark.django_db
def test_create_layer_frame(layer, raster_data, client, expected_status):
    resp = client.post(
        "/api/v1/layer-frames/",
        {
            "layer": layer.id,
            "raster": raster_data.id,
            "name": "Sample frame",
            "index": 0,
        },
    )
    assert resp.status_code == expected_status
    if expected_status == 201:
        data = resp.json()
        assert data["layer"] == layer.id
        assert data["raster"]["id"] == raster_data.id
        assert data["vector"] is None
        frame = LayerFrame.objects.get(id=data["id"])
        assert frame.raster == raster_data
