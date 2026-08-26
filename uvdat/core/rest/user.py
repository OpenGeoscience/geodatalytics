from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from .serializers import MeSerializer, UserSerializer


class UserViewSet(ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = []

    @action(detail=False, pagination_class=None)
    def me(self, request):
        """Return the currently logged in user's information."""
        if request.user.is_anonymous:
            return HttpResponse(status=204)
        return HttpResponse(json.dumps(MeSerializer(request.user).data), status=200)
