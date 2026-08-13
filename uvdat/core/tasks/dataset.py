from __future__ import annotations

import contextlib

from celery import shared_task

from uvdat.core.frame_previews.preview_regeneration import (
    invalidate_and_enqueue_layer_previews,
)
from uvdat.core.models import (
    Dataset,
    FileItem,
    Layer,
    LayerFrame,
    RasterData,
    TaskResult,
    VectorData,
)
from uvdat.core.tasks.run_mode import TaskRunMode

from .conversion import convert_file_item
from .data import create_vector_features
from .networks import create_network
from .regions import create_source_regions


def create_layers_and_frames(  # noqa: C901, PLR0912, PLR0915
    dataset,
    layer_options=None,
    task_result=None,
    *,
    run_mode: TaskRunMode = TaskRunMode.ASYNC,
):
    Layer.objects.filter(dataset=dataset).delete()
    LayerFrame.objects.filter(layer__dataset=dataset).delete()
    vectors = VectorData.objects.filter(dataset=dataset)
    rasters = RasterData.objects.filter(dataset=dataset)

    if layer_options is None:
        layer_options = [
            {"name": data.name.split(".")[0].replace("_", " "), "frames": None, "data": data.name}
            for data in [*vectors.all(), *rasters.all()]
        ]

    for layer_info in layer_options:
        layer = Layer.objects.create(
            dataset=dataset,
            name=layer_info.get("name", dataset.name),
            metadata=layer_info.get("metadata", {}),
        )
        frames = layer_info.get("frames")
        if frames is None:
            frames = []
            kwargs = {"dataset": dataset}
            data_name = layer_info.get("data")
            source_file_names = layer_info.get("source_files")
            if data_name is not None:
                kwargs["name"] = data_name
            if source_file_names is not None:
                kwargs["source_file__name__in"] = source_file_names

            for layer_data in [
                *VectorData.objects.filter(**kwargs).order_by("name").all(),
                *RasterData.objects.filter(**kwargs).order_by("name").all(),
            ]:
                frame_property = layer_info.get("frame_property")
                additional_filters = layer_info.get("additional_filters", {})
                metadata = layer_data.metadata or {}
                bands = metadata.get("bands")
                raster_frames = metadata.get("frames")
                summary = layer_data.summary if hasattr(layer_data, "summary") else {}
                properties = summary.get("properties")
                if properties and frame_property and frame_property in properties:
                    property_summary = properties.get(frame_property)
                    if property_summary is not None:
                        value_set = property_summary.get("value_set")
                        if value_set is not None:
                            for value in value_set:
                                frames.append(
                                    {
                                        "name": value,
                                        "index": len(frames),
                                        "data": layer_data.name,
                                        "source_filters": dict(
                                            **{frame_property: value}, **additional_filters
                                        ),
                                    }
                                )
                        value_range = property_summary.get("range")
                        if value_range is not None:
                            for i in range(*value_range):
                                frames.append(
                                    {
                                        "name": f"Frame {i}",
                                        "index": len(frames),
                                        "data": layer_data.name,
                                        "source_filters": dict(
                                            **{frame_property: i}, **additional_filters
                                        ),
                                    }
                                )
                elif frame_property == "frame" and raster_frames and len(raster_frames) > 1:
                    for raster_frame in raster_frames:
                        i = raster_frame.get("Index")
                        frames.append(
                            {
                                "name": i,
                                "index": i,
                                "data": layer_data.name,
                                "source_filters": {"frame": i},
                            }
                        )
                elif frame_property == "band" and bands and len(bands) > 1:
                    for band in bands:
                        frames.append(
                            {
                                "name": band,
                                "index": len(frames),
                                "data": layer_data.name,
                                "source_filters": {"band": band},
                            }
                        )
                else:
                    frames.append(
                        {
                            "name": layer_data.name,
                            "index": len(frames),
                            "data": layer_data.name,
                            "source_filters": {},
                        }
                    )
        for i, frame_info in enumerate(frames):
            index = frame_info.get("index", i)
            data_name = frame_info.get("data")
            if data_name:
                vector, raster = None, None
                vectors = VectorData.objects.filter(dataset=dataset, name=data_name)
                rasters = RasterData.objects.filter(dataset=dataset, name=data_name)
                if vectors.count():
                    vector = vectors.first()
                if rasters.count():
                    raster = rasters.first()
                LayerFrame.objects.create(
                    name=frame_info.get("name", f"Frame {index}"),
                    layer=layer,
                    index=index,
                    vector=vector,
                    raster=raster,
                    source_filters=frame_info.get("source_filters", {}),
                )

    # Default empty-params previews (no Project/LayerStyle required).
    # Match the surrounding conversion mode: sync ingest must generate
    # previews inline (no Celery worker required).
    for layer in Layer.objects.filter(dataset=dataset):
        if layer.is_multiframe_raster():
            if task_result is not None:
                task_result.write_status(f"Generating frame previews for layer {layer.name}...")
            # All Dataset Preview tasks are run synchronously.
            invalidate_and_enqueue_layer_previews(layer, {}, run_mode=TaskRunMode.SYNC)


@shared_task
def convert_dataset(  # noqa: PLR0913
    dataset_id,
    layer_options=None,
    network_options=None,
    region_options=None,
    result_id=None,
    *,
    run_mode: TaskRunMode | str = TaskRunMode.ASYNC,
):
    # Celery JSON may deserialize StrEnum kwargs as plain strings.
    run_mode = TaskRunMode(run_mode)
    dataset = Dataset.objects.get(id=dataset_id)
    dataset.processing = True
    dataset.save()

    result = None
    if result_id:
        with contextlib.suppress(TaskResult.DoesNotExist):
            result = TaskResult.objects.get(id=result_id)

    VectorData.objects.filter(dataset=dataset).delete()
    RasterData.objects.filter(dataset=dataset).delete()

    for file_to_convert in FileItem.objects.filter(dataset=dataset):
        if result is not None:
            result.write_status(f"Converting file {file_to_convert.name}...")
        convert_file_item(file_to_convert)

    vectors = VectorData.objects.filter(dataset=dataset)
    for vector_data in vectors.all():
        if result is not None:
            result.write_status(f"Processing vector data {vector_data.name}...")

        if network_options:
            create_network(vector_data, network_options)
        elif region_options:
            create_source_regions(vector_data, region_options)
        else:
            create_vector_features(vector_data)

        vector_data.get_summary()

    create_layers_and_frames(
        dataset,
        layer_options,
        task_result=result,
        run_mode=run_mode,
    )

    dataset.processing = False
    dataset.save()

    if result is not None:
        result.complete()
