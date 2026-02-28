from __future__ import annotations

import json

from django.contrib.gis.db.models import Extent
from django.db import connection
from django.http import HttpResponse
from django_large_image.rest import LargeImageFileDetailMixin
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from uvdat.core.models import RasterData, VectorData, VectorFeature
from uvdat.core.rest.access_control import GuardianFilter, GuardianPermission
from uvdat.core.rest.explorer import IPyLeafletTokenAuth
from uvdat.core.rest.serializers import RasterDataSerializer, VectorDataSerializer

VECTOR_TILE_SQL = """
WITH
tilenv as (
    SELECT ST_TRANSFORM(ST_TileEnvelope(%(z)s, %(x)s, %(y)s), %(srid)s) as te
),
tilenvbounds as (
    SELECT
        ST_XMin(te) as xmin,
        ST_YMin(te) as ymin,
        ST_XMax(te) as xmax,
        ST_YMax(te) as ymax,
        (ST_XMax(te) - ST_XMin(te)) / 4 as segsize
    FROM tilenv
),
env as (
    SELECT ST_Segmentize(
        ST_MakeEnvelope(
            xmin,
            ymin,
            xmax,
            ymax,
            %(srid)s
        ),
        segsize
    ) as seg
    FROM tilenvbounds
),
bounds as (
    SELECT
        seg as geom,
        seg::box2d as b2d
    FROM env
),
mvtgeom as (
    SELECT
        ST_AsMVTGeom(
            ST_Transform(t.geometry, %(srid)s),
            bounds.b2d
        ) AS geom,
    t.properties as properties
    FROM
        core_vectorfeature t,
        bounds
    WHERE
        t.vector_data_id = %(vector_data_id)s
        AND ST_Intersects(
            ST_Transform(t.geometry, %(srid)s),
            ST_Transform(bounds.geom, %(srid)s)
        )
        REPLACE_WITH_FILTERS
)
SELECT ST_AsMVT(mvtgeom.*) FROM mvtgeom
;
"""


def get_filter_string(filters: dict | None = None):
    if filters is None:
        return ""

    return_str = ""
    for key, value in filters.items():
        key_path = key.replace(".", ",")
        return_str += f" AND t.properties #>> '{{{key_path}}}' = '{value}'"
    return return_str


class GenericDataViewSet(GenericViewSet, mixins.RetrieveModelMixin):
    permission_classes = [GuardianPermission]
    filter_backends = [GuardianFilter]

    @property
    def authentication_classes(self):
        auth_classes = [IPyLeafletTokenAuth]

        existing_auth_classes = super().authentication_classes
        if existing_auth_classes is not None:
            auth_classes = existing_auth_classes + auth_classes

        return auth_classes


class RasterDataViewSet(GenericDataViewSet, LargeImageFileDetailMixin):
    queryset = RasterData.objects.select_related("dataset").all()
    serializer_class = RasterDataSerializer
    FILE_FIELD_NAME = "cloud_optimized_geotiff"

    @action(
        detail=True,
        methods=["get"],
        url_path=r"raster-data/(?P<resolution>[\d*\.?\d*]+)",
        url_name="raster_data",
    )
    def get_raster_data(self, request, resolution: str = "1", **kwargs):
        raster_data = self.get_object()
        data = raster_data.get_image_data(float(resolution))
        return HttpResponse(json.dumps(data), status=200)


class VectorDataViewSet(GenericDataViewSet):
    queryset = VectorData.objects.select_related("dataset").all()
    serializer_class = VectorDataSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = VectorDataSerializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def bounds(self, request, **kwargs):
        instance = self.get_object()
        features = VectorFeature.objects.filter(vector_data=instance)
        extent = features.aggregate(Extent("geometry")).get("geometry__extent")
        return Response(extent, status=200)

    @action(detail=True, methods=["get"])
    def summary(self, request, **kwargs):
        instance = self.get_object()
        return Response(instance.get_summary(), status=200)

    @action(
        detail=True,
        methods=["get"],
        url_path=r"tiles/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)",
        url_name="tiles",
    )
    def get_vector_tile(self, request, pk: str, x: str, y: str, z: str):
        filters = request.query_params.copy()
        filters.pop("token", None)
        filters_string = get_filter_string(filters)
        with connection.cursor() as cursor:
            cursor.execute(
                VECTOR_TILE_SQL.replace("REPLACE_WITH_FILTERS", filters_string),
                {
                    "z": z,
                    "x": x,
                    "y": y,
                    "srid": 3857,
                    "vector_data_id": pk,
                },
            )
            row = cursor.fetchone()

        tile = row[0]
        return HttpResponse(
            tile,
            content_type="application/octet-stream",
            status=200 if tile else 204,
        )
