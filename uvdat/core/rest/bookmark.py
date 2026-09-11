from __future__ import annotations

from django.db import transaction
import jsonschema
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import Bookmark, Project
from uvdat.core.rest.serializers import BookmarkSerializer


class BookmarkViewSet(ModelViewSet):
    queryset = Bookmark.objects.all()
    serializer_class = BookmarkSerializer

    def create(self, request, **kwargs):
        project = Project.objects.get(id=request.data.get("project"))
        if not project.user_can_edit(request.user):
            return Response(
                "You do not have permission to create bookmarks in this project.",
                status=403,
            )
        serializer = BookmarkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            try:
                serializer.save()
            except jsonschema.exceptions.ValidationError as e:
                return Response(e.message, status=400)
        return Response(serializer.data, status=200)
