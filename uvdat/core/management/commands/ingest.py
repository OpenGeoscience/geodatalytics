from __future__ import annotations

from datetime import UTC, datetime
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
from typing import Any, Literal, TypedDict

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.core.files import File
from django.db.models import Sum
from django.db.models.functions import Coalesce
import djclick as click
import pooch

from uvdat.core.frame_previews.preview_regeneration import invalidate_and_enqueue_previews
from uvdat.core.models import Chart, Dataset, FileItem, Layer, Project
from uvdat.core.tasks.frame_preview import ensure_default_layer_style

DATA_FOLDER = Path(os.environ.get("INGEST_BIND_MOUNT_POINT", "sample_data"))
DOWNLOADS_FOLDER = DATA_FOLDER / "downloads"
VALID_TYPES = ["Project", "Dataset", "Chart"]


class ProjectItem(TypedDict):
    type: Literal["Project"]
    name: str
    default_map_center: list[float]
    default_map_zoom: float
    datasets: list[str]
    action: Literal["replace"] | None


class FrameInfo(TypedDict, total=False):
    name: str
    index: int
    data: str
    source_filters: dict[str, Any]


class LayerInfo(TypedDict, total=False):
    name: str
    frames: list[FrameInfo] | None
    data: str
    source_file: str
    frame_property: str
    additional_filters: dict[str, Any]


class DatasetItem(TypedDict):
    type: Literal["Dataset"]
    name: str
    description: str
    category: str | None
    project: str
    file: str
    layers: list[LayerInfo] | None
    conversion_script: (
        str | None
    )  # Relative path to python file used for conversion with function convert_dataset
    network_options: dict[str, Any] | None
    region_options: dict[str, Any] | None
    action: Literal["redownload", "replace"] | None


class FileItemType(TypedDict):
    name: str
    url: str | None
    path: str
    hash: str | None
    file_type: str
    file_size: int
    metadata: dict[str, Any] | None
    index: int


class ConversionOptions(TypedDict):
    labels: str
    datasets: list[str]
    palette: dict[str, str]


class ChartFileInfo(TypedDict):
    url: str
    hash: str
    path: str


class ChartItem(TypedDict, total=False):
    name: str
    type: Literal["Chart"]
    description: str
    project: str
    files: list[ChartFileInfo]
    editable: bool
    metadata: dict[str, Any]
    chart_options: dict[str, Any]
    conversion_options: ConversionOptions


def ingest_file(file_info, *, index=0, dataset=None, chart=None, replace=False, skip_cache=False):  # noqa: PLR0913
    file_path = file_info.get("path")
    file_name = file_info.get("name", file_path.split("/")[-1])
    file_url = file_info.get("url")
    file_hash = file_info.get("hash")
    file_metadata = file_info.get("metadata", {})

    file_location = DOWNLOADS_FOLDER / file_path
    file_type = file_path.split(".")[-1]
    file_location.parent.mkdir(parents=True, exist_ok=True)

    if file_location.exists() and skip_cache:
        file_location.unlink()

    if file_url is not None:
        pooch.retrieve(
            url=file_url,
            fname=file_location.name,
            path=file_location.parent,
            known_hash=file_hash,
            progressbar=True,
        )
    elif not file_location.exists():
        raise click.ClickException("File path does not exist and no download URL was specified.")

    create_new = True
    existing = FileItem.objects.filter(dataset=dataset, name=file_name)
    if existing.count():
        if replace:
            existing.delete()
        else:
            create_new = False
            click.secho(f"\t\t FileItem {file_name} already exists.", fg="yellow")

    if create_new:
        new_file_item = FileItem.objects.create(
            name=file_name,
            dataset=dataset,
            chart=chart,
            file_type=file_type,
            file_size=file_location.stat().st_size,
            metadata=dict(
                **file_metadata,
                uploaded=str(datetime.now(tz=UTC)),
            ),
            index=index,
        )
        click.secho(f"FileItem {new_file_item.name} created.", fg="green")
        with file_location.open("rb") as f:
            new_file_item.file.save(file_path, File(f))


def generate_ingest_multiframe_previews(converted_dataset_names: set[str]) -> int:
    if not converted_dataset_names:
        return 0
    style_count = 0
    for project in Project.objects.filter(datasets__name__in=converted_dataset_names).distinct():
        layers = Layer.objects.filter(
            dataset__name__in=converted_dataset_names,
            dataset__in=project.datasets.all(),
        )
        for layer in layers:
            if not layer.is_multiframe_raster():
                continue
            style = ensure_default_layer_style(layer, project)
            invalidate_and_enqueue_previews(style)
            style_count += 1
    return style_count


def ingest_projects(data: list[ProjectItem], *, replace=False) -> None:
    for project in data:
        click.echo(f"\t- {project['name']}")
        existing = Project.objects.filter(name=project["name"])
        if (existing.count() and replace) or project.get("action") == "replace":
            existing.delete()
        project_for_setting, created = Project.objects.get_or_create(
            name=project["name"],
            defaults={
                "default_map_center": Point(*project["default_map_center"]),
                "default_map_zoom": project["default_map_zoom"],
            },
        )
        if created:
            click.secho(f"Project {project_for_setting.name} created.", fg="green")

            superuser = User.objects.filter(is_superuser=True).first()
            if superuser is None:
                raise click.ClickException("Please create at least one superuser")
            project_for_setting.set_permissions(owner=superuser)
        else:
            click.secho(
                f"Project {project_for_setting.name} already exists, not importing.",
                fg="cyan",
            )

        # log warning if any datasets are missing
        missing_datasets = set(project["datasets"]) - set(
            Dataset.objects.values_list("name", flat=True)
        )
        if missing_datasets:
            project_name = project_for_setting.name
            missing = ", ".join(missing_datasets)
            click.secho(f"Missing datasets for project {project_name}: {missing}", fg="yellow")

        # Update datasets in project
        project_for_setting.datasets.set(Dataset.objects.filter(name__in=project["datasets"]))


def ingest_charts(data: list[ChartItem], *, replace=False, skip_cache=False) -> None:
    for chart in data:
        click.echo(f"\t- {chart['name']}")
        existing = Chart.objects.filter(name=chart["name"])
        create_new = True
        if existing.count():
            if replace:
                existing.delete()
            else:
                chart_for_conversion = existing.first()
                create_new = False

        if create_new:
            new_chart = Chart.objects.create(
                name=chart["name"],
                description=chart["description"],
                project=Project.objects.get(name=chart["project"]),
                chart_options=chart.get("chart_options"),
                metadata=chart.get("metadata"),
                editable=chart.get("editable", False),
            )
            click.secho(f"\t\t Chart {new_chart.name} created.", fg="green")
            for index, file_info in enumerate(chart.get("files", [])):
                ingest_file(file_info, index=index, chart=new_chart, skip_cache=skip_cache)
            chart_for_conversion = new_chart

            click.echo(f"\t\t Converting data for {chart_for_conversion.name}.")
            chart_for_conversion.spawn_conversion_task(
                conversion_options=chart.get("conversion_options"),
                asynchronous=False,
            )
        else:
            click.secho(
                f"\t\t Chart {chart['name']} already exists, not importing/converting.",
                fg="cyan",
            )


def run_conversion_script(script_path: Path, dataset_for_conversion, dataset) -> None:
    path = script_path.resolve()
    parent = path.parent

    if (parent / "__init__.py").exists():
        # Treat as package
        click.echo(f"Found __init__.py for {script_path}, adding to sys.path")
        sys.path.append(str(parent.parent))  # add the package root
        module_name = f"{parent.name}.{path.stem}"
        module = importlib.import_module(module_name)
    else:
        # Load as standalone script
        spec = importlib.util.spec_from_file_location("custom_conversion", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    # Call convert_dataset if it exists
    if hasattr(module, "convert_dataset"):
        module.convert_dataset(dataset_for_conversion, dataset)
    else:
        raise AttributeError(f"Script {script_path} has no convert_dataset() function.")


def default_conversion_process(dataset: Dataset, options: DatasetItem):
    click.echo(f"\tConverting data for {dataset.name}...")
    dataset.spawn_conversion_task(
        layer_options=options.get("layers"),
        network_options=options.get("network_options"),
        region_options=options.get("region_options"),
        asynchronous=False,
    )


def ingest_datasets(
    data: list[DatasetItem], json_file_path: Path, *, replace=False, skip_cache=False
) -> set[str]:
    converted_dataset_names: set[str] = set()
    superuser = User.objects.filter(is_superuser=True).first()
    if superuser is None:
        raise click.ClickException("Please create at least one superuser")
    for _dataset_index, dataset in enumerate(data):
        click.echo(f"\t- {dataset['name']}")
        create_new = True
        existing = Dataset.objects.filter(name=dataset["name"])
        if existing.count():
            if replace or skip_cache or dataset.get("action", False) in ["redownload", "replace"]:
                existing.delete()
            else:
                dataset_for_conversion = existing.first()
                create_new = False

        if create_new:
            # Create dataset
            new_dataset = Dataset.objects.create(
                name=dataset["name"],
                description=dataset["description"],
                category=dataset["category"],
                metadata=dataset.get("metadata", {}),
            )
            for index, file_info in enumerate(dataset.get("files", [])):
                ingest_file(
                    file_info,
                    index=index,
                    dataset=new_dataset,
                    replace=replace or dataset.get("action", False) == "replace",
                    skip_cache=skip_cache or dataset.get("action", False) == "redownload",
                )
            dataset_for_conversion = new_dataset

            dataset_size_bytes = FileItem.objects.filter(
                dataset=dataset_for_conversion,
            ).aggregate(total=Coalesce(Sum("file_size"), 0))["total"]
            dataset_size_mb = dataset_size_bytes >> 20
            click.secho(
                f"\t\t Dataset {dataset_for_conversion.name} of size {dataset_size_mb} MB.",
                fg="green",
            )
            conversion_script = dataset.get("conversion_script")
            if conversion_script:
                click.echo(f"\tUsing custom conversion script: {conversion_script}")
                # the conversion script is relative to the json file path, make sure it exists
                full_path = json_file_path.parent / conversion_script
                if not full_path.exists():
                    click.secho(f"Conversion script {full_path} does not exist.", fg="red")
                else:
                    run_conversion_script(full_path, dataset_for_conversion, dataset)
            else:
                default_conversion_process(dataset_for_conversion, dataset)
            click.secho(
                f"\t\t Dataset {dataset_for_conversion.name} converted.",
                fg="green",
            )
            converted_dataset_names.add(dataset["name"])
        else:
            click.secho(
                f"\t\t Dataset {dataset['name']} already exists, not importing/converting",
                fg="cyan",
            )

        dataset_for_conversion.set_tags(dataset.get("tags"))
        dataset_for_conversion.set_owner(superuser)

    return converted_dataset_names


@click.command()
@click.argument("file_path")
@click.option(
    "--replace",
    is_flag=True,
    default=False,
    help="Replace existing Models in Database instead of skipping or updating.",
)
@click.option(
    "--clear",
    is_flag=True,
    default=False,
    help="Clear All data in the database for all Projects, Datasets, and Charts",
)
@click.option(
    "--skip-cache",
    is_flag=True,
    default=False,
    help="Do not use cached downloaded files",
)
def ingest(*, file_path, replace, clear, skip_cache):
    file_path = DATA_FOLDER / file_path
    if not file_path.exists():
        click.echo(f"File {file_path} does not exist.")
        return
    if clear:
        if click.confirm("Are you sure you want to delete ALL Project, Dataset and Chart models?"):
            Project.objects.all().delete()
            Dataset.objects.all().delete()
            Chart.objects.all().delete()
            click.secho(
                "Successfully deleted all Project, Dataset, and Chart models",
                fg="green",
            )
        else:
            click.secho("Aborted deletion of models", fg="yellow")
            return
    with file_path.open("r") as f:
        json_data = json.load(f)

    projects = []
    datasets = []
    charts = []
    for item in json_data:
        if item.get("type") not in VALID_TYPES:
            click.secho(f"Invalid item type: {item.get('type')}", fg="red")
            continue

        if item["type"] == "Project":
            projects.append(item)
        elif item["type"] == "Dataset":
            datasets.append(item)
        elif item["type"] == "Chart":
            charts.append(item)
    click.echo("Ingesting Datasets:")
    converted_dataset_names = ingest_datasets(
        datasets, file_path, replace=replace, skip_cache=skip_cache
    )
    click.echo("Ingesting Projects:")
    ingest_projects(projects, replace=replace)
    click.echo("Ingesting Charts:")
    ingest_charts(charts, replace=replace, skip_cache=skip_cache)

    preview_count = generate_ingest_multiframe_previews(converted_dataset_names)
    if preview_count:
        click.echo(f"Generated multiframe raster previews for {preview_count} layer style(s).")

    click.secho("Ingestion complete.", fg="green")
