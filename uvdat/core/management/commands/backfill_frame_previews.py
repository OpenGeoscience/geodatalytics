r"""Backfill multiframe raster frame previews for existing layers and styles.

Dev reset + backfill via docker compose:

docker compose run --rm django ./manage.py clear_frame_previews
docker compose run --rm django ./manage.py backfill_frame_previews
"""

from __future__ import annotations

import djclick as click

from uvdat.core.management.backfill_frame_previews_utils import (
    backfill_layer_previews,
    multiframe_layers_qs,
)


@click.command()
@click.option("--layer-id", type=int, default=None)
@click.option("--dataset-id", type=int, default=None)
@click.option("--project-id", type=int, default=None)
def backfill_frame_previews(
    *,
    layer_id: int | None,
    dataset_id: int | None,
    project_id: int | None,
):
    """Backfill multiframe raster frame previews for existing layers and styles."""
    layers = list(
        multiframe_layers_qs(
            layer_id=layer_id,
            dataset_id=dataset_id,
            project_id=project_id,
        )
    )

    if not layers:
        click.secho("No multiframe raster layers matched the filters.", fg="yellow")
        return

    for layer in layers:
        click.echo(f"Layer {layer.id}")
        backfill_layer_previews(layer, project_id=project_id, echo=click.echo)

    click.secho("Done.", fg="green")
