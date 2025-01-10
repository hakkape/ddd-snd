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
        for k in range(len(com_node_paths[com.id]) - 1):
            dispatch[com.id, k] = m.addVar(
                vtype=GRB.CONTINUOUS, name=f"gamma_{com.id}_{k}_n{com_node_paths[com.id][k]}"
            )
    return dispatch


def add_duration_variables(
    m: Model, sol: Solution, coms: list[Commodity], com_node_paths: list[list[int]]
) -> dict[tuple[int, int], Var]:
    # variables that track the time that each commodity travels between each pair of nodes (theta in Boland et al., here we identify the arcs by their origin node since the destination is clear)
    duration = {}
    for com in coms:
        for k, node in enumerate(com_node_paths[com.id][:-1]):
            relaxed_travel_time = (
                sol.commodity_paths[com.id].services[k].end_time
                - sol.commodity_paths[com.id].services[k].start_time
            )
            duration[com.id, k] = m.addVar(
                vtype=GRB.CONTINUOUS,
                name=f"theta_{com.id}_{k}_n{node}",
                lb=relaxed_travel_time,
            )

    return duration


def add_shorten_variables(
    m: Model, sol: Solution, coms: list[Commodity], com_node_paths: list[list[int]]
) -> dict[tuple[int, int], Var]:
    # binary variables to track if a service needs to be shortened (sigma in Boland et al., here we identify the arcs by their origin node since the destination is clear)
    shorten = {}
    for com in coms:
        for k, node in enumerate(com_node_paths[com.id][:-1]):
            shorten[com.id, k] = m.addVar(
                vtype=GRB.BINARY, name=f"sigma_{com.id}_{k}_n{node}", obj=1
            )
    return shorten


def get_commodity_node_paths(sol: Solution, coms: list[Commodity]) -> list[list[int]]:
    commodity_node_paths = []
    for com in coms:
        visited_nodes = [
            service.start_node for service in sol.commodity_paths[com.id].services
        ]
        visited_nodes.append(com.sink_node)
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
        for k, node in enumerate(com_node_paths[com.id][:-1]):
            real_travel_time = sol.commodity_paths[com.id].services[k].travel_time
            lb = duration[com.id, k].lb
            m.addConstr(
                duration[com.id, k]
                >= real_travel_time - (real_travel_time - lb) * shorten[com.id, k],
                name=f"link_{com.id}_{k}_n{node}",
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
        for k, node in enumerate(com_node_paths[com.id][:-2]):
            m.addConstr(
                dispatch[com.id, k] + duration[com.id, k]
                <= dispatch[com.id, k + 1],
                name=f"time_consistency_{com.id}_{k}_n{node}",
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
        m.addConstr(
            dispatch[com.id, 0] >= com.release, name=f"release_{com.id}"
        )
        second_to_last_k = len(com_node_paths[com.id]) - 2
        m.addConstr(
            dispatch[com.id, second_to_last_k]
            + duration[com.id, second_to_last_k]
            <= com.deadline,
            name=f"deadline_{com.id}",
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
            k1 = sol.commodity_paths[com1.id].services.index(service)
            for com2 in service.commodities_transported:
                k2 = sol.commodity_paths[com2.id].services.index(service)
                if com1.id < com2.id:
                    m.addConstr(
                        dispatch[com1.id, k1] == dispatch[com2.id, k2],
                        name=f"dispatch_link_{com1.id}_{com2.id}_{node}",
                    )


def setup_identification_model(sol: Solution, instance: Instance):
    m = Model("Identxification")
    com_node_paths = get_commodity_node_paths(sol, instance.commodities)

    # variables
    dispatch = add_dispatch_variables(m, sol, instance.commodities, com_node_paths)
    duration = add_duration_variables(m, sol, instance.commodities, com_node_paths)
    shorten = add_shorten_variables(m, sol, instance.commodities, com_node_paths)
    m.update()  # necessary because we access the variables lower bounds before the model gets updated (when solving)

    # constraints
    add_linking_constraints(
        m, sol, duration, shorten, com_node_paths, instance.commodities
    )
    add_time_consistency_constraints(
        m, sol, dispatch, duration, com_node_paths, instance.commodities
    )
    add_time_window_constraints(
        m, sol, dispatch, duration, instance.commodities, com_node_paths
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
        k = sol.commodity_paths[com.id].services.index(service)
        service.start_time = dispatch[com.id, k].x
        service.end_time = service.start_time + service.travel_time


def find_nodes_to_insert(
    sol: Solution, shorten: dict[tuple[int, int], Var]
) -> list[tuple[int, int]]:
    # if we have an arc ((i,t),(j,t')) that is too short, we need to add a new node (j, t+t_{ij})
    # set, in case we have multiple arcs that would result in the same split
    nodes_to_insert = set()

    for (com_id, k), var in shorten.items():
        if var.x > 0.5:
            service = sol.commodity_paths[com_id].services[k]
            node = service.end_node
            time = service.start_time + service.travel_time
            nodes_to_insert.add((node, time))

    return list(nodes_to_insert)
