#!/usr/bin/env python3
# For command line usage help, call this script with the flag "-h"
import argparse
import os, glob
from pathlib import Path
from ddd_snd.instance import read_modified_dow_instance, Instance
from ddd_snd.solver import solve_csnd, solve_snd


# Define here the functionality of the script
def main(instance_path: Path, delta_t: float, full_model: bool):
    ins = read_modified_dow_instance(instance_path, delta_t)
    if full_model:
        sol = solve_snd(ins, 1) 
    else:
        sol = solve_csnd(ins)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Solves timed C instance with given discretization"
    )

    parser.add_argument(
        "number",
        metavar="NUMBER",
        type=int,
        help="Number of instance to solve",
    )
    parser.add_argument(
        "delta_t",
        metavar="DELTA_T",
        type=float,
        help="Time discretization to use (in hours)",
    )
    # optional flag to solve with full model instead of DDD
    parser.add_argument(
        "-f",
        action="store_true",
        help="Solve with full model instead of DDD",
    )

    # -- Reading out the arguments the user entered --
    instance_number = parser.parse_args().number
    delta_t = parser.parse_args().delta_t
    full_model = parser.parse_args().f
    instance_path = Path(f"../../instances/C_timed/c{instance_number}.dow")

    # -- Calling main function --
    main(instance_path, delta_t, full_model)
