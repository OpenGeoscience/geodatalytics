r"""Clear all raster frame previews and layer style raster params.

Dev reset + backfill via docker compose:

docker compose run --rm django ./manage.py clear_frame_previews
docker compose run --rm django ./manage.py backfill_frame_previews
"""

from __future__ import annotations

import djclick as click

from uvdat.core.models import LayerStyle, RasterFramePreview


@click.command()
def clear_frame_previews():
    """Delete all frame previews and set raster_style_params to None on all layer styles."""
    preview_count, _ = RasterFramePreview.objects.all().delete()
    style_count = LayerStyle.objects.update(raster_style_params=None)

    click.echo(f"Deleted {preview_count} RasterFramePreview rows")
    click.echo(f"Cleared raster_style_params on {style_count} LayerStyle rows")
    click.secho("Done.", fg="green")
