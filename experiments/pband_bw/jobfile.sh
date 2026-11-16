#!/bin/bash -l
#
#
#
# Traces:
#    atk_idle
#    atk_heavy
#
#
# Experiments:
#    aware: --warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/pband_bw/aware.ini
#    blind: --warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/pband_bw/blind.ini
#
#
#
#
sbatch -p debug --mincpus=1 -c 2 -J atk_idle_aware -o atk_idle_aware.out -e atk_idle_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/pband_bw/aware.ini  -traces /home/agam/Github/kryptos/traces/pband_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/pband_bw_atk_idle.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_idle_blind -o atk_idle_blind.out -e atk_idle_blind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/pband_bw/blind.ini  -traces /home/agam/Github/kryptos/traces/pband_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/pband_bw_atk_idle.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_heavy_aware -o atk_heavy_aware.out -e atk_heavy_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/pband_bw/aware.ini  -traces /home/agam/Github/kryptos/traces/pband_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/pband_bw_atk_heavy.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_heavy_blind -o atk_heavy_blind.out -e atk_heavy_blind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/pband_bw/blind.ini  -traces /home/agam/Github/kryptos/traces/pband_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/pband_bw_atk_heavy.champsimtrace.xz"
