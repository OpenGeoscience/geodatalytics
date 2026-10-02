from __future__ import annotations

from rest_framework.viewsets import ModelViewSet

from uvdat.core.models import Network, NetworkAnimation, NetworkState
from uvdat.core.rest.serializers import (
    NetworkAnimationSerializer,
    NetworkSerializer,
    NetworkStateSerializer,
)


class NetworkViewSet(ModelViewSet):
    queryset = Network.objects.all()
    serializer_class = NetworkSerializer


class NetworkAnimationViewSet(ModelViewSet):
    queryset = NetworkAnimation.objects.all()
    serializer_class = NetworkAnimationSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        project_id: str | None = self.request.query_params.get("project")
        if project_id is not None and project_id.isdigit():
            qs = qs.filter(project=int(project_id))
        network_id: str | None = self.request.query_params.get("network")
        if network_id is not None and network_id.isdigit():
            qs = qs.filter(network=int(network_id))
        return qs

    def perform_create(self, serializer):
        instance = serializer.save()
        # Automatically create a first state
        state = NetworkState.objects.create(
            animation=instance,
            index=0,
        )
        state.update_components()


class NetworkStateViewSet(ModelViewSet):
    queryset = NetworkState.objects.prefetch_related(
        "deactivated_nodes", "components", "components__nodes"
    ).all()
    serializer_class = NetworkStateSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        project_id: str | None = self.request.query_params.get("project")
        if project_id is not None and project_id.isdigit():
            qs = qs.filter(animation__project=int(project_id))
        network_id: str | None = self.request.query_params.get("network")
        if network_id is not None and network_id.isdigit():
            qs = qs.filter(animation__network=int(network_id))
        anim_id: str | None = self.request.query_params.get("animation")
        if anim_id is not None and anim_id.isdigit():
            qs = qs.filter(animation=int(anim_id))
        return qs

    def perform_create(self, serializer):
        instance = serializer.save()
        instance.update_components()

    def perform_destroy(self, instance):
        # Update other animation state indices
        other_states = instance.animation.states.exclude(id=instance.id).order_by("index")
        for i, state in enumerate(other_states):
            state.index = i
        NetworkState.objects.bulk_update(other_states, ["index"])
        instance.delete()
