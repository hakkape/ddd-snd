import rustworkx as rx
from dataclasses import dataclass
from pathlib import Path
from math import ceil, floor


@dataclass
class NodeData:
    name: str


@dataclass
class ArcData:
    travel_time: int
    flow_cost: float  # flow cost per unit of flow
    fixed_cost: float  # fixed cost per multiple of capacity
    capacity: float | None


@dataclass
class Commodity:
    id: int
    source_node: int
    sink_node: int
    quantity: float
    release: int
    deadline: int


@dataclass
class Instance:
    flat_graph: rx.PyDiGraph
    commodities: list[Commodity]
    


def read_modified_dow_instance(path: Path, delta_t: float) -> Instance:
    # instances in dow format with additional travel times and commodity release and deadline times
    # all times get converted to integers (multiples of delta_t)
    with open(path, "r") as f:
        lines = f.readlines()
    n_nodes, n_arcs, n_commodities = map(int, lines[1].split())
    flat_graph = rx.PyDiGraph()
    for i in range(1, n_nodes+1):
        flat_graph.add_node(NodeData(name = i))
    for i, line in enumerate(lines[2 : n_arcs + 2]):
        i, j, flow_cost, capacity, fixed_cost, travel_time = map(float, line.split()[:6])
        travel_time = ceil(travel_time / delta_t)
        flat_graph.add_edge(int(i) - 1, int(j) - 1, ArcData(travel_time, flow_cost, fixed_cost, capacity))
    commodities = []
    for line in lines[n_arcs + 2 :]:
        source_node, sink_node, quantity, release, deadline = line.split()[:5]
        source_node = int(source_node) - 1
        sink_node = int(sink_node) - 1
        quantity = float(quantity)
        release = ceil(float(release) / delta_t)
        deadline = floor(float(deadline) / delta_t)
        commodities.append(Commodity(len(commodities), source_node, sink_node, quantity, release, deadline))
    return Instance(flat_graph, commodities)
