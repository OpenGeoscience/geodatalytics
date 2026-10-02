from __future__ import annotations

import random

from celery import shared_task
from django.conf import settings
from django.db.models import Count, Max
from django.utils import timezone
import networkx as nx
import numpy as np

from uvdat.core.models import (
    Chart,
    Network,
    NetworkAnimation,
    NetworkNode,
    NetworkState,
    TaskResult,
)

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
        self.input_defaults = {
            "recovery_mode": "betweenness",
        }
        self.output_types = {
            "animation": "network_animation",
            "results_chart": "Chart",
            "resiliency_score": "number",
        }
        self.attribution = "Jack Watson, Northeastern University"

    @classmethod
    def is_enabled(cls):
        return settings.UVDAT_ENABLE_NETWORK_RECOVERY

    def get_input_options(self):
        return {
            "network_failure": TaskResult.objects.filter(task_type="flood_network_failure"),
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


@shared_task(base=AnalysisTask)
def network_recovery(result_id):
    result = TaskResult.objects.get(id=result_id)
    failure_id = result.inputs.get("network_failure")
    failure = TaskResult.objects.get(id=failure_id)
    mode = result.inputs.get("recovery_mode")
    network_id = failure.inputs.get("network")
    network = Network.objects.get(id=network_id)
    network_graph = network.get_graph()

    # Run task
    result.name = f"{mode.title()} Recovery from Failure Result {failure.id}"
    result.save()

    result.write_status("Reading network failure state...")
    failure_animation_id = failure.outputs.get("animation")
    failure_animation = NetworkAnimation.objects.get(id=failure_animation_id)
    last_failure_state = failure_animation.states.all().order_by("-index").first()
    last_state_failures = [node.id for node in last_failure_state.deactivated_nodes.all()]
    node_recoveries = last_state_failures.copy()

    result.write_status("Sorting failed nodes according to recovery mode...")
    if mode == "random":
        random.shuffle(node_recoveries)
    else:
        nodes_sorted, _edge_list = sort_graph_centrality(network_graph, mode)
        node_recoveries.sort(key=nodes_sorted.index)

    n_existing_anims = NetworkAnimation.objects.filter(
        name__contains="Flood Recovery",
        network=network,
        project=result.project,
    ).count()
    recovery_animation = NetworkAnimation.objects.create(
        name=f"Flood Recovery {n_existing_anims + 1}",
        network=network,
        project=result.project,
        task_result=result,
    )

    for i in range(len(node_recoveries) + 1):
        deactivated = [n for n in last_state_failures if n not in node_recoveries[:i]]
        state = NetworkState.objects.create(animation=recovery_animation, index=i)
        state.deactivated_nodes.set(NetworkNode.objects.filter(id__in=deactivated))
        state.update_components()

    result.write_status("Creating Results chart...")
    timesteps = []
    n_deactivated_values = []
    gcc_values = []

    for state in failure_animation.states.all().order_by("index"):
        timesteps.append(state.index)
        n_deactivated_values.append(state.deactivated_nodes.count())
        gcc_values.append(
            state.components.annotate(component_size=Count("nodes"))
            .aggregate(gcc_size=Max("component_size", default=0))
            .get("gcc_size")
        )
    for state in recovery_animation.states.all().order_by("index"):
        timesteps.append(failure_animation.states.count() + state.index)
        n_deactivated_values.append(state.deactivated_nodes.count())
        gcc_values.append(
            state.components.annotate(component_size=Count("nodes"))
            .aggregate(gcc_size=Max("component_size", default=0))
            .get("gcc_size")
        )

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
            "animation": recovery_animation.id,
            "results_chart": chart.id,
            "resiliency_score": resiliency,
        }
    )
