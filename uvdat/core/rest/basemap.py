from __future__ import annotations

from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import Basemap
from uvdat.core.rest.access_control import GuardianFilter, GuardianPermission
from uvdat.core.rest.serializers import BasemapSerializer


class BasemapViewSet(ModelViewSet):
    queryset = Basemap.objects.all()
    serializer_class = BasemapSerializer
    permission_classes = [GuardianPermission]
    filter_backends = [GuardianFilter]
