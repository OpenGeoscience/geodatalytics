from __future__ import annotations

from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.contrib.gis.serializers import geojson
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from uvdat.core.models import (
    Basemap,
    Chart,
    Colormap,
    Dataset,
    DatasetTag,
    FileItem,
    Layer,
    LayerFrame,
    LayerStyle,
    Network,
    NetworkEdge,
    NetworkNode,
    Project,
    RasterData,
    Region,
    TaskResult,
    VectorData,
    ViewState,
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "is_superuser"]


class BasemapSerializer(serializers.ModelSerializer):
    class Meta:
        model = Basemap
        fields = "__all__"


class ProjectPermissionsSerializer(serializers.Serializer):
    owner_id = serializers.IntegerField()
    collaborator_ids = serializers.ListField(child=serializers.IntegerField())
    follower_ids = serializers.ListField(child=serializers.IntegerField())

    def validate(self, attrs):
        collaborators = set(attrs["collaborator_ids"])
        followers = set(attrs["follower_ids"])
        owner = attrs["owner_id"]

        if collaborators & followers or owner in (collaborators | followers):
            raise serializers.ValidationError(
                "A user cannot have multiple permissions on a single project"
            )

        return super().validate(attrs)


class ProjectSerializer(serializers.ModelSerializer):
    default_map_center = serializers.SerializerMethodField("get_center")
    owner = serializers.SerializerMethodField("get_owner")
    collaborators = serializers.SerializerMethodField("get_collaborators")
    followers = serializers.SerializerMethodField("get_followers")
    item_counts = serializers.SerializerMethodField("get_item_counts")

    def get_center(self, obj):
        # Web client expects Lon, Lat
        if obj.default_map_center:
            return [obj.default_map_center.x, obj.default_map_center.y]
        return None

    def get_owner(self, obj: Project):
        return UserSerializer(obj.owner()).data

    def get_collaborators(self, obj: Project):
        return [UserSerializer(user).data for user in obj.collaborators()]

    def get_followers(self, obj: Project):
        return [UserSerializer(user).data for user in obj.followers()]

    def get_item_counts(self, obj):
        return {
            "datasets": obj.datasets.count(),
            "charts": obj.charts.count(),
            "analyses": obj.task_results.count(),
        }

    def to_internal_value(self, data):
        center = data.get("default_map_center")
        data = super().to_internal_value(data)
        if isinstance(center, list):
            data["default_map_center"] = Point(center[0], center[1])
        return data

    def validate_allow_unauthenticated(self, value):
        request = self.context.get("request")
        if value and not request.user.is_superuser:
            raise ValidationError("Only superusers can allow unauthenticated access to a project.")
        return value

    class Meta:
        model = Project
        fields = "__all__"


class TagsField(serializers.Field):
    def to_internal_value(self, data):
        if not isinstance(data, list) or any(not isinstance(v, str) for v in data):
            raise serializers.ValidationError(
                "Dataset tags must be expressed as a list of strings."
            )
        for tag in data:
            DatasetTag.objects.get_or_create(tag=tag)
        return DatasetTag.objects.filter(tag__in=data)

    def to_representation(self, value):
        return [t.tag for t in value.all()]


class DatasetSerializer(serializers.ModelSerializer):
    owner = serializers.SerializerMethodField("get_owner")
    n_layers = serializers.SerializerMethodField("get_n_layers")
    tags = TagsField()

    def get_owner(self, obj):
        owner = obj.owner()
        if owner is not None:
            return UserSerializer(owner).data
        return None

    def get_n_layers(self, obj):
        return Layer.objects.filter(dataset=obj).count()

    class Meta:
        model = Dataset
        fields = "__all__"


class FileItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileItem
        fields = "__all__"


class ChartSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chart
        fields = "__all__"


class ColormapSerializer(serializers.ModelSerializer):
    class Meta:
        model = Colormap
        fields = "__all__"


class LayerStyleSerializer(serializers.ModelSerializer):
    is_default = serializers.SerializerMethodField("get_is_default")

    def get_is_default(self, obj):
        if obj.layer.default_style is None:
            return False
        return obj.layer.default_style.id == obj.id

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["style_spec"] = instance.repr_style_configs()
        return data

    def create(self, validated_data):
        style_spec = self.initial_data.pop("style_spec", None)
        instance = super().create(validated_data)
        instance.save_style_configs(style_spec)
        return instance

    def update(self, instance, validated_data):
        style_spec = self.initial_data.pop("style_spec", None)
        instance.save_style_configs(style_spec)
        return super().update(instance, validated_data)

    class Meta:
        model = LayerStyle
        exclude = ["default_frame", "opacity"]


class LayerSerializer(serializers.ModelSerializer):
    default_style = LayerStyleSerializer()

    class Meta:
        model = Layer
        fields = ["id", "name", "metadata", "dataset", "default_style"]


class VectorDataSerializer(serializers.ModelSerializer):
    file_size = serializers.SerializerMethodField("get_file_size")

    def get_file_size(self, obj):
        if obj.geojson_data:
            return obj.geojson_data.size
        return -1

    class Meta:
        model = VectorData
        fields = "__all__"


class RasterDataSerializer(serializers.ModelSerializer):
    file_size = serializers.SerializerMethodField("get_file_size")

    def get_file_size(self, obj):
        if obj.cloud_optimized_geotiff:
            return obj.cloud_optimized_geotiff.size
        return -1

    class Meta:
        model = RasterData
        fields = "__all__"


class LayerFrameSerializer(serializers.ModelSerializer):
    vector = VectorDataSerializer()
    raster = RasterDataSerializer()

    class Meta:
        model = LayerFrame
        fields = "__all__"


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = "__all__"


class RegionFeatureCollectionSerializer(geojson.Serializer):
    # Override this method to ensure the pk field is a number instead of a string
    def get_dump_object(self, obj):
        val = super().get_dump_object(obj)
        val["properties"]["id"] = int(val["properties"].pop("pk"))

        return val


class NetworkNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkNode
        fields = "__all__"


class NetworkEdgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = NetworkEdge
        fields = "__all__"


class NetworkSerializer(serializers.ModelSerializer):
    dataset = serializers.SerializerMethodField("get_dataset")
    nodes = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    def get_dataset(self, obj):
        return obj.vector_data.dataset.id

    class Meta:
        model = Network
        fields = "__all__"


class AnalysisTypeSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    db_value = serializers.CharField(max_length=25)
    description = serializers.CharField(max_length=255)
    details = serializers.CharField(max_length=2048, allow_null=True)
    attribution = serializers.CharField(max_length=255)
    input_options = serializers.JSONField()
    input_types = serializers.JSONField()
    output_types = serializers.JSONField()


class TaskResultSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField("get_name")

    def get_name(self, obj):
        if obj.name and obj.created:
            timestamp = obj.created.strftime("%Y-%m-%d %I:%M %p UTC")
            return f"{timestamp} - {obj.name}"
        return obj.name

    class Meta:
        model = TaskResult
        fields = "__all__"


class ViewStateSerializer(serializers.ModelSerializer):
    map_center = serializers.SerializerMethodField("get_center")

    def get_center(self, obj):
        # Web client expects Lon, Lat
        if obj.map_center:
            return [obj.map_center.x, obj.map_center.y]
        return None

    def to_internal_value(self, data):
        center = data.get("map_center")
        data = super().to_internal_value(data)
        if isinstance(center, list):
            data["map_center"] = Point(center[0], center[1])
        return data

    class Meta:
        model = ViewState
        fields = "__all__"
