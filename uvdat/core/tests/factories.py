from __future__ import annotations

from pathlib import Path

from django.contrib.auth.models import User
from django.contrib.gis.geos import LineString, Point
import factory.django
from factory.faker import faker
import factory.fuzzy

from uvdat.core.models import (
    Dataset,
    FileItem,
    Layer,
    LayerFrame,
    LayerStyle,
    Project,
    RasterData,
    VectorData,
)
from uvdat.core.models.networks import Network, NetworkEdge, NetworkNode


class FuzzyPointField(factory.fuzzy.BaseFuzzyAttribute):
    """Yield random point."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def fuzz(self):
        fake = faker.Faker()
        return Point((fake.latitude(), fake.longitude()))


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Faker("user_name")
    email = factory.Faker("safe_email")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")


class SuperUserFactory(UserFactory):
    class Meta:
        model = User

    username = factory.Faker("user_name")
    email = factory.Faker("safe_email")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    is_superuser = True


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    name = factory.Faker("name")
    default_map_center = FuzzyPointField()
    default_map_zoom = factory.Faker("pyfloat", min_value=0, max_value=22)


class DatasetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Dataset

    name = factory.Faker("name")
    category = factory.Faker(
        "random_element",
        elements=[
            "climate",
            "elevation",
            "region",
            "flood",
            "transportation",
            "energy",
        ],
    )


class FileItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FileItem

    name = factory.Faker("name")
    dataset = factory.SubFactory(DatasetFactory)
    file_type = "geojson"
    file_size = 100
    file = factory.django.FileField(
        filename=factory.Faker("file_name", extension=factory.SelfAttribute("...file_type")),
        data=factory.Faker("binary", length=factory.SelfAttribute("...file_size")),
    )


class RasterDataFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RasterData

    name = factory.Faker("name")
    dataset = factory.SubFactory(DatasetFactory)
    cloud_optimized_geotiff = factory.django.FileField(
        filename=factory.Faker("file_name", extension="tif"),
        from_path=Path(__file__).parent / "data" / "sample_cog.tif",
    )


class VectorDataFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VectorData

    name = factory.Faker("name")
    dataset = factory.SubFactory(DatasetFactory)
    geojson_data = factory.django.FileField(
        filename=factory.Faker("file_name", extension="json"),
        from_path=Path(__file__).parent / "data" / "sample_geo.json",
    )


class LayerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Layer

    name = factory.Faker("name")
    dataset = factory.SubFactory(DatasetFactory)


class LayerFrameFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LayerFrame

    name = factory.Faker("name")
    layer = factory.SubFactory(LayerFactory)
    vector = factory.SubFactory(VectorDataFactory)
    raster = factory.SubFactory(RasterDataFactory)


class LayerStyleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LayerStyle

    name = factory.Faker("name")
    layer = factory.SubFactory(LayerFactory)
    project = factory.SubFactory(ProjectFactory)
    default_frame = factory.fuzzy.FuzzyInteger(1, 10)
    opacity = factory.fuzzy.FuzzyFloat(0.0, 1.0)


class NetworkFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Network

    vector_data = factory.SubFactory(VectorDataFactory)


class NetworkNodeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NetworkNode

    name = factory.Faker("name")
    network = factory.SubFactory(NetworkFactory)
    location = FuzzyPointField()


class NetworkEdgeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NetworkEdge

    name = factory.Faker("name")
    network = factory.SubFactory(NetworkFactory)

    # TODO: Fix bug where both of these fields point to the same node
    # Ensure the edge and both nodes are in the same network
    from_node = factory.SubFactory(NetworkNodeFactory, network=factory.SelfAttribute("..network"))
    to_node = factory.SubFactory(NetworkNodeFactory, network=factory.SelfAttribute("..network"))

    @factory.lazy_attribute
    def line_geometry(self):
        return LineString(self.from_node.location, self.to_node.location)
