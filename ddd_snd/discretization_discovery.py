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


def getCommodityNodePaths(sol: Solution, coms: list[Commodity]) -> list[list[int]]:
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
            
def add_time_consistency_constraints(m: Model, sol: Solution, dispatch: dict[tuple[int, int], Var], duration: dict[tuple[int, int], Var], com_node_paths: list[list[int]], coms: list[Commodity]):
    # (7) in Boland et al.
    for com in coms:
        for n_arc, node in enumerate(com_node_paths[com.id][:-1]):
            m.addConstr(
                dispatch[com.idx, node] + duration[com.idx, node] <= dispatch[com.idx, com_node_paths[com.id][n_arc + 1]]
            )
            
def add_time_window_constraints(m: Model, sol: Solution, dispatch: dict[tuple[int, int], Var], duration: dict[tuple[int,int],Var], coms: list[Commodity], com_node_paths: list[list[int]]):
    # (8, 9) in Boland et al.
    for com in coms:
        m.addConstr(
            dispatch[com.idx, com.source_node] >= com.release
        )
        second_to_last_node = com_node_paths[com.id][-2]
        m.addConstr(
            dispatch[com.idx, second_to_last_node] + duration[com.idx, second_to_last_node] <= com.deadline
        )


def add_dispatch_linking_constraints(m: Model, dispatch: dict[tuple[int, int], Var], com_node_paths: list[list[int]], sol: Solution, coms: list[Commodity]):
    # (10) in Boland et al.
    # TODO: since we link all of these variables, we might as well directly replace them with a variable for service dispatch times
    for com in coms:
        for n_arc, node in enumerate(com_node_paths[com.id][:-1]):
            m.addConstr(
                dispatch[com.idx, node] == sol.commodity_paths[com.id].services[n_arc].start_time
            )



def setupIdentifcationModel(sol: Solution, instance: Instance):
    m = Model("Identification")
    com_node_paths = getCommodityNodePaths(sol, instance.commodities)

    # variables
    dispatch = add_dispatch_variables(m, sol, instance.commodities, com_node_paths)
    duration = add_duration_variables(m, sol, instance.commodities, com_node_paths)
    shorten = add_shorten_variables(m, sol, instance.commodities, com_node_paths)

    # constraints
    add_linking_constraints(m, dispatch, duration, shorten, com_node_paths)
    add_time_consistency_constraints(m, dispatch, duration, com_node_paths)
    add_time_window_constraints(m, dispatch, duration, instance.commodities, com_node_paths)
    add_dispatch_linking_constraints(m, dispatch, com_node_paths, sol, instance.commodities)
    return m, dispatch, duration, shorten


def identifyTooShortArcs(sol: Solution):
    m, dispatch, duration, shorten = setupIdentifcationModel(sol)
    m.optimize()
    shortened_arcs = []
    for (com, node), var in shorten.items():
        if var.x > 0.5:
            shortened_arcs.append((com, node))
