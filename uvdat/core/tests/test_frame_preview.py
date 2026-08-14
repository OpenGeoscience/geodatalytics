from __future__ import annotations

import inspect

from django.core.files.base import ContentFile
import pytest

from uvdat.core.frame_previews.fingerprint import (
    _fingerprint_payload,
    params_fingerprint,
    style_fingerprint,
)
from uvdat.core.frame_previews.preview_regeneration import (
    get_layer_style_preview_status,
    invalidate_and_enqueue_layer_previews,
    invalidate_and_enqueue_previews,
)
from uvdat.core.frame_previews.raster_style import (
    apply_source_filters_to_style_query,
    raster_source_filter_kwargs,
)
from uvdat.core.models import LayerStyle, RasterFramePreview, TaskResult
from uvdat.core.models.frame_preview import PreviewStatus
from uvdat.core.tasks.analytics import flood_simulation as flood_mod
from uvdat.core.tasks.frame_preview import (
    FRAME_PREVIEW_DEFAULT_RESOLUTION_FRACTION,
    FRAME_PREVIEW_MAX_PX,
    FRAME_PREVIEW_MIN_PX,
    generate_frame_previews,
    resolve_preview_max_dimension,
)
from uvdat.core.tasks.run_mode import TaskRunMode

# LayerStyle PATCH still requires vector style_spec (colors/sizes); unused for fingerprints.
_VECTOR_STYLE_SPEC = {
    "default_frame": 0,
    "opacity": 1,
    "colors": [{"name": "all", "visible": True, "use_feature_props": True}],
    "sizes": [{"name": "all", "zoom_scaling": True, "single_size": 5}],
    "filters": [],
}


def _patch_preview_delay(mocker):
    return mocker.patch("uvdat.core.tasks.frame_preview.generate_frame_previews.delay")


def _make_preview(
    layer_frame,
    *,
    fingerprint=None,
    params=None,
    status=PreviewStatus.COMPLETE,
    **kwargs,
):
    params = dict(params or {})
    fingerprint = fingerprint if fingerprint is not None else params_fingerprint(params)
    return RasterFramePreview.objects.create(
        layer_frame=layer_frame,
        style_fingerprint=fingerprint,
        raster_style_params=params,
        status=status,
        **kwargs,
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
            "style_spec": _VECTOR_STYLE_SPEC,
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
    style.raster_style_params = {"palette": "#00ff00", "min": 0, "max": 1}
    style.save(update_fields=["raster_style_params"])

    assert style_fingerprint(style) == style_fingerprint(LayerStyle.objects.get(pk=style.pk))


def test_style_fingerprint_stable_key_order_and_treats_null_as_empty():
    """Fingerprint uses sorted JSON keys; null params match empty params."""
    base = {"palette": "#fff", "min": 0, "max": 1}
    reordered = {"max": 1, "palette": "#fff", "min": 0}

    assert _fingerprint_payload(base) == _fingerprint_payload(reordered)
    assert _fingerprint_payload(None) == _fingerprint_payload({})
    assert params_fingerprint(None) == params_fingerprint({})


@pytest.mark.django_db
def test_invalidate_and_enqueue_previews_uses_db_fingerprint(
    layer_style_factory,
    layer_frame_factory,
    mocker,
):
    layer_style = layer_style_factory()
    layer_frame_factory(layer=layer_style.layer, index=0)
    layer_frame_factory(layer=layer_style.layer, index=1)

    delay = _patch_preview_delay(mocker)

    invalidate_and_enqueue_previews(layer_style)

    delay.assert_called_once()
    layer_id, fingerprint, params = delay.call_args.args[:3]
    assert layer_id == layer_style.layer_id
    assert fingerprint == style_fingerprint(LayerStyle.objects.get(pk=layer_style.pk))
    assert params == dict(layer_style.raster_style_params or {})
    assert delay.call_args.kwargs.get("layer_style_id") == layer_style.id
    assert TaskResult.objects.filter(task_type="frame_preview").count() == 1


@pytest.mark.django_db
def test_invalidate_and_enqueue_previews_skips_when_previews_current(
    layer_style_factory,
    layer_frame_factory,
    mocker,
):
    layer_style = layer_style_factory()
    frame_0 = layer_frame_factory(layer=layer_style.layer, index=0)
    frame_1 = layer_frame_factory(layer=layer_style.layer, index=1)
    fingerprint = style_fingerprint(layer_style)

    preview_0 = _make_preview(
        frame_0,
        fingerprint=fingerprint,
        width=100,
        height=80,
        bounds={"srs": "EPSG:4326", "xmin": -1, "xmax": 1, "ymin": -2, "ymax": 2},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = _make_preview(
        frame_1,
        fingerprint=fingerprint,
        width=120,
        height=90,
        bounds={"srs": "EPSG:4326", "xmin": -2, "xmax": 2, "ymin": -3, "ymax": 3},
    )
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)

    delay = _patch_preview_delay(mocker)

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

    preview_0 = _make_preview(
        frame_0,
        fingerprint="stale-fingerprint",
        width=100,
        height=80,
        bounds={},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = _make_preview(
        frame_1,
        fingerprint="stale-fingerprint",
        width=120,
        height=90,
        bounds={},
    )
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)

    delay = _patch_preview_delay(mocker)

    result = invalidate_and_enqueue_previews(layer_style)

    delay.assert_called_once()
    assert result is not None

    new_fingerprint = style_fingerprint(layer_style)
    # Stale fingerprint rows are left alone; new fingerprint rows are regenerating.
    preview_0.refresh_from_db()
    preview_1.refresh_from_db()
    assert preview_0.style_fingerprint == "stale-fingerprint"
    assert preview_0.status == PreviewStatus.COMPLETE

    new_previews = list(
        RasterFramePreview.objects.filter(
            layer_frame__layer=layer_style.layer,
            style_fingerprint=new_fingerprint,
        )
    )
    assert len(new_previews) == 2
    assert all(p.status == PreviewStatus.CREATING for p in new_previews)
    assert all(not p.image for p in new_previews)


@pytest.mark.django_db
def test_invalidate_and_enqueue_previews_runs_synchronously(
    layer_style_factory,
    layer_frame_factory,
    mocker,
):
    layer_style = layer_style_factory()
    layer_frame_factory(layer=layer_style.layer, index=0)
    layer_frame_factory(layer=layer_style.layer, index=1)

    delay = _patch_preview_delay(mocker)
    apply = mocker.patch("uvdat.core.tasks.frame_preview.generate_frame_previews.apply")

    invalidate_and_enqueue_previews(layer_style, run_mode=TaskRunMode.SYNC)

    apply.assert_called_once()
    delay.assert_not_called()
    assert apply.call_args.kwargs["args"][0] == layer_style.layer_id
    assert apply.call_args.kwargs["kwargs"]["layer_style_id"] == layer_style.id


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
    fingerprint = style_fingerprint(layer_style)

    preview_0 = _make_preview(
        frame_0,
        fingerprint=fingerprint,
        width=100,
        height=80,
        bounds={"srs": "EPSG:4326", "xmin": -1, "xmax": 1, "ymin": -2, "ymax": 2},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_2 = _make_preview(
        frame_2,
        fingerprint=fingerprint,
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
    fingerprint = style_fingerprint(layer_style)

    preview_0 = _make_preview(
        frame_0,
        fingerprint=fingerprint,
        width=100,
        height=80,
        bounds={"srs": "EPSG:4326", "xmin": -1, "xmax": 1, "ymin": -2, "ymax": 2},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = _make_preview(
        frame_1,
        fingerprint=fingerprint,
        width=120,
        height=90,
        bounds={"srs": "EPSG:4326", "xmin": -2, "xmax": 2, "ymin": -3, "ymax": 3},
    )
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)
    preview_2 = _make_preview(
        frame_2,
        fingerprint=fingerprint,
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
    fingerprint = style_fingerprint(layer_style)

    preview_0 = _make_preview(
        frame_0,
        fingerprint=fingerprint,
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
    preview_1 = _make_preview(
        frame_1,
        fingerprint=fingerprint,
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
    fingerprint = style_fingerprint(layer_style)

    preview_0 = _make_preview(
        frame_0,
        fingerprint=fingerprint,
        width=100,
        height=100,
        bounds={},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = _make_preview(
        frame_1,
        fingerprint=fingerprint,
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
    layer_style.raster_style_params = {"palette": "#00ff00", "min": 0, "max": 1}
    layer_style.save(update_fields=["raster_style_params"])
    fingerprint = style_fingerprint(layer_style)

    preview_0 = _make_preview(
        frame_0,
        fingerprint=fingerprint,
        params=layer_style.raster_style_params,
        width=100,
        height=100,
        bounds={},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = _make_preview(
        frame_1,
        fingerprint=fingerprint,
        params=layer_style.raster_style_params,
        width=100,
        height=100,
        bounds={},
    )
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)

    _patch_preview_delay(mocker)

    resp = authenticated_api_client.patch(
        f"/api/v1/layer-styles/{layer_style.id}/",
        {
            "name": layer_style.name,
            "layer": layer_style.layer_id,
            "project": layer_style.project_id,
            "style_spec": _VECTOR_STYLE_SPEC,
            "raster_style_params": {"palette": "#ff0000", "min": 0, "max": 1},
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
    fingerprint = style_fingerprint(layer_style)

    preview = _make_preview(
        frame_0,
        fingerprint=fingerprint,
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
    fingerprint = style_fingerprint(layer_style)

    preview_0 = _make_preview(
        frame_0,
        fingerprint=fingerprint,
        width=100,
        height=100,
        bounds={},
    )
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = _make_preview(
        frame_1,
        fingerprint=fingerprint,
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
def test_layer_api_serves_default_previews_without_layer_style(
    authenticated_api_client,
    layer_factory,
    layer_frame_factory,
    project,
    user,
):
    """Empty-params previews are available on a layer with no LayerStyle."""
    layer = layer_factory()
    project.set_collaborators([user])
    project.datasets.set([layer.dataset])
    frame_0 = layer_frame_factory(layer=layer, index=0)
    frame_1 = layer_frame_factory(layer=layer, index=1)
    fingerprint = params_fingerprint({})

    preview_0 = _make_preview(frame_0, fingerprint=fingerprint, width=100, height=100, bounds={})
    preview_0.image.save("frame-0.png", ContentFile(b"png0"), save=True)
    preview_1 = _make_preview(frame_1, fingerprint=fingerprint, width=100, height=100, bounds={})
    preview_1.image.save("frame-1.png", ContentFile(b"png1"), save=True)

    resp = authenticated_api_client.get(f"/api/v1/layers/{layer.id}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_style"] is None
    assert data["preview_status"] == "ready"
    assert len(data["multiframe_previews"]) == 2


@pytest.mark.django_db
def test_styles_with_identical_params_share_preview_rows(
    layer_style_factory,
    layer_frame_factory,
):
    style_a = layer_style_factory(name="A")
    style_b = layer_style_factory(name="B", layer=style_a.layer, project=style_a.project)
    style_a.raster_style_params = {"palette": "#00ff00", "min": 0, "max": 1}
    style_b.raster_style_params = {"palette": "#00ff00", "min": 0, "max": 1}
    style_a.save(update_fields=["raster_style_params"])
    style_b.save(update_fields=["raster_style_params"])

    frame_0 = layer_frame_factory(layer=style_a.layer, index=0)
    frame_1 = layer_frame_factory(layer=style_a.layer, index=1)
    fingerprint = style_fingerprint(style_a)
    assert fingerprint == style_fingerprint(style_b)

    for frame in (frame_0, frame_1):
        preview = _make_preview(
            frame,
            fingerprint=fingerprint,
            params=style_a.raster_style_params,
            width=50,
            height=50,
            bounds={},
        )
        preview.image.save(f"frame-{frame.index}.png", ContentFile(b"png"), save=True)

    assert style_a.multiframe_previews() is not None
    assert style_b.multiframe_previews() is not None
    assert RasterFramePreview.objects.filter(style_fingerprint=fingerprint).count() == 2


@pytest.mark.django_db
def test_generate_frame_previews_continues_when_style_deleted(
    layer_style_factory,
    layer_frame_factory,
    mocker,
):
    """Deleted styles still finish from the enqueued params snapshot."""
    layer_style = layer_style_factory()
    layer_frame_factory(layer=layer_style.layer, index=0)
    layer_frame_factory(layer=layer_style.layer, index=1)
    params = {"palette": "#00ff00", "min": 0, "max": 1}
    layer_style.raster_style_params = params
    layer_style.save(update_fields=["raster_style_params"])
    fingerprint = style_fingerprint(layer_style)
    result = TaskResult.objects.create(
        name="Frame previews",
        task_type="frame_preview",
        project=layer_style.project,
        inputs={
            "layer_id": layer_style.layer_id,
            "fingerprint": fingerprint,
            "layer_style_id": layer_style.id,
        },
    )
    style_id = layer_style.id
    layer_id = layer_style.layer_id
    for frame in layer_style.layer.raster_frames():
        _make_preview(
            frame,
            fingerprint=fingerprint,
            params=params,
            status=PreviewStatus.CREATING,
        )
    layer_style.delete()

    mocker.patch(
        "uvdat.core.tasks.frame_preview.generate_frame_preview_png",
        return_value=(b"png", 10, 10, None),
    )

    generate_frame_previews(layer_id, fingerprint, params, result.id, layer_style_id=style_id)

    result.refresh_from_db()
    assert result.completed is not None
    assert result.outputs["ready_count"] == 2
    assert (
        RasterFramePreview.objects.filter(
            layer_frame__layer_id=layer_id,
            style_fingerprint=fingerprint,
            status=PreviewStatus.COMPLETE,
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_invalidate_and_enqueue_skips_when_fingerprint_job_in_flight(
    layer_style_factory,
    layer_frame_factory,
    mocker,
):
    layer_style = layer_style_factory()
    layer_frame_factory(layer=layer_style.layer, index=0)
    layer_frame_factory(layer=layer_style.layer, index=1)
    delay = _patch_preview_delay(mocker)

    first = invalidate_and_enqueue_previews(layer_style)
    second = invalidate_and_enqueue_previews(layer_style)

    delay.assert_called_once()
    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert TaskResult.objects.filter(task_type="frame_preview").count() == 1


@pytest.mark.django_db
def test_invalidate_and_enqueue_starts_job_for_different_fingerprint(
    layer_style_factory,
    layer_frame_factory,
    mocker,
):
    layer_style = layer_style_factory()
    layer_frame_factory(layer=layer_style.layer, index=0)
    layer_frame_factory(layer=layer_style.layer, index=1)
    delay = _patch_preview_delay(mocker)

    first = invalidate_and_enqueue_layer_previews(layer_style.layer, {})
    layer_style.raster_style_params = {"palette": "#00ff00", "min": 0, "max": 1}
    layer_style.save(update_fields=["raster_style_params"])
    second = invalidate_and_enqueue_previews(layer_style)

    assert delay.call_count == 2
    assert first is not None
    assert second is not None
    assert first.id != second.id
    assert first.completed is None
    assert second.completed is None


def test_flood_simulation_enqueues_style_previews_after_params():
    """Regression: flood default style params must trigger preview generation."""
    source = inspect.getsource(flood_mod.flood_simulation)
    assert "invalidate_and_enqueue_previews(style, run_mode=TaskRunMode.SYNC)" in source
    assert "raster_style_params" in source
