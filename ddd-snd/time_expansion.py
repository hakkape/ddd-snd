from dataclasses import dataclass, field
import rustworkx as rx
from .instance import *
from bisect import bisect_left


def get_edge_index(graph, i, j):
    edge_indices = graph.edge_indices_from_endpoints(i, j)
    assert (
        len(edge_indices) == 1
    ), "There should be exactly one edge between two nodes, found: " + str(
        len(edge_indices)
    )
    return edge_indices[0]


@dataclass
class TimeNodeData:
    id: int
    flat_id: int
    time: int


class DiscretizedGraph(rx.PyDiGraph):
    def __init__(
        self, graph: rx.PyDiGraph, node_to_times: list[list[int]], relaxed: bool
    ):
        super().__init__()
        self.node_to_times: list[list[int]] = node_to_times
        self.flat_to_expanded_nodes: dict[int, list[int]] = {}
        self.flat_to_expanded_arcs: dict[int, list[int]] = {}
        self.g_flat: rx.PyDiGraph = graph
        self.relaxed = relaxed
        if self.relaxed:
            self._create_relaxed_time_expanded_graph()
        else:
            self._create_time_expanded_graph()

    def _add_timed_nodes(self):
        # add node for each timepoint
        for node in self.g_flat.node_indices():
            self.flat_to_expanded_nodes[node] = []
            for time in self.node_to_times[node]:
                id_ex = self.add_node(
                    TimeNodeData(id=0, flat_id=self.g_flat[node].id, time=time)
                )
                self[id_ex].id = id_ex
                self.flat_to_expanded_nodes[node].append(id_ex)

    def _add_holding_arcs(self):
        # add holding arcs
        holding_arc_data = ArcData(
            travel_time=0, flow_cost=0, fixed_cost=0, capacity=None
        )
        for node in self.g_flat.node_indices():
            expanded_nodes = self.flat_to_expanded_nodes[node]
            holding_arcs = zip(expanded_nodes[:-1], expanded_nodes[1:])
            self.add_edges_from(
                [
                    (
                        i,
                        j,
                        holding_arc_data,
                    )
                    for i, j in holding_arcs
                ]
            )

    # add arcs between nodes
    def _add_travel_arcs(self):
        for arc in self.g_flat.edge_indices():
            self.flat_to_expanded_arcs[arc] = []
            arc_data = self.g_flat.get_edge_data_by_index(arc)
            travel_time = arc_data.travel_time
            i, j = self.g_flat.get_edge_endpoints_by_index(arc)
            potential_start_nodes = self.flat_to_expanded_nodes[i]
            potential_end_nodes = self.flat_to_expanded_nodes[j]
            end_node_index = 0
            # from every start node, connect to last possible end node
            for start_node in potential_start_nodes:
                start_time = self[start_node].time
                # find latest node whose time is not higher than the arrival time
                while (
                    end_node_index + 1 < len(potential_end_nodes)
                    and self[potential_end_nodes[end_node_index + 1]].time
                    <= start_time + travel_time
                ):
                    end_node_index += 1

                offset = 0
                # if not relaxed, we need to check if we need to round up to the next node
                if not self.relaxed:
                    if (
                        self[potential_end_nodes[end_node_index]].time
                        != start_time + travel_time
                    ):
                        offset = 1

                # add arc between start and end node
                end_node = potential_end_nodes[end_node_index + offset]

                arc_ex = self.add_edge(start_node, end_node, arc_data)
                self.flat_to_expanded_arcs[arc].append(arc_ex)

    def _create_time_expanded_graph(self):
        self._add_timed_nodes()
        self._add_holding_arcs()
        self._add_relaxed_travel_arcs()

    def _shorten_travel_arcs_unrelaxed(self, new_node: int, next_node: int, time: int):
        # shorten ingoing travel arcs of after node
        ingoing_arcs = self.in_edges(
            next_node
        )  # returns tuples of form (predecessor_index, node_index, data)
        # if this arc arrives between the time of the new and the after node, we can delete it and replace it by an arc to the new node
        for i, j, data in ingoing_arcs:
            # skip holding arcs
            if self[i].flat_id == self[j].flat_id:
                continue
            arrival_time = self[i].time + data.travel_time
            after_time = self[next_node].time
            if arrival_time < after_time and arrival_time >= time:
                # remove old edge
                edge_to_remove = get_edge_index(self, i, j)
                self.remove_edge(edge_to_remove)  # from graph
                self.flat_to_expanded_arcs[j].remove(edge_to_remove)  # from mapping

                # add new edge
                new_edge = self.add_edge(i, new_node, data)  # to graph
                self.flat_to_expanded_arcs[j].append(new_edge)  # to mapping

    def _refine_holding_arc(self, new_node: int, previous_node: int, next_node: int):
        # remove old holding arc
        holding_arc = get_edge_index(self, previous_node, next_node)
        self.remove_edge(holding_arc)

        # add new holding arcs
        self.add_edge(previous_node, new_node, ArcData(0, 0, 0, None))
        self.add_edge(new_node, next_node, ArcData(0, 0, 0, None))

    def _add_travel_arcs_new_node(self, new_node: int):
        # get arcs outgoing from the corresponding flat node
        flat_node = self[new_node].flat_id
        outgoing_arcs = self.g_flat.out_edges(flat_node)
        for i, j, data in outgoing_arcs:
            arrival_time = self[new_node].time + data.travel_time
            # find first expanded node for flat node j that has a time no earlier than the arrival time
            k_j = bisect_left(self.node_to_times[j], arrival_time)
            j_ex = self.flat_to_expanded_nodes[j][k_j]            
            if self.relaxed:
                # if we hit exactly, use this node, if not, use the previous one
                if self[j_ex].time != arrival_time:
                    j_ex = self.flat_to_expanded_nodes[j][k_j - 1]
            # add new travel arc
            self.add_edge(new_node, j_ex, data)  # to graph
            self.flat_to_expanded_arcs[i].append(j_ex)  # to mapping

    def _lengthen_travel_arcs_relaxed(
        self, new_node: int, previous_node: int, time: int
    ):
        # find all arcs going into the previous node
        # if they arrive no earlier than the new node, we replace them by arcs to the new node
        ingoing_arcs = self.in_edges(previous_node)
        for i, j, data in ingoing_arcs:
            # skip holding arcs
            if self[i].flat_id == self[j].flat_id:
                continue
            arrival_time = self[i].time + data.travel_time
            if arrival_time >= time:
                # remove old edge
                edge_to_remove = get_edge_index(self, i, previous_node)
                self.remove_edge(edge_to_remove)  # from graph
                self.flat_to_expanded_arcs[previous_node].remove(
                    edge_to_remove
                )  # from mapping
                # add new edge
                new_edge = self.add_edge(i, new_node, data)  # to graph
                self.flat_to_expanded_arcs[previous_node].append(new_edge)  # to mapping

    def refine_discretization(self, flat_node: int, time: int):
        # determine insertion point of new time point
        k_new = bisect_left(self.node_to_times[flat_node], time)
        k_previous = k_new - 1  # index of the time point before the new one
        k_next = k_new + 1  # index of the time point after the new one after insertion

        # determine previous and next node
        previous_node = self.flat_to_expanded_nodes[flat_node][k_previous]
        next_node = self.flat_to_expanded_nodes[flat_node][
            k_new
        ]  # next node after insertion still has k_new as index since new node has not been added yet

        # insert time point into list of time points for node
        self.node_to_times[flat_node].insert(k_new, time)

        # update the graph
        # add new node
        new_node = self.add_node(
            TimeNodeData(id=0, flat_id=flat_node, time=time)
        )  # to graph
        self.flat_to_expanded_nodes[flat_node].insert(k_new, new_node)  # to mapping
        # update arcs
        self._refine_holding_arc(new_node, previous_node, next_node)
        self._add_travel_arcs_new_node(new_node)
        if self.relaxed:
            self._lengthen_travel_arcs_relaxed(new_node, previous_node, time)
        else:
            self._shorten_travel_arcs_unrelaxed(new_node, next_node, time)


def create_regular_discretization(n_nodes: int, last_time: int, delta_t: int):
    node_to_times = [
        [n * delta_t for n in range(last_time // delta_t + 1)] for _ in range(n_nodes)
    ]
    return node_to_times


def create_relaxed_initial_discretization(n_nodes: int, last_time: int):
    node_to_times = [[0, last_time] for _ in range(n_nodes)]
    return node_to_times
