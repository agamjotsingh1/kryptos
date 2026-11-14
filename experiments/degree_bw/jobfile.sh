#!/bin/bash -l
#
#
#
# Traces:
#    atk_idle
#    atk_light
#    atk_medium
#    atk_heavy
#    benign_cache
#
#
# Experiments:
#    bwaware: --warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwaware.ini
#    bwblind: --warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwblind.ini
#
#
#
#
sbatch -p debug --mincpus=1 -c 2 -J atk_idle_bwaware -o atk_idle_bwaware.out -e atk_idle_bwaware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwaware.ini  -traces /home/agam/Github/kryptos/traces/degree_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/degree_bw_atk_idle.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_idle_bwblind -o atk_idle_bwblind.out -e atk_idle_bwblind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwblind.ini  -traces /home/agam/Github/kryptos/traces/degree_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/degree_bw_atk_idle.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_light_bwaware -o atk_light_bwaware.out -e atk_light_bwaware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwaware.ini  -traces /home/agam/Github/kryptos/traces/degree_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/degree_bw_atk_light.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_light_bwblind -o atk_light_bwblind.out -e atk_light_bwblind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwblind.ini  -traces /home/agam/Github/kryptos/traces/degree_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/degree_bw_atk_light.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_medium_bwaware -o atk_medium_bwaware.out -e atk_medium_bwaware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwaware.ini  -traces /home/agam/Github/kryptos/traces/degree_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/degree_bw_atk_medium.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_medium_bwblind -o atk_medium_bwblind.out -e atk_medium_bwblind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwblind.ini  -traces /home/agam/Github/kryptos/traces/degree_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/degree_bw_atk_medium.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_heavy_bwaware -o atk_heavy_bwaware.out -e atk_heavy_bwaware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwaware.ini  -traces /home/agam/Github/kryptos/traces/degree_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/degree_bw_atk_heavy.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_heavy_bwblind -o atk_heavy_bwblind.out -e atk_heavy_bwblind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwblind.ini  -traces /home/agam/Github/kryptos/traces/degree_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/degree_bw_atk_heavy.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J benign_cache_bwaware -o benign_cache_bwaware.out -e benign_cache_bwaware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwaware.ini  -traces /home/agam/Github/kryptos/traces/degree_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/degree_bw_benign_cache.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J benign_cache_bwblind -o benign_cache_bwblind.out -e benign_cache_bwblind.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=5000000 --simulation_instructions=10000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/degree_bw/bwblind.ini  -traces /home/agam/Github/kryptos/traces/degree_bw_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/degree_bw_benign_cache.champsimtrace.xz"
