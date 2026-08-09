from __future__ import annotations

import io

import pandas as pd
import requests

from uvdat.core.models import NetworkNode, VectorData, VectorFeature
from uvdat.core.tasks.run_mode import TaskRunMode

LINE_COLORS = {
    "RED": "#D31414",
    "GREEN": "#188A00",
    "BLUE": "#1F63AC",
    "ORANGE": "#D88901",
    "SILVER": "#7B8B86",
}

RIDERSHIP_DATA_URL = "https://data.kitware.com/api/v1/item/69938a5d92fec64197f41dc3/download"


STATION_NAME_ABBREVIATIONS = {
    "Northeastern University": "Northeastern",
    "Massachusetts Avenue": "Massachusetts Ave",
}


def convert_dataset(dataset, options):
    # Run standard conversion task first
    dataset.spawn_conversion_task(
        layer_options=options.get("layers"),
        network_options=options.get("network_options"),
        region_options=options.get("region_options"),
        run_mode=TaskRunMode.SYNC,
    )

    # Post-processing

    # For each associated vector feature, add style properties
    # To color features by the LINE property
    for feature in VectorFeature.objects.filter(vector_data__dataset=dataset):
        lines = feature.properties.get("LINE", "").split("/")
        colors = [LINE_COLORS[line] for line in lines if line in LINE_COLORS]
        if colors:
            fill = colors[0]
            stroke = colors[1] if len(colors) > 1 else fill
            default_style = {
                "fill": fill,
                "stroke": stroke,
            }
            feature.properties = feature.properties | default_style
            feature.save()

    # Add ridership data to stations
    response = requests.get(RIDERSHIP_DATA_URL, timeout=1000)
    ridership_data = pd.read_csv(io.StringIO(response.text.replace("\r", "")))
    for _, station in ridership_data.iterrows():
        station_name = station.loc["stop_name"].replace("'", "")
        if station_name in STATION_NAME_ABBREVIATIONS:
            station_name = STATION_NAME_ABBREVIATIONS[station_name]
        total_offs = int(station.loc["total_offs"])
        node_matches = NetworkNode.objects.filter(
            network__vector_data__dataset=dataset, metadata__STATION__iexact=station_name
        )
        if node_matches.count():
            new = {"total_ridership": total_offs}
            node = node_matches.first()
            node.metadata = node.metadata | new
            node.save()
            feature = node.vector_feature
            feature.properties = feature.properties | new
            feature.save()
        else:
            print(f"Could not find node for {station_name}")

    # Update vector data summary
    for vector in VectorData.objects.filter(dataset=dataset):
        vector.get_summary(cache=False)
