from ddd_snd.instance import Instance, NodeData, ArcData, Commodity
import glob
import rustworkx as rx
from pathlib import Path
from tqdm import tqdm
from numpy import random

input_path = "../../instances/C" 
output_path = "../../instances/C_timed"

def read_unmodified_dow_instance(path: Path) -> Instance:
    # instances in dow format with additional travel times and commodity release and deadline times
    with open(path, "r") as f:
        lines = f.readlines()
    n_nodes, n_arcs, n_commodities = map(int, lines[1].split())
    flat_graph = rx.PyDiGraph()
    for i in range(n_nodes):
        flat_graph.add_node(NodeData(name = i + 1))
    for i, line in enumerate(lines[2 : n_arcs + 2]):
        i, j, flow_cost, capacity, fixed_cost = map(float, line.split()[:5])
        flat_graph.add_edge(int(i) - 1, int(j) - 1, ArcData(0, flow_cost, fixed_cost, capacity))
    commodities = []
    for line in lines[n_arcs + 2 :]:
        source_node, sink_node, quantity, = line.split()[:3]
        source_node = int(source_node) - 1
        sink_node = int(sink_node) - 1
        quantity = float(quantity)
        commodities.append(Commodity(len(commodities), source_node, sink_node, quantity, 0, 0))
    return Instance(flat_graph, commodities)

def write_modified_dow_instance(instance: Instance, path: Path):
    g = instance.flat_graph
    with open(path, "w") as f:
        f.write("modified according to Boland et al. 2017\n")
        f.write(f"{g.num_nodes()} {g.num_edges()} {len(instance.commodities)}\n")
        for arc in instance.flat_graph.edge_indices():
            i, j = instance.flat_graph.get_edge_endpoints_by_index(arc)
            arc_data = instance.flat_graph.get_edge_data_by_index(arc)
            f.write(f"{int(g[i].name)} {int(g[j].name)} {int(arc_data.flow_cost)} {int(arc_data.capacity)} {int(arc_data.fixed_cost)} {float(arc_data.travel_time):.2f}\n")
        for com in instance.commodities:
            f.write(f"{int(com.source_node) + 1} {int(com.sink_node) + 1} {int(com.quantity)} {float(com.release):.2f} {float(com.deadline):.2f}\n")
            
def sample_release_time(average_path_length: float, standard_deviation_factor: float = 1/6):
    valid_release_time = False
    standard_deviation = average_path_length * standard_deviation_factor
    min_value = average_path_length - 3 * standard_deviation
    max_value = average_path_length + 3 * standard_deviation
    while not valid_release_time:
        start_time = random.normal(average_path_length, standard_deviation)
        valid_release_time = (start_time >= min_value) and (start_time <= max_value)
    return start_time


def sample_deadline(average_path_length: float, release_time:float, com_path_length: float, mean_factor: float = 1/4):
    valid_deadline = False
    mean = average_path_length * mean_factor
    standard_deviation = mean / 6
    min_value = mean - 3 * standard_deviation
    max_value = mean + 3 * standard_deviation
    while not valid_deadline:
        variation = random.normal(mean, standard_deviation) 
        valid_deadline = (variation >= min_value) and (variation <= max_value)
    return release_time + com_path_length + variation
            
def time_DOW_instance(ins: Instance):
    cost_per_mile = 0.55
    miles_per_hour = 60
    cost_per_hour = cost_per_mile * miles_per_hour
    # so fixed_cost = cost_per_hour * travel_time => travel_time = fixed_cost / cost_per_hour
    for arc in ins.flat_graph.edge_indices():
        arc_data = ins.flat_graph.get_edge_data_by_index(arc)
        arc_data.travel_time = float(arc_data.fixed_cost / cost_per_hour)

    # find shortest path lengths (with respect to travel time) for each commodity
    lengths = rx.all_pairs_dijkstra_path_lengths(ins.flat_graph,lambda x: x.travel_time)
    
    average_path_length = sum([lengths[com.source_node][com.sink_node] for com in ins.commodities]) / len(ins.commodities)
    
    for com in ins.commodities:
        com.release = float(sample_release_time(average_path_length))
        com.deadline = float(sample_deadline(average_path_length, com.release, lengths[com.source_node][com.sink_node]))
    

if __name__ == "__main__":
    # create output directory if it does not exist
    Path(output_path).mkdir(parents=True, exist_ok=True)
    for path in tqdm(glob.glob(f"{input_path}/*.dow")):
        ins = read_unmodified_dow_instance(path)
        time_DOW_instance(ins)
        write_modified_dow_instance(ins, Path(f"{output_path}/{Path(path).name}"))
