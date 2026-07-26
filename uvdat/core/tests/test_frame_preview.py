from __future__ import annotations

from django.core.files.base import ContentFile
import pytest

from uvdat.core.frame_previews.fingerprint import _fingerprint_payload, style_fingerprint
from uvdat.core.frame_previews.preview_regeneration import (
    get_layer_style_preview_status,
    invalidate_and_enqueue_previews,
)
from uvdat.core.frame_previews.raster_style import (
    apply_source_filters_to_style_query,
    raster_source_filter_kwargs,
)
from uvdat.core.models import LayerStyle, RasterFramePreview
from uvdat.core.models.frame_preview import PreviewStatus
from uvdat.core.tasks.frame_preview import (
    DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC,
    FRAME_PREVIEW_DEFAULT_RESOLUTION_FRACTION,
    FRAME_PREVIEW_MAX_PX,
    FRAME_PREVIEW_MIN_PX,
    resolve_preview_max_dimension,
)


@pytest.mark.django_db
def test_layer_style_api_stores_client_raster_style_params(
    authenticated_api_client,
    layer_style_factory,
    layer_frame_factory,
    project,
    user,
):
    layer_style = layer_style_factory()
    layer_frame_factory(layer=layer_style.layer, index=0)
    project.set_collaborators([user])
    project.datasets.set([layer_style.layer.dataset])
    raster_style_params = {"palette": "#00ff00", "min": 0, "max": 1}

    resp = authenticated_api_client.patch(
        f"/api/v1/layer-styles/{layer_style.id}/",
        {
            "name": layer_style.name,
            "layer": layer_style.layer_id,
            "project": layer_style.project_id,
            "style_spec": DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC,
            "raster_style_params": raster_style_params,
        },
        format="json",
    )
    assert resp.status_code == 200
    assert "raster_style_params" not in resp.json()
    layer_style.refresh_from_db()
    assert layer_style.raster_style_params == raster_style_params


def test_raster_source_filter_kwargs_extracts_frame():
    assert raster_source_filter_kwargs({"frame": 3}) == {"frame": 3}
    assert raster_source_filter_kwargs({"band": 2}) == {}
    assert raster_source_filter_kwargs({"frame": 1, "band": 2}) == {"frame": 1}


def test_apply_source_filters_to_style_query_embeds_band_not_frame():
    query = apply_source_filters_to_style_query({"palette": "#fff"}, {"frame": 3, "band": 2})
    assert query == {"palette": "#fff", "band": 2}
    assert "frame" not in query
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
def test_style_fingerprint_matches_db_after_ingest_style_setup(layer_style_factory):
    """Enqueue fingerprint must match what the Celery task reads from the database."""
    style = layer_style_factory()
    style.save_style_configs(DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC)

    assert style_fingerprint(style) == style_fingerprint(LayerStyle.objects.get(pk=style.pk))


def test_style_fingerprint_stable_key_order_and_ignores_opacity_default_frame():
    """Fingerprint uses sorted JSON keys and ignores opacity / default_frame."""
    base = {
        "colors": [{"name": "all", "visible": True, "single_color": "#ffffff"}],
        "filters": [],
        "sizes": [],
        "opacity": 1,
        "default_frame": 0,
    }
    reordered = {
        "default_frame": 0,
        "sizes": [],
        "filters": [],
        "opacity": 1,
        "colors": [{"single_color": "#ffffff", "visible": True, "name": "all"}],
    }
    opacity_and_frame_only = {
        **base,
        "opacity": 0.25,
        "default_frame": 3,
    }

    assert _fingerprint_payload(base) == _fingerprint_payload(reordered)
    assert _fingerprint_payload(base) == _fingerprint_payload(opacity_and_frame_only)
    assert "opacity" not in _fingerprint_payload(base)
    assert "default_frame" not in _fingerprint_payload(base)


@pytest.mark.django_db
def test_invalidate_and_enqueue_previews_uses_db_fingerprint(
    layer_style_factory,
    layer_frame_factory,
    mocker,
):
    layer_style = layer_style_factory()
    layer_frame_factory(layer=layer_style.layer, index=0)
    layer_frame_factory(layer=layer_style.layer, index=1)
    layer_style.save_style_configs(DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC)

    delay = mocker.patch("uvdat.core.tasks.frame_preview.generate_layer_style_previews.delay")

    invalidate_and_enqueue_previews(layer_style)

    delay.assert_called_once()
    _, fingerprint, _ = delay.call_args.args
    assert fingerprint == style_fingerprint(LayerStyle.objects.get(pk=layer_style.pk))


@pytest.mark.django_db
def test_invalidate_and_enqueue_previews_skips_when_previews_current(
    layer_style_factory,
    layer_frame_factory,
    mocker,
):
    layer_style = layer_style_factory()
    frame_0 = layer_frame_factory(layer=layer_style.layer, index=0)
    frame_1 = layer_frame_factory(layer=layer_style.layer, index=1)
    layer_style.save_style_configs(DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC)
    fingerprint = style_fingerprint(layer_style)

    preview_0 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_0,
        status=PreviewStatus.COMPLETE,
        style_fingerprint=fingerprint,
        width=100,
        height=80,
        bounds={"srs": "EPSG:4326", "xmin": -1, "xmax": 1, "ymin": -2, "ymax": 2},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_1,
        status=PreviewStatus.COMPLETE,
        style_fingerprint=fingerprint,
        width=120,
        height=90,
        bounds={"srs": "EPSG:4326", "xmin": -2, "xmax": 2, "ymin": -3, "ymax": 3},
    )
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)

    delay = mocker.patch("uvdat.core.tasks.frame_preview.generate_layer_style_previews.delay")

    result = invalidate_and_enqueue_previews(layer_style)

    delay.assert_not_called()
    assert result is None
    assert get_layer_style_preview_status(layer_style) == "ready"

    preview_0.refresh_from_db()
    preview_1.refresh_from_db()
    assert preview_0.status == PreviewStatus.COMPLETE
    assert preview_1.status == PreviewStatus.COMPLETE
    assert preview_0.image.name
    assert preview_1.image.name
    assert preview_0.width == 100
    assert preview_1.width == 120


@pytest.mark.django_db
def test_invalidate_and_enqueue_previews_runs_when_fingerprint_changed(
    layer_style_factory,
    layer_frame_factory,
    mocker,
):
    layer_style = layer_style_factory()
    frame_0 = layer_frame_factory(layer=layer_style.layer, index=0)
    frame_1 = layer_frame_factory(layer=layer_style.layer, index=1)
    layer_style.save_style_configs(DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC)

    preview_0 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_0,
        status=PreviewStatus.COMPLETE,
        style_fingerprint="stale-fingerprint",
        width=100,
        height=80,
        bounds={},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_1,
        status=PreviewStatus.COMPLETE,
        style_fingerprint="stale-fingerprint",
        width=120,
        height=90,
        bounds={},
    )
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)

    delay = mocker.patch("uvdat.core.tasks.frame_preview.generate_layer_style_previews.delay")

    result = invalidate_and_enqueue_previews(layer_style)

    delay.assert_called_once()
    assert result is not None

    preview_0.refresh_from_db()
    preview_1.refresh_from_db()
    assert preview_0.status == PreviewStatus.REGENERATING
    assert preview_1.status == PreviewStatus.REGENERATING
    assert not preview_0.image
    assert not preview_1.image


@pytest.mark.django_db
def test_invalidate_and_enqueue_previews_runs_synchronously(
    layer_style_factory,
    layer_frame_factory,
    mocker,
):
    layer_style = layer_style_factory()
    layer_frame_factory(layer=layer_style.layer, index=0)
    layer_frame_factory(layer=layer_style.layer, index=1)
    layer_style.save_style_configs(DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC)

    delay = mocker.patch("uvdat.core.tasks.frame_preview.generate_layer_style_previews.delay")
    apply = mocker.patch("uvdat.core.tasks.frame_preview.generate_layer_style_previews.apply")

    invalidate_and_enqueue_previews(layer_style, asynchronous=False)

    apply.assert_called_once()
    delay.assert_not_called()
    assert apply.call_args.kwargs["args"][0] == layer_style.id


@pytest.mark.django_db
def test_multiframe_previews_for_style_returns_none_for_single_frame(
    layer_style_factory,
    layer_frame_factory,
):
    layer_style = layer_style_factory()
    layer_frame_factory(layer=layer_style.layer, index=0)

    assert layer_style.multiframe_previews() is None


@pytest.mark.django_db
def test_multiframe_previews_for_style_returns_none_when_partial(
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
        status=PreviewStatus.COMPLETE,
        width=100,
        height=80,
        bounds={"srs": "EPSG:4326", "xmin": -1, "xmax": 1, "ymin": -2, "ymax": 2},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_2 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_2,
        status=PreviewStatus.COMPLETE,
        width=200,
        height=150,
        bounds={"srs": "EPSG:4326", "xmin": -3, "xmax": 3, "ymin": -4, "ymax": 4},
    )
    preview_2.image.save("frame-2.png", ContentFile(b"png2"), save=True)

    assert layer_style.multiframe_previews() is None


@pytest.mark.django_db
def test_multiframe_previews_for_style_ordered_by_frame_index(
    layer_style_factory,
    layer_frame_factory,
):
    layer_style = layer_style_factory()
    frame_0 = layer_frame_factory(layer=layer_style.layer, index=0)
    frame_1 = layer_frame_factory(layer=layer_style.layer, index=1)
    frame_2 = layer_frame_factory(layer=layer_style.layer, index=2)

    preview_0 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_0,
        status=PreviewStatus.COMPLETE,
        width=100,
        height=80,
        bounds={"srs": "EPSG:4326", "xmin": -1, "xmax": 1, "ymin": -2, "ymax": 2},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_1,
        status=PreviewStatus.COMPLETE,
        width=120,
        height=90,
        bounds={"srs": "EPSG:4326", "xmin": -2, "xmax": 2, "ymin": -3, "ymax": 3},
    )
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)
    preview_2 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_2,
        status=PreviewStatus.COMPLETE,
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
        {
            "url": preview_1.image.url,
            "width": 120,
            "height": 90,
            "bounds": preview_1.bounds,
        },
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
    frame_0 = layer_frame_factory(layer=layer_style.layer, index=0)
    frame_1 = layer_frame_factory(layer=layer_style.layer, index=1)

    preview_0 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_0,
        status=PreviewStatus.COMPLETE,
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
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_1,
        status=PreviewStatus.COMPLETE,
        width=100,
        height=80,
        bounds={},
    )
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)

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
    frame_1 = layer_frame_factory(layer=layer_style.layer, index=1)

    preview_0 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_0,
        status=PreviewStatus.COMPLETE,
        width=100,
        height=100,
        bounds={},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_1,
        status=PreviewStatus.COMPLETE,
        width=100,
        height=100,
        bounds={},
    )
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)

    resp = authenticated_api_client.get(f"/api/v1/layer-styles/{layer_style.id}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["preview_status"] == "ready"
    assert data["multiframe_previews"] == [
        {
            "url": preview_0.image.url,
            "width": 100,
            "height": 100,
            "bounds": {},
        },
        {
            "url": preview_1.image.url,
            "width": 100,
            "height": 100,
            "bounds": {},
        },
    ]


@pytest.mark.django_db
def test_layer_style_patch_reports_notready_after_preview_invalidation(
    authenticated_api_client,
    layer_style_factory,
    layer_frame_factory,
    project,
    user,
    mocker,
):
    layer_style = layer_style_factory()
    project.set_collaborators([user])
    project.datasets.set([layer_style.layer.dataset])
    frame_0 = layer_frame_factory(layer=layer_style.layer, index=0)
    frame_1 = layer_frame_factory(layer=layer_style.layer, index=1)
    layer_style.save_style_configs(DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC)
    fingerprint = style_fingerprint(layer_style)

    preview_0 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_0,
        status=PreviewStatus.COMPLETE,
        style_fingerprint=fingerprint,
        width=100,
        height=100,
        bounds={},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_1,
        status=PreviewStatus.COMPLETE,
        style_fingerprint=fingerprint,
        width=100,
        height=100,
        bounds={},
    )
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)

    mocker.patch("uvdat.core.tasks.frame_preview.generate_layer_style_previews.delay")

    updated_spec = {
        **DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC,
        "colors": [
            {
                "name": "all",
                "visible": True,
                "use_feature_props": True,
                "single_color": "#ff0000",
            }
        ],
    }
    resp = authenticated_api_client.patch(
        f"/api/v1/layer-styles/{layer_style.id}/",
        {
            "name": layer_style.name,
            "layer": layer_style.layer_id,
            "project": layer_style.project_id,
            "style_spec": updated_spec,
        },
        format="json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["preview_status"] == "notready"
    assert "multiframe_previews" not in data


@pytest.mark.django_db
def test_api_omits_previews_while_not_ready(
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
        status=PreviewStatus.COMPLETE,
        width=100,
        height=100,
        bounds={},
    )
    preview.image.save("frame-0.png", ContentFile(b"png0"), save=True)

    resp = authenticated_api_client.get(f"/api/v1/layer-styles/{layer_style.id}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["preview_status"] == "notready"
    assert "multiframe_previews" not in data


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
    frame_1 = layer_frame_factory(layer=layer, index=1)

    preview_0 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_0,
        status=PreviewStatus.COMPLETE,
        width=100,
        height=100,
        bounds={},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = RasterFramePreview.objects.create(
        layer_style=layer_style,
        layer_frame=frame_1,
        status=PreviewStatus.COMPLETE,
        width=100,
        height=100,
        bounds={},
    )
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)

    resp = authenticated_api_client.get(f"/api/v1/layers/{layer.id}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["preview_status"] == "ready"
    assert data["multiframe_previews"] == [
        {
            "url": preview_0.image.url,
            "width": 100,
            "height": 100,
            "bounds": {},
        },
        {
            "url": preview_1.image.url,
            "width": 100,
            "height": 100,
            "bounds": {},
        },
    ]
    assert "multiframe_previews" not in data.get("default_style", {})


@pytest.mark.django_db
def test_dataset_layers_self_heal_missing_default_style(
    authenticated_api_client,
    layer_style_factory,
    layer_frame_factory,
    project,
    user,
):
    """A layer with styles but no default_style should still surface previews.

    ``default_style`` can be nulled (``on_delete=SET_NULL``) when the style it
    pointed at is removed. The layers endpoint should adopt an existing style as
    the default so its frame previews are not lost.
    """
    layer_style = layer_style_factory(name="Default")
    layer = layer_style.layer
    layer.default_style = None
    layer.save(update_fields=["default_style"])
    project.set_collaborators([user])
    project.datasets.set([layer.dataset])
    frame_0 = layer_frame_factory(layer=layer, index=0)
    frame_1 = layer_frame_factory(layer=layer, index=1)

    for frame in (frame_0, frame_1):
        preview = RasterFramePreview.objects.create(
            layer_style=layer_style,
            layer_frame=frame,
            status=PreviewStatus.COMPLETE,
            width=100,
            height=100,
            bounds={},
        )
        preview.image.save(f"frame-{frame.index}.png", ContentFile(b"png"), save=True)

    resp = authenticated_api_client.get(f"/api/v1/datasets/{layer.dataset_id}/layers/")
    assert resp.status_code == 200
    layers = resp.json()
    assert len(layers) == 1
    layer_data = layers[0]
    assert layer_data["default_style"]["id"] == layer_style.id
    assert layer_data["preview_status"] == "ready"
    assert len(layer_data["multiframe_previews"]) == 2

    layer.refresh_from_db()
    assert layer.default_style_id == layer_style.id


@pytest.mark.django_db
def test_create_style_sets_default_when_layer_has_none(
    authenticated_api_client,
    layer_factory,
    project,
    user,
):
    """Creating the first style for a layer without a default adopts it."""
    layer = layer_factory()
    project.set_collaborators([user])
    project.datasets.set([layer.dataset])
    assert layer.default_style_id is None

    resp = authenticated_api_client.post(
        "/api/v1/layer-styles/",
        {
            "name": "terrain",
            "layer": layer.id,
            "project": project.id,
            "style_spec": DEFAULT_MULTIFRAME_RASTER_STYLE_SPEC,
        },
        format="json",
    )
    assert resp.status_code == 200

    layer.refresh_from_db()
    assert layer.default_style_id == resp.json()["id"]
