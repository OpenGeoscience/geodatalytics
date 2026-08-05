from __future__ import annotations

import logging

from celery import shared_task
import pandas as pd
from webcolors import name_to_hex

from uvdat.core.models import Chart, TaskResult

logger = logging.getLogger(__name__)


@shared_task
def convert_chart(chart_id, conversion_options, result_id=None):
    chart = Chart.objects.get(id=chart_id)

    result = None
    if result_id:
        result = TaskResult.objects.get(id=result_id)

    label_column = conversion_options.get("labels")
    dataset_columns = conversion_options.get("datasets")
    palette_options = conversion_options.get("palette")

    chart_data = {
        "labels": [],
        "datasets": [],
    }

    chart_file = chart.fileitem_set.first()
    if result is not None:
        result.write_status(f"Converting file {chart_file.name}...")
    if chart_file.file_type == "csv":
        with chart_file.file.open() as f:
            raw_data = pd.read_csv(f)
    else:
        raise NotImplementedError(
            f"Convert chart data for file type {chart_file.file_type}",
        )
    chart_data["labels"] = raw_data[label_column].fillna(-1).tolist()
    chart_data["datasets"] = [
        {
            "label": dataset_column,
            "backgroundColor": name_to_hex(palette_options.get(dataset_column, "black")),
            "borderColor": name_to_hex(palette_options.get(dataset_column, "black")),
            "data": raw_data[dataset_column].fillna(-1).tolist(),
        }
        for dataset_column in dataset_columns
    ]

    chart.chart_data = chart_data
    chart.save()
    logger.info("Saved converted data for chart %s.", chart.name)

    if result is not None:
        result.complete()
