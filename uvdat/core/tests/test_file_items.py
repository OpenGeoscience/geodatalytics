from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.files.base import File
import pytest
from pytest_lazy_fixtures import lf

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("client", "expected_status"),
    [(lf("api_client"), 401), (lf("authenticated_api_client"), 201)],
)
@pytest.mark.django_db
def test_upload_and_create_file_item(
    multiframe_vector_file,
    dataset,
    client,
    expected_status,
    s3ff_field_value_factory: Callable[[File[bytes]], str],
):
    with multiframe_vector_file["path"].open("rb") as f:
        s3ff_value = s3ff_field_value_factory(File(file=f, name=multiframe_vector_file["name"]))

    fileitem_expected = {
        "name": "multiframe_vector.geojson",
        "file": s3ff_value,
        "file_type": "geojson",
        "dataset": dataset.id,
        "metadata": {
            "source": "pytest",
        },
    }
    resp = client.post("/api/v1/files/", fileitem_expected)
    assert resp.status_code == expected_status
    if expected_status == 201:
        serialized_fileitem = resp.json()
        for key, value in fileitem_expected.items():
            if key == "file":
                assert "multiframe_vector.geojson" in serialized_fileitem[key]
            else:
                assert serialized_fileitem[key] == value
        assert "id" in serialized_fileitem
