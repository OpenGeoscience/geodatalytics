from __future__ import annotations

from django.contrib import admin

from uvdat.core.models import (
    Basemap,
    Chart,
    ColorConfig,
    Colormap,
    ColormapConfig,
    Dataset,
    FileItem,
    FilterConfig,
    Layer,
    LayerFrame,
    LayerStyle,
    Network,
    NetworkEdge,
    NetworkNode,
    Project,
    RasterData,
    RasterFramePreview,
    Region,
    SizeConfig,
    SizeRangeConfig,
    TaskResult,
    VectorData,
    VectorFeature,
    ViewState,
)


@admin.register(Basemap)
class BasemapAdmin(admin.ModelAdmin):
    list_display = ["id", "name"]


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["id", "name"]


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "category"]


@admin.register(FileItem)
class FileItemAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "dataset", "chart"]


@admin.register(Chart)
class ChartAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "editable"]


@admin.register(Layer)
class LayerAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "dataset"]


@admin.register(LayerFrame)
class LayerFrameAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "index", "layer"]


@admin.register(LayerStyle)
class LayerStyleAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "layer"]


@admin.register(RasterFramePreview)
class RasterFramePreviewAdmin(admin.ModelAdmin):
    list_display = ["id", "layer_frame", "style_fingerprint", "raster_style_params", "width", "height", "status"]
    list_select_related = ["layer_frame"]

@admin.register(Colormap)
class ColormapAdmin(admin.ModelAdmin):
    list_display = ["id", "name"]


@admin.register(ColorConfig)
class ColorConfigAdmin(admin.ModelAdmin):
    list_display = ["id", "style", "name"]


@admin.register(ColormapConfig)
class ColormapConfigAdmin(admin.ModelAdmin):
    list_display = ["id", "colormap", "color_by"]


@admin.register(SizeConfig)
class SizeConfigAdmin(admin.ModelAdmin):
    list_display = ["id", "style", "name"]


@admin.register(SizeRangeConfig)
class SizeRangeConfigAdmin(admin.ModelAdmin):
    list_display = ["id", "minimum", "maximum", "size_by"]


@admin.register(FilterConfig)
class FilterConfigAdmin(admin.ModelAdmin):
    list_display = ["id", "style", "filter_by"]


@admin.register(RasterData)
class RasterDataAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "source_file"]


@admin.register(VectorData)
class VectorDataAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "source_file"]


@admin.register(VectorFeature)
class VectorFeatureAdmin(admin.ModelAdmin):
    list_display = ["id", "dataset"]
    list_select_related = ["vector_data__dataset"]


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "dataset"]


@admin.register(Network)
class NetworkAdmin(admin.ModelAdmin):
    list_display = ["id", "category", "dataset"]
    list_select_related = ["vector_data__dataset"]


@admin.register(NetworkEdge)
class NetworkEdgeAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "network", "dataset"]
    list_select_related = ["network__vector_data__dataset"]


@admin.register(NetworkNode)
class NetworkNodeAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "network", "dataset"]
    list_select_related = ["network__vector_data__dataset"]


@admin.register(TaskResult)
class TaskResultAdmin(admin.ModelAdmin):
    list_display = ["id", "creator", "task_type", "inputs"]


@admin.register(ViewState)
class ViewStateAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "project"]
