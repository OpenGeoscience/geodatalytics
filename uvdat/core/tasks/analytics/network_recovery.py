from __future__ import annotations

import random

from celery import shared_task
from django.conf import settings
from django.utils import timezone
import networkx as nx
import numpy as np

from uvdat.core.models import Chart, Network, NetworkEdge, NetworkNode, TaskResult

from .analysis_type import AnalysisInputError, AnalysisTask, AnalysisType

RECOVERY_MODES = [
    "random",
    "betweenness",
    "degree",
    "information",
    "eigenvector",
    "load",
    "closeness",
    "second order",
]


class NetworkRecovery(AnalysisType):
    def __init__(self):
        super().__init__()
        self.name = "Network Recovery"
        self.description = (
            "Provide a network failure state and select a "
            "recovery mode to view network recovery priority."
        )
        self.db_value = "network_recovery"
        self.input_types = {
            "network_failure": "TaskResult",
            "recovery_mode": "string",
        }
        self.output_types = {
            "recoveries": "network_animation",
            "gcc_chart": "Chart",
            "resiliency_score": "number",
        }
        self.attribution = "Jack Watson, Northeastern University"

    @classmethod
    def is_enabled(cls):
        return settings.UVDAT_ENABLE_NETWORK_RECOVERY

    def get_input_options(self):
        # Prevent circular import
        from uvdat.core.tasks.analytics import analysis_types  # noqa: PLC0415

        node_failure_analysis_types = [
            at().db_value
            for at in analysis_types
            if at().output_types.get("failures") == "network_animation"
        ]
        return {
            "network_failure": TaskResult.objects.filter(task_type__in=node_failure_analysis_types),
            "recovery_mode": RECOVERY_MODES,
        }

    def run_task(self, *, project, **inputs):
        result = TaskResult.objects.create(
            name="Network Recovery",
            task_type=self.db_value,
            inputs=inputs,
            project=project,
            status="Initializing task...",
        )
        network_recovery.delay(result.id)
        return result

    def validate_inputs(self, inputs):
        super().validate_inputs(inputs)
        mode = inputs.get("recovery_mode")
        if mode not in RECOVERY_MODES:
            raise AnalysisInputError("Recovery mode not a valid option")

    def finalize(self, result):
        pass


def get_network_graph(network):
    network = {
        "nodes": NetworkNode.objects.filter(network=network),
        "edges": NetworkEdge.objects.filter(network=network),
    }
    if len(network.get("nodes")) == 0 and len(network.get("edges")) == 0:
        return None

    # Construct adj list
    edge_list: dict[int, list[int]] = {}
    for e in network.get("edges"):
        if e.from_node.id not in edge_list:
            edge_list[e.from_node.id] = []
        edge_list[e.from_node.id].append(e.to_node.id)
    for edges in edge_list.values():
        edges.sort()
    return nx.from_dict_of_lists(edge_list)


# Authored by Jack Watson
# Takes in a second argument, measure, which is a string specifying the centrality
# measure to calculate.
def sort_graph_centrality(g, measure):
    if measure == "betweenness":
        cent = nx.betweenness_centrality(g)  # get betweenness centrality
    elif measure == "degree":
        cent = nx.degree_centrality(g)
    elif measure == "information":
        cent = nx.current_flow_closeness_centrality(g)
    elif measure == "eigenvector":
        cent = nx.eigenvector_centrality(g, 10000)
    elif measure == "load":
        cent = nx.load_centrality(g)
    elif measure == "closeness":
        cent = nx.closeness_centrality(g)
    elif measure == "second order":
        cent = nx.second_order_centrality(g)
    cent_list = list(cent.items())  # convert to np array
    cent_arr = np.array(cent_list)
    # sort array of tuples by betweenness, from highest to lowest
    cent_idx = np.argsort(cent_arr, 0, descending=True)

    node_list = list(g.nodes())
    nodes_sorted = [node_list[i] for i in cent_idx[:, 1]]
    edge_list = list(g.edges())

    return nodes_sorted, edge_list


def _get_gcc(graph: nx.Graph, deactivated: list[int]) -> set[int]:
    """Get the greatest connected component after removing deactivated nodes."""
    remaining_graph = graph.copy()
    remaining_graph.remove_nodes_from(deactivated)
    components = list(nx.connected_components(remaining_graph))
    return max(components, key=len)


@shared_task(base=AnalysisTask)
def network_recovery(result_id):
    result = TaskResult.objects.get(id=result_id)
    failure_id = result.inputs.get("network_failure")
    failure = TaskResult.objects.get(id=failure_id)
    mode = result.inputs.get("recovery_mode")
    network_id = failure.inputs.get("network")
    network = Network.objects.get(id=network_id)

    # Run task
    result.name = f"{mode.title()} Recovery from Failure Result {failure.id}"
    result.save()

    result.write_status("Reading network failure state...")
    node_failures = failure.outputs.get("failures")
    frames = sorted(int(key) for key in node_failures)
    last_frame_failures = node_failures[str(frames[-1])]
    node_recoveries = last_frame_failures.copy()
    graph = get_network_graph(network)

    result.write_status("Sorting failed nodes according to recovery mode...")
    if mode == "random":
        random.shuffle(node_recoveries)
    else:
        nodes_sorted, _edge_list = sort_graph_centrality(graph, mode)
        node_recoveries.sort(key=nodes_sorted.index)

    recovery_timesteps = {
        i: [n for n in last_frame_failures if n not in node_recoveries[:i]]
        for i in range(len(node_recoveries) + 1)
    }

    result.write_status("Creating GCC chart...")
    timesteps = []
    n_deactivated_values = []
    gcc_values = []

    for i, nodes in enumerate(node_failures.values()):
        timesteps.append(i)
        n_deactivated_values.append(len(nodes))
        gcc_values.append(len(_get_gcc(graph, nodes)))
    for i, nodes in enumerate(recovery_timesteps.values()):
        timesteps.append(len(node_failures) + i)
        n_deactivated_values.append(len(nodes))
        gcc_values.append(len(_get_gcc(graph, nodes)))

    chart, _ = Chart.objects.get_or_create(
        name=f"Network GCC Changes for {mode.title()} Recovery After {failure.name}",
        description=(
            "Number of nodes in the network's greatest connected component "
            "over time during network outages and recoveries"
        ),
        project=result.project,
    )
    chart.metadata = {
        "source": "Generated by Network Recovery Analysis Task",
        "created": timezone.now().strftime("%d/%m/%Y %H:%M"),
        "node_failures": node_failures,
        "node_recoveries": recovery_timesteps,
    }
    chart.chart_data = {
        "labels": timesteps,
        "datasets": [
            {
                "data": n_deactivated_values,
                "label": "Deactivated Nodes",
                "borderColor": "#ff0000",
                "backgroundColor": "#ff0000",
            },
            {
                "data": gcc_values,
                "label": "Greatest Connected Component",
                "borderColor": "#0000ff",
                "backgroundColor": "#0000ff",
            },
        ],
    }
    chart.chart_options = {
        "chart_title": "Greatest Connected Component versus Deactivated Nodes Over Time",
        "x_title": "Timestep in Network Event",
        "y_title": "Number of nodes",
    }
    chart.save()

    # resiliency score equals area under gcc curve with outages
    # over area under gcc curve without outages
    resiliency = sum(gcc_values) / (network.nodes.count() * len(gcc_values))

    result.write_outputs(
        {
            "recoveries": recovery_timesteps,
            "gcc_chart": chart.id,
            "resiliency_score": resiliency,
        }
    )
