from __future__ import annotations

from django.contrib.gis.db import models as geo_models
from django.db import models
import networkx as nx

from .data import VectorData, VectorFeature
from .layer import Layer
from .project import Project
from .querysets import ProjectQuerySet
from .task_result import TaskResult


class Network(models.Model):
    name = models.CharField(max_length=255, default="Network")
    vector_data = models.ForeignKey(VectorData, on_delete=models.CASCADE, related_name="networks")
    category = models.CharField(max_length=25)
    metadata = models.JSONField(blank=True, null=True)

    project_filter_path = "vector_data__dataset__project"
    objects = ProjectQuerySet.as_manager()

    def __str__(self):
        return f"{self.name} ({self.id})"

    @property
    def dataset(self):
        return self.vector_data.dataset

    def get_graph(self):
        return nx.Graph([(edge.from_node.id, edge.to_node.id) for edge in self.edges.all()])


class NetworkNode(models.Model):
    name = models.CharField(max_length=255)
    vector_feature = models.ForeignKey(
        VectorFeature, on_delete=models.CASCADE, related_name="nodes", null=True
    )
    network = models.ForeignKey(Network, on_delete=models.CASCADE, related_name="nodes")
    metadata = models.JSONField(blank=True, null=True)
    capacity = models.IntegerField(null=True)
    location = geo_models.PointField()

    project_filter_path = "network__vector_data__dataset__project"
    objects = ProjectQuerySet.as_manager()

    def __str__(self):
        return f"{self.name} ({self.id})"

    @property
    def dataset(self):
        return self.network.dataset

    def get_adjacent_nodes(self) -> models.QuerySet:
        entering_node_ids = (
            NetworkEdge.objects.filter(to_node=self.id)
            .values_list("from_node_id", flat=True)
            .distinct()
        )
        exiting_node_ids = (
            NetworkEdge.objects.filter(from_node=self.id)
            .values_list("to_node_id", flat=True)
            .distinct()
        )
        return NetworkNode.objects.exclude(id=self.id).filter(
            models.Q(id__in=entering_node_ids) | models.Q(id__in=exiting_node_ids)
        )


class NetworkEdge(models.Model):
    name = models.CharField(max_length=255)
    vector_feature = models.ForeignKey(
        VectorFeature, on_delete=models.CASCADE, related_name="edges", null=True
    )
    network = models.ForeignKey(Network, on_delete=models.CASCADE, related_name="edges")
    metadata = models.JSONField(blank=True, null=True)
    capacity = models.IntegerField(null=True)
    line_geometry = geo_models.LineStringField()
    directed = models.BooleanField(default=False)
    from_node = models.ForeignKey(NetworkNode, related_name="+", on_delete=models.CASCADE)
    to_node = models.ForeignKey(NetworkNode, related_name="+", on_delete=models.CASCADE)

    project_filter_path = "network__vector_data__dataset__project"
    objects = ProjectQuerySet.as_manager()

    def __str__(self):
        return f"{self.name} ({self.id})"

    @property
    def dataset(self):
        return self.network.dataset


class NetworkAnimation(models.Model):
    name = models.CharField(max_length=255)
    network = models.ForeignKey(Network, on_delete=models.CASCADE, related_name="animations")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="animations")
    task_result = models.ForeignKey(
        TaskResult, on_delete=models.CASCADE, related_name="animations", null=True, blank=True
    )
    sync_layers = models.ManyToManyField(Layer, blank=True)

    project_filter_path = "project"
    objects = ProjectQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "network", "project"], name="unique_name_network_project"
            )
        ]

    def __str__(self):
        return f"Network Animation ({self.id})"


class NetworkState(models.Model):
    animation = models.ForeignKey(NetworkAnimation, on_delete=models.CASCADE, related_name="states")
    index = models.PositiveIntegerField(default=0)
    deactivated_nodes = models.ManyToManyField(NetworkNode, blank=True)

    project_filter_path = "animation__project"
    objects = ProjectQuerySet.as_manager()

    def __str__(self):
        return f"Network State ({self.id})"

    def update_components(self):
        # Check whether component relationships need to be updated
        old_component_spec = sorted(
            [list(c.nodes.values_list("id", flat=True)) for c in self.components.all()],
            key=len,
            reverse=True,
        )
        deactivated_ids = list(self.deactivated_nodes.values_list("id", flat=True))
        if len(deactivated_ids) > 0:
            network_graph = self.animation.network.get_graph()
            network_graph.remove_nodes_from(deactivated_ids)
            components = nx.connected_components(network_graph)
            new_component_spec = sorted(
                [list(c) for c in components if len(c) > 1],
                key=len,
                reverse=True,
            )
        else:
            # no deactivated nodes means all nodes are in one component
            new_component_spec = [[n.id for n in self.animation.network.nodes.all()]]
        # If update necessary, delete old components and create new ones
        if new_component_spec != old_component_spec:
            self.components.all().delete()
            for node_set in new_component_spec:
                component = NetworkComponent.objects.create(state=self)
                component.nodes.set(NetworkNode.objects.filter(id__in=node_set))


class NetworkComponent(models.Model):
    state = models.ForeignKey(NetworkState, on_delete=models.CASCADE, related_name="components")
    nodes = models.ManyToManyField(NetworkNode, blank=True)

    project_filter_path = "state__animation__project"
    objects = ProjectQuerySet.as_manager()

    def __str__(self):
        return f"Network Component ({self.id})"
