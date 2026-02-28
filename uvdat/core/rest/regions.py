from __future__ import annotations

from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet

from uvdat.core.models import Region
from uvdat.core.rest.access_control import GuardianFilter, GuardianPermission

from .serializers import RegionSerializer


class RegionViewSet(mixins.RetrieveModelMixin, mixins.ListModelMixin, GenericViewSet):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer
    permission_classes = [GuardianPermission]
    filter_backends = [GuardianFilter]
