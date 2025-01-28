from ddd_snd.snd.solver import solve_snd, solve_csnd
from ddd_snd.solution import Solution
import pytest


def check_tiny_sol(sol: Solution):
    flow_cost = 4
    fixed_cost = 3
    sol.print()
    assert sol is not None
    assert sol.total_cost == flow_cost + fixed_cost
    assert sol.total_flow_cost == flow_cost
    assert sol.total_fixed_cost == fixed_cost
    # have three services, one of which transports two commodities
    assert len(sol.services) == 3
    assert len(sol.commodity_paths) == 3
    assert len([s for s in sol.services if len(s.commodities_transported) > 1]) == 1


def test_solve_snd(tiny_instance):
    sol = solve_snd(tiny_instance, 1)
    check_tiny_sol(sol)


def test_solve_coarser_snd(tiny_instance):
    sol = solve_snd(tiny_instance, 2)  # with discretization of, can not find a solution
    assert sol is None


def test_solve_csnd(tiny_instance):
    sol = solve_csnd(tiny_instance)
    check_tiny_sol(sol)
