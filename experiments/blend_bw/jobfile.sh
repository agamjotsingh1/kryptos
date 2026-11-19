#!/bin/bash
#
#
#
# Traces:
#    flo
#    fmid
#    fhi
#
#
# Experiments:
#    aware: --warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/aware_blend.ini
#    blind: --warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/blind_blend.ini
#
#
#
#
/home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core --warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/aware_blend.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_flo.champsimtrace.xz > flo_aware.out 2>&1
/home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core --warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/blind_blend.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_flo.champsimtrace.xz > flo_blind.out 2>&1
/home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core --warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/aware_blend.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_fmid.champsimtrace.xz > fmid_aware.out 2>&1
/home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core --warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/blind_blend.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_fmid.champsimtrace.xz > fmid_blind.out 2>&1
/home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core --warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/aware_blend.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_fhi.champsimtrace.xz > fhi_aware.out 2>&1
/home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core --warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/blind_blend.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_fhi.champsimtrace.xz > fhi_blind.out 2>&1
