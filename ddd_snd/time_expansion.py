from dataclasses import dataclass, field, InitVar
import rustworkx as rx
from .instance import ArcData, Commodity, NodeData
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
    flat_node: int
    time: int
    name: str = field(init=False)
    flat_node_data: InitVar[NodeData]  # only used to initialize this dataclass

    def __post_init__(self, flat_node_data: NodeData):
        self.name = f"{flat_node_data.name}_{self.time}"


class DiscretizedGraph(rx.PyDiGraph):
    # for some god-forsaken reason using the rustworkx interface we can not easily inherit from the PyDiGraph class
    # instead we could use composition or use this workaround using __new__ instead of __init__, see here
    # https://stackoverflow.com/questions/78593608/subclass-super-init-args-kwargs-not-working-says-object-init-t
    def __new__(
        cls, graph: rx.PyDiGraph, node_to_times: list[list[int]], relaxed: bool
    ):
        new_graph = rx.PyDiGraph.__new__(cls)
        new_graph.node_to_times = node_to_times
        new_graph.flat_to_expanded_nodes = {}
        new_graph.flat_to_expanded_arcs = {}
        new_graph.g_flat = graph
        new_graph.relaxed = relaxed
        new_graph._create_time_expanded_graph()
        return new_graph

    # workaround to get IDs of ingoing and outgoing edges, not something that PyDiGraph provides
    def get_out_edge_indices(self, node: int):
        return self.incident_edges(node)

    def get_in_edge_indices(self, node: int):
        all_incident_edges = self.incident_edges(node, all_edges=True)
        return [edge for edge in all_incident_edges if self.get_edge_endpoints_by_index(edge)[1] == node]

    def _add_timed_nodes(self):
        # add node for each timepoint
        for node in self.g_flat.node_indices():
            self.flat_to_expanded_nodes[node] = []
            for time in self.node_to_times[node]:
                id_ex = self.add_node(
                    TimeNodeData(
                        flat_node=node, time=time, flat_node_data=self.g_flat[node]
                    )
                )
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
                        # in this case, we might outside the time horizon, in which case we do not add the arc
                        if end_node_index + offset >= len(potential_end_nodes):
                            continue

                # add arc between start and end node
                end_node = potential_end_nodes[end_node_index + offset]

                arc_ex = self.add_edge(start_node, end_node, arc_data)
                self.flat_to_expanded_arcs[arc].append(arc_ex)

    def _create_time_expanded_graph(self):
        self._add_timed_nodes()
        self._add_holding_arcs()
        self._add_travel_arcs()

    def _shorten_travel_arcs_unrelaxed(self, new_node: int, next_node: int, time: int):
        # shorten ingoing travel arcs of after node
        ingoing_arcs = self.in_edges(
            next_node
        )  # returns tuples of form (predecessor_index, node_index, data)
        # if this arc arrives between the time of the new and the after node, we can delete it and replace it by an arc to the new node
        for i, j, data in ingoing_arcs:
            # skip holding arcs
            if self[i].flat_node == self[j].flat_node:
                continue
            arrival_time = self[i].time + data.travel_time
            after_time = self[next_node].time
            if arrival_time < after_time and arrival_time >= time:
                flat_arc = get_edge_index(self.g_flat, self[i].flat_node, self[j].flat_node)
                # remove old edge
                arc_to_remove = get_edge_index(self, i, j)
                self.remove_edge_from_index(arc_to_remove)  # from graph
                self.flat_to_expanded_arcs[flat_arc].remove(arc_to_remove)  # from mapping

                # add new edge
                new_arc = self.add_edge(i, new_node, data)  # to graph
                self.flat_to_expanded_arcs[flat_arc].append(new_arc)  # to mapping

    def _refine_holding_arc(self, new_node: int, previous_node: int, next_node: int | None):
        # add new holding arc to new node
        self.add_edge(previous_node, new_node, ArcData(0, 0, 0, None))
        # if next node exists, move holding arc
        if next_node is not None:
            # remove old holding arc
            holding_arc = get_edge_index(self, previous_node, next_node)
            self.remove_edge_from_index(holding_arc)
            self.add_edge(new_node, next_node, ArcData(0, 0, 0, None))

    def _add_travel_arcs_new_node(self, new_node: int):
        # get arcs outgoing from the corresponding flat node
        flat_node = self[new_node].flat_node
        outgoing_arcs = self.g_flat.out_edges(flat_node)
        for i, j, data in outgoing_arcs:
            arrival_time = self[new_node].time + data.travel_time
            # find first expanded node for flat node j that has a time no earlier than the arrival time
            k_j = bisect_left(self.node_to_times[j], arrival_time)
            no_larger_node = k_j == len(self.node_to_times[j])

            j_ex = None
            if self.relaxed:
                # if there is no larger or equal node, we need to use the last node
                if no_larger_node:
                    j_ex = self.flat_to_expanded_nodes[j][-1]
                # if there is a larger or equal node, check
                # if we hit exactly, use this node, if not, use the previous one
                else: 
                    j_ex = self.flat_to_expanded_nodes[j][k_j]
                    if self[j_ex].time != arrival_time:
                        j_ex = self.flat_to_expanded_nodes[j][k_j - 1]
            else:
                if no_larger_node:
                    continue # we do not add arcs to nodes that are outside the time horizon
                j_ex = self.flat_to_expanded_nodes[j][k_j]

            # add new travel arc
            new_arc = self.add_edge(new_node, j_ex, data)  # to graph
            flat_arc = get_edge_index(self.g_flat, flat_node, j)
            self.flat_to_expanded_arcs[flat_arc].append(new_arc)  # to mapping

    def _lengthen_travel_arcs_relaxed(
        self, new_node: int, previous_node: int, time: int
    ):
        # find all arcs going into the previous node
        # if they arrive no earlier than the new node, we replace them by arcs to the new node
        ingoing_arcs = self.in_edges(previous_node)
        for i, j, data in ingoing_arcs:
            # skip holding arcs
            if self[i].flat_node == self[j].flat_node:
                continue
            arrival_time = self[i].time + data.travel_time
            if arrival_time >= time:
                flat_arc = get_edge_index(self.g_flat, self[i].flat_node, self[j].flat_node)
                # remove old edge
                arc_to_remove = get_edge_index(self, i, previous_node)
                self.flat_to_expanded_arcs[flat_arc].remove(
                    arc_to_remove
                )  # from mapping
                self.remove_edge_from_index(arc_to_remove)  # from graph
                # add new edge
                new_arc = self.add_edge(i, new_node, data)  # to graph
                self.flat_to_expanded_arcs[flat_arc].append(new_arc)  # to mapping

    def refine_discretization(self, flat_node: int, time: int):
        # determine insertion point of new time point
        k_new = bisect_left(self.node_to_times[flat_node], time)
        k_previous = k_new - 1  # index of the time point before the new one
        k_next = k_new + 1  # index of the time point after the new one after insertion

        # determine previous and next node
        previous_node = self.flat_to_expanded_nodes[flat_node][k_previous]
        # next node after insertion still has k_new as index since new node has not been added yet
        # it can also be that the new node we add is later than the last time point, in which case next_node is None
        next_node = self.flat_to_expanded_nodes[flat_node][
            k_new
        ] if k_new < len(self.node_to_times[flat_node]) else None

        # insert time point into list of time points for node
        self.node_to_times[flat_node].insert(k_new, time)

        # update the graph
        # add new node
        new_node = self.add_node(
            TimeNodeData(
                flat_node=flat_node, time=time, flat_node_data=self.g_flat[flat_node]
            )
        )  # to graph
        self.flat_to_expanded_nodes[flat_node].insert(k_new, new_node)  # to mapping
        # update arcs
        self._refine_holding_arc(new_node, previous_node, next_node)
        self._add_travel_arcs_new_node(new_node)
        if self.relaxed:
            self._lengthen_travel_arcs_relaxed(new_node, previous_node, time)
        else:
            if next_node is not None:
                self._shorten_travel_arcs_unrelaxed(new_node, next_node, time)


def create_regular_discretization(
    n_nodes: int, last_time: int, delta_t: int
) -> list[list[int]]:
    node_to_times = [
        [n * delta_t for n in range(last_time // delta_t + 1)] for _ in range(n_nodes)
    ]
    return node_to_times


def create_relaxed_initial_discretization(
    n_nodes: int, coms: list[Commodity]
) -> list[list[int]]:
    node_times = {n: {0} for n in range(n_nodes)}
    for com in coms:
        node_times[com.source_node].add(com.release)
        node_times[com.sink_node].add(com.deadline)
    node_to_times = [sorted(list(node_times[n])) for n in range(n_nodes)]
    return node_to_times
