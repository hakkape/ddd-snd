# Dynamic Discretization Discovery for Service Network Design
An implementation of the algorithm by Boland et al. 2017 ["The Continuous-Time Service Network Design Problem"](https://doi.org/10.1287/opre.2017.1624).

# Installation
Works on `Python 3.12.2`. Needs a `Gurobi` license installed.
```bash
pip install -e . # local editable installation
```

# Usage 
```bash
# inputs: 
# - NUMBER: the number of the .dow file to solve, e.g., NUMBER = 33 -> c33.dow
# - DELTA_T: time discretization to use (in hours), e..g, DELTA_T = 0.5 -> time points represent half hours
# (travel times in instance get rounded up, release times rounded up, deadlines rounded down to closest time point)
# optional flag -f: solve fully time discretized model instead of using DDD
scripts/solving/solve_timed_C_instance.py <NUMBER> <DELTA_T> [-f]
```
# Instance Format
Note: instance format does NOT support comments, added below for explanation.
Is derived from the `.dow` format used by the `C` instances, see `instances/` folder for more information.
Nodes are indexed by integers starting from 1. 
Flow costs, capacities, fixed costs, travel times, commodity quantities, release times and deadlines can be given as decimal numbers.
```
Some comment # first line is ignored
NUM_NODES NUM_ARCS NUM_COMMODITIES
TAIL_NODE HEAD_NODE FLOW_COST CAPACITY FIXED_COST TRAVEL_TIME # arc information
...
SOURCE_NODE SINK_NODE QUANTITY RELEASE_TIME DEADLINE_TIME # commodity information
```