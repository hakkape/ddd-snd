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
    cost: float  # cost of vehicles used for this service
    capacity: float  # capacity of vehicles used for this service
    commodities_transported: list[Commodity]


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



    