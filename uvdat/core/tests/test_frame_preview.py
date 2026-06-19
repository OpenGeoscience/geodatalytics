from __future__ import annotations

from django.core.files.base import ContentFile
import pytest

from uvdat.core.models import RasterFramePreview
from uvdat.core.raster_style import (
    apply_source_filters_to_style_query,
    build_thumbnail_style_query,
    raster_source_filter_kwargs,
)
from uvdat.core.tasks.frame_preview import (
    FRAME_PREVIEW_DEFAULT_RESOLUTION_FRACTION,
    FRAME_PREVIEW_MAX_PX,
    FRAME_PREVIEW_MIN_PX,
    resolve_preview_max_dimension,
)


def test_build_thumbnail_style_query_does_not_embed_frame():
    style_spec = {
        "colors": [{"name": "all", "visible": True, "single_color": "#ffffff"}],
        "filters": [],
    }
    query = build_thumbnail_style_query(style_spec, {"frame": 3}, {})
    assert "frame" not in query
    assert query == {"palette": "#ffffff"}


def test_raster_source_filter_kwargs_extracts_frame():
    assert raster_source_filter_kwargs({"frame": 3}) == {"frame": 3}
    assert raster_source_filter_kwargs({"band": 2}) == {}
    assert raster_source_filter_kwargs({"frame": 1, "band": 2}) == {"frame": 1}


def test_apply_source_filters_to_style_query_embeds_band_not_frame():
    query = apply_source_filters_to_style_query({}, {"frame": 3, "band": 2})
    assert query == {"band": 2}
    assert apply_source_filters_to_style_query({}, {"frame": 3, "band": 1}) == {"band": 1}
    assert apply_source_filters_to_style_query({}, {"band": 1}) == {"band": 1}


@pytest.mark.parametrize(
    ("resolution_fraction", "raster_max_dimension", "expected_max_px"),
    [
        (None, None, round(FRAME_PREVIEW_MAX_PX * FRAME_PREVIEW_DEFAULT_RESOLUTION_FRACTION)),
        (0.25, None, 1024),
        (0.5, None, 2048),
        (FRAME_PREVIEW_DEFAULT_RESOLUTION_FRACTION, None, 512),
        (None, 4096, FRAME_PREVIEW_MIN_PX),
        (0.25, 4096, FRAME_PREVIEW_MIN_PX),
        (0.5, 4096, 2048),
        (None, 800, 800),
        (0.5, 500, 500),
        (0.75, None, 3072),
    ],
)
def test_resolve_preview_max_dimension(
    resolution_fraction,
    raster_max_dimension,
    expected_max_px,
):
    assert (
        resolve_preview_max_dimension(resolution_fraction, raster_max_dimension) == expected_max_px
    )


@pytest.mark.django_db
def test_multiframe_previews_for_style_returns_none_for_single_frame(
    layer_style_factory,
    layer_frame_factory,
):
    layer_style = layer_style_factory()
    layer_frame_factory(layer=layer_style.layer, index=0)

    assert layer_style.multiframe_previews() is None


@pytest.mark.django_db
def test_multiframe_previews_for_style_ordered_by_frame_index(
    layer_style_factory,
    layer_frame_factory,
):
    layer_style = layer_style_factory()
    frame_0 = layer_frame_factory(layer=layer_style.layer, index=0)
    layer_frame_factory(layer=layer_style.layer, index=1)
    frame_2 = layer_frame_factory(layer=layer_style.layer, index=2)

    preview_0 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_0,
        width=100,
        height=80,
        bounds={"srs": "EPSG:4326", "xmin": -1, "xmax": 1, "ymin": -2, "ymax": 2},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_2 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_2,
        width=200,
        height=150,
        bounds={"srs": "EPSG:4326", "xmin": -3, "xmax": 3, "ymin": -4, "ymax": 4},
    )
    preview_2.image.save("frame-2.png", ContentFile(b"png2"), save=True)

    previews = layer_style.multiframe_previews()
    assert previews == [
        {
            "url": preview_0.image.url,
            "width": 100,
            "height": 80,
            "bounds": preview_0.bounds,
        },
        None,
        {
            "url": preview_2.image.url,
            "width": 200,
            "height": 150,
            "bounds": preview_2.bounds,
        },
    ]


@pytest.mark.django_db
def test_preview_bounds_includes_corners(
    layer_style_factory,
    layer_frame_factory,
):
    layer_style = layer_style_factory()
    frame = layer_frame_factory(layer=layer_style.layer, index=0)
    layer_frame_factory(layer=layer_style.layer, index=1)

    preview = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame,
        width=100,
        height=80,
        bounds={
            "srs": "EPSG:4326",
            "xmin": -1,
            "xmax": 1,
            "ymin": -2,
            "ymax": 2,
            "ul": {"x": -1, "y": 2},
            "ur": {"x": 1, "y": 2},
            "lr": {"x": 1, "y": -2},
            "ll": {"x": -1, "y": -2},
        },
    )
    preview.image.save("frame-0.png", ContentFile(b"png0"), save=True)

    previews = layer_style.multiframe_previews()
    assert previews[0]["bounds"]["ul"] == {"x": -1, "y": 2}


@pytest.mark.django_db
def test_layer_style_api_includes_multiframe_previews(
    authenticated_api_client,
    layer_style_factory,
    layer_frame_factory,
    project,
    user,
):
    layer_style = layer_style_factory()
    project.set_collaborators([user])
    project.datasets.set([layer_style.layer.dataset])
    frame_0 = layer_frame_factory(layer=layer_style.layer, index=0)
    layer_frame_factory(layer=layer_style.layer, index=1)

    preview = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_0,
        width=100,
        height=100,
        bounds={},
    )
    preview.image.save("frame-0.png", ContentFile(b"png0"), save=True)

    resp = authenticated_api_client.get(f"/api/v1/layer-styles/{layer_style.id}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["multiframe_previews"] == [
        {
            "url": preview.image.url,
            "width": 100,
            "height": 100,
            "bounds": {},
        },
        None,
    ]


@pytest.mark.django_db
def test_layer_api_includes_multiframe_previews(
    authenticated_api_client,
    layer_style_factory,
    layer_frame_factory,
    project,
    user,
):
    layer_style = layer_style_factory()
    layer = layer_style.layer
    layer.default_style = layer_style
    layer.save(update_fields=["default_style"])
    project.set_collaborators([user])
    project.datasets.set([layer.dataset])
    frame_0 = layer_frame_factory(layer=layer, index=0)
    layer_frame_factory(layer=layer, index=1)

    preview = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_0,
        width=100,
        height=100,
        bounds={},
    )
    preview.image.save("frame-0.png", ContentFile(b"png0"), save=True)

    resp = authenticated_api_client.get(f"/api/v1/layers/{layer.id}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["multiframe_previews"] == [
        {
            "url": preview.image.url,
            "width": 100,
            "height": 100,
            "bounds": {},
        },
        None,
    ]
    assert "multiframe_previews" not in data.get("default_style", {})
