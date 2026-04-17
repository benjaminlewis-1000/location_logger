#! /usr/bin/env python

import os
import numpy as np
from python_tsp.exact import solve_tsp_dynamic_programming
from python_tsp.heuristics import solve_tsp_simulated_annealing, solve_tsp_local_search, solve_tsp_lin_kernighan
import time
import fast_tsp

# for size in [5, 20, 100, 1000, 3500]:

#     dist = np.random.randint(1, 100, (size, size))
#     np.fill_diagonal(dist, 0)
#     dist = dist + dist.T
#     # s = time.time()
#     # ans = solve_tsp_local_search(dist, max_processing_time=3, perturbation_scheme='ps6')
#     # print(time.time() - s, f" sec elapsed w {size} points", ans[1])
#     # s = time.time()
#     # ans = solve_tsp_local_search(dist, max_processing_time=10, perturbation_scheme='ps6')
#     # print(time.time() - s, f" sec elapsed w {size} points", ans[1])
#     # s = time.time()
#     # ans = solve_tsp_local_search(dist, max_processing_time=30, perturbation_scheme='ps6')
#     # print(time.time() - s, f" sec elapsed w {size} points", ans[1])
#     s = time.time()
#     ans = solve_tsp_dynamic_programming(dist)
#     print(time.time() - s, f" sec elapsed w {size} points exact", ans[1])
#     s = time.time()
#     ans = solve_tsp_lin_kernighan(dist)
#     print(time.time() - s, f" sec elapsed w {size} points", ans[1])
#     s = time.time()
#     ans2 = fast_tsp.find_tour(dist)
#     print(time.time() - s, f" sec elapsed w {size} points, FAST", np.sum(ans[1]))
#     print()

# exit()

def read_dist(file):
    startread = False
    num_lines = sum(1 for _ in open(file))
    num_header_lines = 0 
    line_no = 0
    matrix = None
    with open(file, 'r') as fh:
        lines = fh.readlines()
        for line in lines:
            # Process each line
            data = line.strip()

            if startread:
                nums = data.split()
                nums = [int(n) for n in nums]
                matrix[line_no, :line_no + 1] = nums
                line_no += 1
            else:
                num_header_lines += 1

            if data == 'EDGE_WEIGHT_SECTION':
                startread = True
                matrix_size = num_lines - num_header_lines
                print(matrix_size)
                matrix = np.zeros( (matrix_size, matrix_size) )

    matrix = matrix + matrix.T
    assert np.all(matrix == matrix.T)

    return matrix



file = '/home/lewisbp/Downloads/usa3100_mixed.tsp'
matrix = read_dist(file)

ans_init = solve_tsp_lin_kernighan(matrix)
ans_2 = solve_tsp_local_search(matrix, max_processing_time=30, perturbation_scheme='ps6', x0=ans_init[0])
ans_4 = solve_tsp_simulated_annealing(matrix, max_processing_time=30, perturbation_scheme='ps6', x0=ans_init[0])
ans_3 = fast_tsp.find_tour(matrix.astype(np.int32))
print(ans_init[1], ans_2[1], np.sum(ans_3))