from .solution import Solution, TimedService, CommodityPath
from .instance import Commodity, Instance
from gurobipy import Model, GRB, quicksum, Var


def add_dispatch_variables(
    m: Model, sol: Solution, coms: list[Commodity], com_node_paths: list[list[int]]
) -> dict[tuple[int, int], Var]:
    # variables that track the dispatch time of each commodity at each node that it visits (gamma in Boland et al.)
    dispatch = {}
    for com in coms:
        # we skip the last node, since we do not need to dispatch there
        for node in com_node_paths[com.id][:-1]:
            dispatch[com.idx, node] = m.addVar(
                vtype=GRB.CONTINUOUS, name=f"gamma_{com}_{node}"
            )
    return dispatch


def add_duration_variables(
    m: Model, sol: Solution, coms: list[Commodity], com_node_paths: list[list[int]]
) -> dict[tuple[int, int], Var]:
    # variables that track the time that each commodity travels between each pair of nodes (theta in Boland et al., here we identify the arcs by their origin node since the destination is clear)
    duration = {}
    for com in coms:
        for n_arc, node in enumerate(com_node_paths[com.id][:-1]):
            relaxed_travel_time = (
                sol.commodity_paths[com.id].services[n_arc].end_time
                - sol.commodity_paths[com.id].services[n_arc].start_time
            )
            duration[com.idx, node] = m.addVar(
                vtype=GRB.CONTINUOUS, name=f"theta_{com}_{node}", lb=relaxed_travel_time
            )

    return duration


def add_shorten_variables(
    m: Model, sol: Solution, coms: list[Commodity], com_node_paths: list[list[int]]
) -> dict[tuple[int, int], Var]:
    # binary variables to track if a service needs to be shortened (sigma in Boland et al., here we identify the arcs by their origin node since the destination is clear)
    shorten = {}
    for com in coms:
        for node in com_node_paths[com.id][:-1]:
            shorten[com.idx, node] = m.addVar(
                vtype=GRB.BINARY, name=f"sigma_{com}_{node}", obj=1
            )


def get_commodity_node_paths(sol: Solution, coms: list[Commodity]) -> list[list[int]]:
    commodity_node_paths = []
    for com in coms:
        visited_nodes = [
            service.start_node for service in sol.commodity_paths[com.id].services
        ]
        visited_nodes.add(com.sink_node)
        commodity_node_paths.append(list(visited_nodes))

    return commodity_node_paths


def add_linking_constraints(
    m: Model,
    sol: Solution,
    duration: dict[tuple[int, int], Var],
    shorten: dict[tuple[int, int], Var],
    com_node_paths: list[list[int]],
    coms: list[Commodity],
):
    # (6) in Boland et al.
    for com in coms:
        for n_arc, node in enumerate(com_node_paths[com.id][:-1]):
            real_travel_time = sol.commodity_paths[com.id].services[n_arc].travel_time
            m.addConstr(
                duration[com.idx, node] >= real_travel_time(1 - shorten[com.idx, node])
            )


def add_time_consistency_constraints(
    m: Model,
    sol: Solution,
    dispatch: dict[tuple[int, int], Var],
    duration: dict[tuple[int, int], Var],
    com_node_paths: list[list[int]],
    coms: list[Commodity],
):
    # (7) in Boland et al.
    for com in coms:
        for n_arc, node in enumerate(com_node_paths[com.id][:-1]):
            m.addConstr(
                dispatch[com.idx, node] + duration[com.idx, node]
                <= dispatch[com.idx, com_node_paths[com.id][n_arc + 1]]
            )


def add_time_window_constraints(
    m: Model,
    sol: Solution,
    dispatch: dict[tuple[int, int], Var],
    duration: dict[tuple[int, int], Var],
    coms: list[Commodity],
    com_node_paths: list[list[int]],
):
    # (8, 9) in Boland et al.
    for com in coms:
        m.addConstr(dispatch[com.idx, com.source_node] >= com.release)
        second_to_last_node = com_node_paths[com.id][-2]
        m.addConstr(
            dispatch[com.idx, second_to_last_node]
            + duration[com.idx, second_to_last_node]
            <= com.deadline
        )


def add_dispatch_linking_constraints(
    m: Model,
    dispatch: dict[tuple[int, int], Var],
    com_node_paths: list[list[int]],
    sol: Solution,
    coms: list[Commodity],
):
    # (10) in Boland et al.
    # TODO: since we link all of these variables, we might as well directly replace them with a variable for service dispatch times
    for service in sol.services:
        node = service.start_node
        if len(service.commodities_transported) < 2:
            continue
        for com1 in service.commodities_transported:
            for com2 in service.commodities_transported:
                if com1.id < com2.id:
                    m.addConstr(dispatch[com1.idx, node] == dispatch[com2.idx, node])


def setup_identification_model(sol: Solution, instance: Instance):
    m = Model("Identxification")
    com_node_paths = get_commodity_node_paths(sol, instance.commodities)

    # variables
    dispatch = add_dispatch_variables(m, sol, instance.commodities, com_node_paths)
    duration = add_duration_variables(m, sol, instance.commodities, com_node_paths)
    shorten = add_shorten_variables(m, sol, instance.commodities, com_node_paths)

    # constraints
    add_linking_constraints(m, dispatch, duration, shorten, com_node_paths)
    add_time_consistency_constraints(m, dispatch, duration, com_node_paths)
    add_time_window_constraints(
        m, dispatch, duration, instance.commodities, com_node_paths
    )
    add_dispatch_linking_constraints(
        m, dispatch, com_node_paths, sol, instance.commodities
    )
    return m, dispatch, duration, shorten


def update_timed_services(sol: Solution, dispatch: dict[tuple[int, int], Var]):
    # given a solution that can be implemented, update the start and end times of the services
    for service in sol.services:
        # get any commodity on that service and get its dispatch time: this is the start time
        # arrival time is then start time + travel time
        com = service.commodities_transported[0]
        start_node = service.start_node
        service.start_time = dispatch[com.idx, start_node].x
        service.end_time = service.start_time + service.travel_time


def find_nodes_to_insert(sol: Solution, shorten: dict[tuple[int, int], Var]) -> list[tuple[int, int]]:
    # if we have an arc ((i,t),(j,t')) that is too short, we need to add a new node (j, t+t_{ij})
    # set, in case we have multiple arcs that would result in the same split
    nodes_to_insert = set()
    
    for (com, node), var in shorten.items():
        if var.x > 0.5:
            # find service that starts at this node
            for service in sol.commodity_paths[com.id].services:
                found = False
                if service.start_node == node:
                    # add new node to set
                    nodes_to_insert.add((service.end_node, service.start_time + service.travel_time))
                    found = True
                    break
                assert(found, "Can not identify service that needs to be split")

    return list(nodes_to_insert)
