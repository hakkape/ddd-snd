from .instance import Commodity
from dataclasses import dataclass
from gurobipy import Model, GRB, quicksum


@dataclass
class TimedService:
    start_time: int
    end_time: int
    start_node: int
    end_node: int
    travel_time: int
    n_vehicles: int  # number of vehicles used for this service
    cost: float  # cost of vehicles used for this service
    capacity: float  # capacity of vehicles used for this service
    commodities_transported: list[Commodity]

    def arc_to_string(self):
        return f"(({self.start_node}, {self.start_time}),({self.end_node}, {self.end_time}))"


@dataclass
class CommodityPath:
    duration: int  # time between leaving start node and arriving at end node
    flow_cost: float
    services: list[TimedService]


@dataclass
class Solution:
    services: list[TimedService]
    commodity_paths: list[CommodityPath]
    total_flow_cost: float
    total_fixed_cost: float
    total_cost: float

    def print(self):
        print(
            f"Solution with cost {self.total_cost} = {self.total_flow_cost} flow cost + {self.total_fixed_cost} fixed cost"
        )
        print("Services:")
        for service in self.services:
            print(
                f"{service.n_vehicles}x {service.arc_to_string()}, travel time: {service.travel_time},  cost {service.cost}, capacity {service.capacity}"
            )
        print("Commodity paths:")
        for com_id, path in enumerate(self.commodity_paths):
            path_string = ", ".join([s.arc_to_string() for s in path.services])
            print(
                f"Com {com_id}: flow cost {path.flow_cost}, duration {path.duration}, path: {path_string}"
            )
