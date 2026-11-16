#!/bin/bash -l
#
#
#
# Traces:
#    atk_idle
#    atk_light
#    atk_medium
#    atk_heavy
#
#
# Experiments:
#    aware: --warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/policy_bw/aware.ini
#    blind: --warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/policy_bw/blind.ini
#
#
#
#
sbatch -p debug --mincpus=1 -c 2 -J atk_idle_aware -o atk_idle_aware.out -e atk_idle_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/policy_bw/aware.ini  -traces /home/agam/Github/kryptos/traces/policy_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/policy_bw_atk_idle.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_idle_blind -o atk_idle_blind.out -e atk_idle_blind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/policy_bw/blind.ini  -traces /home/agam/Github/kryptos/traces/policy_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/policy_bw_atk_idle.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_light_aware -o atk_light_aware.out -e atk_light_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/policy_bw/aware.ini  -traces /home/agam/Github/kryptos/traces/policy_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/policy_bw_atk_light.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_light_blind -o atk_light_blind.out -e atk_light_blind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/policy_bw/blind.ini  -traces /home/agam/Github/kryptos/traces/policy_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/policy_bw_atk_light.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_medium_aware -o atk_medium_aware.out -e atk_medium_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/policy_bw/aware.ini  -traces /home/agam/Github/kryptos/traces/policy_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/policy_bw_atk_medium.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_medium_blind -o atk_medium_blind.out -e atk_medium_blind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/policy_bw/blind.ini  -traces /home/agam/Github/kryptos/traces/policy_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/policy_bw_atk_medium.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_heavy_aware -o atk_heavy_aware.out -e atk_heavy_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/policy_bw/aware.ini  -traces /home/agam/Github/kryptos/traces/policy_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/policy_bw_atk_heavy.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_heavy_blind -o atk_heavy_blind.out -e atk_heavy_blind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/policy_bw/blind.ini  -traces /home/agam/Github/kryptos/traces/policy_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/policy_bw_atk_heavy.champsimtrace.xz"
