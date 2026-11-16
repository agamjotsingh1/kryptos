#!/bin/bash -l
#
#
#
# Traces:
#    atk_d_lo
#    atk_d_mid
#    atk_d_hi
#
#
# Experiments:
#    aware: --warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/aware.ini
#    blind: --warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/blind.ini
#
#
#
#
sbatch -p debug --mincpus=1 -c 2 -J atk_d_lo_aware -o atk_d_lo_aware.out -e atk_d_lo_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/aware.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_atk_d_lo.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_d_lo_blind -o atk_d_lo_blind.out -e atk_d_lo_blind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/blind.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_atk_d_lo.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_d_mid_aware -o atk_d_mid_aware.out -e atk_d_mid_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/aware.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_atk_d_mid.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_d_mid_blind -o atk_d_mid_blind.out -e atk_d_mid_blind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/blind.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_atk_d_mid.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_d_hi_aware -o atk_d_hi_aware.out -e atk_d_hi_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/aware.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_atk_d_hi.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_d_hi_blind -o atk_d_hi_blind.out -e atk_d_hi_blind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=50000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/blend_bw/blind.ini  -traces /home/agam/Github/kryptos/traces/blend_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/blend_bw_atk_d_hi.champsimtrace.xz"
