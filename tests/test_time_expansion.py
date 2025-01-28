from ddd_snd.snd.time_expansion import (
    create_regular_discretization,
    create_relaxed_initial_discretization,
    get_edge_index,
    DiscretizedGraph,
)
import pytest
import rustworkx as rx


def test_create_regular_discretization(tiny_full_discretization):
    disc = create_regular_discretization(3, 3, 1)
    assert disc == tiny_full_discretization


def test_create_relaxaxed_discretization(
    tiny_instance, tiny_initial_relaxed_discretization
):
    disc = create_relaxed_initial_discretization(
        tiny_instance.flat_graph.num_nodes(), tiny_instance.commodities
    )
    assert disc == tiny_initial_relaxed_discretization


def test_get_edge_index():
    g = rx.PyDiGraph()
    n1 = g.add_node(0)
    n2 = g.add_node(1)
    arc_1 = g.add_edge(n1, n2, None)
    arc_2 = g.add_edge(n2, n1, None)
    assert arc_1 != arc_2
    assert get_edge_index(g, n1, n2) == arc_1
    assert get_edge_index(g, n2, n1) == arc_2


def test_fully_discretized_graph(tiny_instance, tiny_full_discretization):
    g = DiscretizedGraph(tiny_instance.flat_graph, tiny_full_discretization, False)
    # Check that the graph has the correct nodes
    assert g.num_nodes() == 12
    # Each flat node once for each time step, ordered correctly
    for flat_node in range(3):
        for time in range(4):
            n = g.flat_to_expanded_nodes[flat_node][time]
            assert g[n].flat_node == flat_node
            assert g[n].time == time
    # Check that the graph has the correct arcs
    n_holdings_arcs = 9
    n_transport_arcs = 9
    assert g.num_edges() == n_holdings_arcs + n_transport_arcs
    flat_arcs = [(0, 0, 1), (1, 1, 2), (2, 0, 2)]
    for flat_arc_id, i_flat, j_flat in flat_arcs:
        for time in range(3):
            arc = g.flat_to_expanded_arcs[flat_arc_id][time]
            i, j = g.get_edge_endpoints_by_index(arc)
            assert g[i].flat_node == i_flat
            assert g[j].flat_node == j_flat
            assert g[i].time == time
            assert (
                g[j].time == time + 1
            )  # all arcs have a travel time of 1 in this instance
    for flat_node in range(3):
        for time in range(3):
            i = g.flat_to_expanded_nodes[flat_node][time]
            j = g.flat_to_expanded_nodes[flat_node][time + 1]
            assert len(g.edge_indices_from_endpoints(i, j)) == 1
            holding_arc = get_edge_index(g, i, j)
            arc_data = g.get_edge_data_by_index(holding_arc)
            assert arc_data.travel_time == 0
            assert arc_data.flow_cost == 0
            assert arc_data.fixed_cost == 0
            assert arc_data.capacity == None


def test_initial_relaxed_discretized_graph(
    tiny_instance, tiny_initial_relaxed_discretization
):
    g = DiscretizedGraph(
        tiny_instance.flat_graph, tiny_initial_relaxed_discretization, True
    )
    # Check that the graph has the correct nodes
    nodes_expanded = [  # (flat_node, time)
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
        (1, 2),
        (2, 0),
        (2, 2),
        (2, 3),
    ]
    assert g.num_nodes() == len(nodes_expanded)
    for node in g.node_indices():
        assert (g[node].flat_node, g[node].time) in nodes_expanded

    # Check that the graph has the correct arcs
    arcs_expanded = [
        ((0, 0), (1, 1)),  # transport arcs
        ((0, 1), (1, 2)),
        ((1, 0), (2, 0)),
        ((1, 1), (2, 2)),
        ((1, 2), (2, 3)),
        ((0, 0), (2, 0)),
        ((0, 1), (2, 2)),
        ((0, 0), (0, 1)),  # holding arcs
        ((1, 0), (1, 1)),
        ((1, 1), (1, 2)),
        ((2, 0), (2, 2)),
        ((2, 2), (2, 3)),
    ]
    assert g.num_edges() == len(arcs_expanded)
    for arc in g.edge_indices():
        i, j = g.get_edge_endpoints_by_index(arc)
        data = g.get_edge_data_by_index(arc)
        assert (
            (g[i].flat_node, g[i].time),
            (g[j].flat_node, g[j].time),
        ) in arcs_expanded
        if g[i].flat_node == g[j].flat_node:
            assert data.travel_time == 0
            assert data.flow_cost == 0
            assert data.fixed_cost == 0
            assert data.capacity == None
        else:
            assert data.travel_time == 1
            assert data.flow_cost == g[j].flat_node - g[i].flat_node
            assert data.fixed_cost == g[j].flat_node - g[i].flat_node
            assert data.capacity == 2


def test_refining_relaxed_discretization(
    tiny_instance, tiny_initial_relaxed_discretization
):
    g = DiscretizedGraph(
        tiny_instance.flat_graph, tiny_initial_relaxed_discretization, True
    )
    old_n_nodes = g.num_nodes()
    old_n_arcs = g.num_edges()
    last_node = g.node_indices()[-1]
    g.refine_discretization(2, 1)
    # need to have one additional node
    new_node = g.node_indices()[-1]
    assert g.num_nodes() == old_n_nodes + 1
    assert g[new_node].flat_node == 2
    assert g[new_node].time == 1
    # 1. two ingoing travel arcs are replaced
    # 2. one holding arc is replaced by two
    # 3. no other arcs are added (since flat node has no outgoing arcs)
    assert g.num_edges() == old_n_arcs + 1
    # check arcs removed
    arcs_removed = [((0, 0), (2, 0)), ((0, 0), (2, 0)), ((2, 0), (2, 2))]
    for i in range(len(arcs_removed)):
        i_flat = arcs_removed[i][0][0]
        i_time = arcs_removed[i][0][1]
        j_flat = arcs_removed[i][1][0]
        j_time = arcs_removed[i][1][1]
        i = g.flat_to_expanded_nodes[i_flat][i_time]
        j = g.flat_to_expanded_nodes[j_flat][j_time]
        arcs_removed_indices = g.edge_indices_from_endpoints(i, j)
        assert len(arcs_removed_indices) == 0
    # check arcs added
    arcs_added = [
        ((0, 0), (2, 1)),
        ((1, 0), (2, 1)),
        ((2, 0), (2, 1)),
        ((2, 1), (2, 2)),
    ]
    for i in range(len(arcs_added)):
        i_flat = arcs_added[i][0][0]
        i_time = arcs_added[i][0][1]
        j_flat = arcs_added[i][1][0]
        j_time = arcs_added[i][1][1]
        i = g.flat_to_expanded_nodes[i_flat][i_time]
        j = g.flat_to_expanded_nodes[j_flat][j_time]
        arcs_added_indices = g.edge_indices_from_endpoints(i, j)
        assert len(arcs_added_indices) == 1
        arc = arcs_added_indices[0]
        data = g.get_edge_data_by_index(arc)
        if i_flat == j_flat:
            assert data.travel_time == 0
            assert data.flow_cost == 0
            assert data.fixed_cost == 0
            assert data.capacity == None
        else:
            assert data.travel_time == 1
            assert data.flow_cost == j_flat - i_flat
            assert data.fixed_cost == j_flat - i_flat
            assert data.capacity == 2
