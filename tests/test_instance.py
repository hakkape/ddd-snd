from ddd_snd.instance import Instance, read_modified_dow_instance
import pytest
import rustworkx as rx


def compare_flat_graphs(g1: rx.PyDiGraph, g2: rx.PyDiGraph):
    assert g1.num_nodes() == g2.num_nodes()
    assert g1.num_edges() == g2.num_edges()
    # nodes and arcs need to have same data
    for n in range(g1.num_nodes()):
        assert g1[n] == g2[n]
    for n in range(g1.num_edges()):
        assert g1.get_edge_data_by_index(n) == g2.get_edge_data_by_index(n)


def test_instance_reading(tiny_instance_dow_file, tiny_instance):
    instance = read_modified_dow_instance(tiny_instance_dow_file, 1)
    compare_flat_graphs(instance.flat_graph, tiny_instance.flat_graph)
    assert len(instance.commodities) == len(tiny_instance.commodities)
    for i in range(len(instance.commodities)):
        assert instance.commodities[i] == tiny_instance.commodities[i]
        

    
