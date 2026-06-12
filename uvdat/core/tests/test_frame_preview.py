from __future__ import annotations

import pytest

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
