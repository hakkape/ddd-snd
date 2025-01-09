from .time_expansion import DiscretizedGraph, TimeNodeData
from .instance import Instance, Commodity
from .solution import TimedService, CommodityPath, Solution
from gurobipy import Model, GRB, quicksum, Var
from bisect import bisect_left


def add_design_variables(m: Model, g: DiscretizedGraph)-> dict[int, Var]:
    y = {}
    for flat_arc in DiscretizedGraph.g_flat.edge_indices():
        fixed_cost = DiscretizedGraph.g_flat[flat_arc].fixed_cost
        for expanded_arc in DiscretizedGraph.flat_to_expanded_arcs[flat_arc]:
            y[expanded_arc] = m.addVar(
                vtype=GRB.INTEGER, name=f"x_{expanded_arc}", obj=fixed_cost
            )

    return y


def add_flow_variables(m: Model, coms: list[Commodity], g: DiscretizedGraph) -> dict[tuple[int, int], Var]:
    x = {}
    for arc in DiscretizedGraph.edge_indices():
        flow_cost = g.get_edge_data_by_index(arc).flow_cost
        for com in coms:
            x[arc, com.id] = m.addVar(
                vtype=GRB.BINARY, name=f"x_{arc}_{com}", obj=flow_cost * com.quantity
            )

    return x


def add_flow_conservation_constraints(
    m: Model, x: dict, coms: list[Commodity], g: DiscretizedGraph
):
    for com in coms:
        # find source and sink node of commodity in time expanded graph
        k_source = bisect_left(g.node_to_times[com.source_node], com.release)
        source_node = g.flat_to_expanded_nodes[com.source_node][k_source]
        k_sink = bisect_left(g.node_to_times[com.sink_node], com.deadline)
        sink_node = g.flat_to_expanded_nodes[com.sink_node][k_sink]
        for node in g.node_indices():
            rhs = 0
            if node == source_node:
                rhs = 1
            elif node == sink_node:
                rhs = -1
            m.addConstr(
                quicksum(x[arc, com.id] for arc in g.out_edges(node))
                - quicksum(x[arc, com.id] for arc in g.in_edges(node))
                == rhs
            )


def add_capacity_constraints(
    m: Model, x: dict, y: dict, coms: list[Commodity], g: DiscretizedGraph
):
    # for each time expanded non-holding arc, capacity of vehicles must not be exceeded by sum of commodity flows
    for arc in g.edge_indices():
        vehicle_capacity = g.get_edge_data_by_index(arc).capacity
        if vehicle_capacity is not None:
            flow = quicksum(com.quantity * x[arc, com.id] for com in coms)
            capacity = vehicle_capacity * y[arc]
            m.addConstr(flow <= capacity)


def build_snd_model(instance: Instance, g: DiscretizedGraph):
    m = Model("snd")

    # variables
    x = add_flow_variables(m, g)
    y = add_design_variables(m, g)

    # constraints
    add_flow_conservation_constraints(m, x, instance.commodities, g)
    add_capacity_constraints(m, x, y, instance.commodities, g)

    return m, x, y


def getSolution(m: Model, x: dict, y: dict, coms: list[Commodity], g: DiscretizedGraph):
    # check that optimal solution found
    if m.status != GRB.OPTIMAL:
        raise Exception("Optimization was stopped with status " + str(m.status))

    # extract solution
    services = []
    commodity_paths = [CommodityPath(duration=0, flow_cost=0, services=[]) for _ in coms]
    total_flow_cost = 0
    total_fixed_cost = 0

    # for each service arc, determine if vehicles drive over it
    for arc in g.edge_indices():
        is_holding_arc = g.get_edge_data_by_index(arc).capacity is not None
        if is_holding_arc:
            continue
        val = round(y[arc].x)
        if val == 0:
            continue
        # collect arc data
        i, j = g.get_edge_endpoints_by_index(arc)
        arc_data = g.get_edge_data_by_index(arc)
        # collect solution data
        commodities_transported = []
        service_cost = val * arc_data.fixed_cost
        total_fixed_cost += service_cost
        # determine commodities on this service arc
        for com in coms:
            if x[arc, com.id].x > 0.5: 
                commodities_transported.append(com)
                # add costs
                arc_flow_cost = com.quantity * arc_data.flow_cost
                commodity_paths[com.id].flow_cost += arc_flow_cost
                commodity_paths[com.id].duration += arc_data.travel_time
                total_flow_cost += arc_flow_cost
        
        service = TimedService(
            start_time=g[i].time,
            end_time=g[j].time,
            start_node=g[i].flat_id,
            end_node=g[j].flat_id,
            travel_time=arc_data.travel_time,
            cost=service_cost,
            capacity=val * arc_data.capacity,
            commodities_transported=commodities_transported,
        )
        # store service in each commodity path
        for com in commodities_transported:
            commodity_paths[com.id].services.append(service)
        
        services.append(service)
        
    # sort services for each commodity along path
    for com in coms:
        services_sorted = []
        current_node = com.source_node
        while current_node != com.sink_node:
            found = False
            for service in services:
                if service.start_node == current_node:
                    services_sorted.append(service)
                    current_node = service.end_node
                    found = True
                    break
            if not found:
                raise Exception("Could not construct service")
        commodity_paths[com.id].services = services_sorted

    return Solution(
        services=services,
        commodity_paths=commodity_paths,
        total_flow_cost=total_flow_cost,
        total_fixed_cost=total_fixed_cost,
        total_cost=total_flow_cost + total_fixed_cost,
    )
