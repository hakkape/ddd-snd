import rustworkx as rx
from dataclasses import dataclass


@dataclass
class NodeData:
    id: int


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
