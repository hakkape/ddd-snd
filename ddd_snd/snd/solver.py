from ..instance import Instance
from ..solution import Solution
from .model import build_snd_model, get_solution
from .time_expansion import (
    create_relaxed_initial_discretization,
    create_regular_discretization,
    DiscretizedGraph,
)
from ..discretization_discovery import (
    setup_identification_model,
    update_timed_services,
    find_nodes_to_insert,
)
from gurobipy import GRB
from math import ceil


def solve_snd(ins: Instance, delta_t: int) -> Solution | None:
    n_nodes_flat = ins.flat_graph.num_nodes()
    time_horizon = max(
        ceil(com.deadline / delta_t) * delta_t for com in ins.commodities
    )
    g_disc = DiscretizedGraph(
        ins.flat_graph,
        create_regular_discretization(n_nodes_flat, time_horizon, delta_t),
        False,
    )
    m, x, y = build_snd_model(ins, g_disc)
    m.optimize()
    print(f"nodes in discretization: {g_disc.num_nodes()}")
    if m.status == GRB.INFEASIBLE:
        return None
    return get_solution(m, x, y, ins.commodities, g_disc)


def solve_csnd(ins: Instance) -> Solution | None:
    # create initial discretized graph
    n_nodes_flat = ins.flat_graph.num_nodes()
    g_disc = DiscretizedGraph(
        ins.flat_graph,
        create_relaxed_initial_discretization(n_nodes_flat, ins.commodities),
        True,
    )

    lb = -10e100
    ub = 10e100
    iteration = 0

    while True:
        # solve model for current discretization
        m, x, y = build_snd_model(ins, g_disc)
        m.setParam("OutputFlag", 0)
        m.optimize()
        if m.status == GRB.INFEASIBLE:
            return None
        sol = get_solution(m, x, y, ins.commodities, g_disc)
        lb = max(sol.total_cost, lb)

        # run model to identify arcs that need to be fixed
        m_fix, dispatch, duration, shorten = setup_identification_model(sol, ins)
        m_fix.setParam("OutputFlag", 0)
        m_fix.optimize()

        # status update
        iteration += 1
        print(
            f"iteration {iteration}: lower bound: {lb}, conflicts: {m_fix.objVal}, nodes in discretization: {g_disc.num_nodes()}"
        )

        # if no problems, we are done:
        if m_fix.objVal == 0:
            update_timed_services(sol, dispatch)
            return sol
        # else: try to fix solution and if that also does not work, refine discretization

        # try to find a feasible solution
        # TODO: not strictly necessary for termination

        # identify arcs that need to be split, adjust discretization, repeat
        nodes_to_insert = find_nodes_to_insert(sol, shorten)

        # update discretization
        for node, time in nodes_to_insert:
            g_disc.refine_discretization(node, time)
