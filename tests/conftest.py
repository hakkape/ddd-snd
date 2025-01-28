from ddd_snd.instance import Instance, Commodity, ArcData, NodeData
from ddd_snd.snd.time_expansion import DiscretizedGraph
import rustworkx as rx
from pathlib import Path
import pytest


@pytest.fixture
def TEST_DATA_DIR():
    return (Path(__file__).parent / "data").resolve()


@pytest.fixture
def tiny_instance_dow_file(TEST_DATA_DIR):
    return TEST_DATA_DIR / "tiny_instance.dow"


@pytest.fixture
def tiny_instance() -> Instance:
    com1 = Commodity(
        id=0, source_node=0, sink_node=2, quantity=1, release=0, deadline=3
    )
    com2 = Commodity(
        id=1, source_node=1, sink_node=2, quantity=1, release=1, deadline=2
    )
    com3 = Commodity(
        id=2, source_node=0, sink_node=1, quantity=1, release=1, deadline=2
    )
    flat_graph = rx.PyDiGraph()
    flat_graph.add_node(NodeData(name=1))
    flat_graph.add_node(NodeData(name=2))
    flat_graph.add_node(NodeData(name=3))
    flat_graph.add_edge(
        0, 1, ArcData(travel_time=1, flow_cost=1, fixed_cost=1, capacity=2)
    )
    flat_graph.add_edge(
        1, 2, ArcData(travel_time=1, flow_cost=1, fixed_cost=1, capacity=2)
    )
    flat_graph.add_edge(
        0, 2, ArcData(travel_time=1, flow_cost=2, fixed_cost=2, capacity=2)
    )
    return Instance(flat_graph, [com1, com2, com3])


@pytest.fixture
def tiny_full_discretization() -> list[list[int]]:
    return [[0, 1, 2, 3], [0, 1, 2, 3], [0, 1, 2, 3]]


@pytest.fixture
def tiny_initial_relaxed_discretization() -> list[list[int]]:
    return [[0, 1], [0, 1, 2], [0, 2, 3]]


@pytest.fixture
def tiny_fully_discretized_graph() -> DiscretizedGraph:
    g = DiscretizedGraph()
    return g


@pytest.fixture
def tiny_initial_relaxed_discretized_graph() -> DiscretizedGraph:
    g = DiscretizedGraph()
    return g
