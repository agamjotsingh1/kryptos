#!/bin/bash -l
#
#
#
# Traces:
#    idle
#    benign
#    atk_lo
#    atk_mid
#    atk_hi
#
#
# Experiments:
#    aware: --warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/aware.ini
#    flat: --warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/flat.ini
#
#
#
#
sbatch -p debug --mincpus=1 -c 2 -J idle_aware -o idle_aware.out -e idle_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/aware.ini  -traces /home/agam/Github/kryptos/traces/filltime_steer_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/filltime_steer_idle.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J idle_flat -o idle_flat.out -e idle_flat.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/flat.ini  -traces /home/agam/Github/kryptos/traces/filltime_steer_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/filltime_steer_idle.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J benign_aware -o benign_aware.out -e benign_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/aware.ini  -traces /home/agam/Github/kryptos/traces/filltime_steer_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/filltime_steer_benign.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J benign_flat -o benign_flat.out -e benign_flat.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/flat.ini  -traces /home/agam/Github/kryptos/traces/filltime_steer_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/filltime_steer_benign.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_lo_aware -o atk_lo_aware.out -e atk_lo_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/aware.ini  -traces /home/agam/Github/kryptos/traces/filltime_steer_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/filltime_steer_atk_lo.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_lo_flat -o atk_lo_flat.out -e atk_lo_flat.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/flat.ini  -traces /home/agam/Github/kryptos/traces/filltime_steer_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/filltime_steer_atk_lo.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_mid_aware -o atk_mid_aware.out -e atk_mid_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/aware.ini  -traces /home/agam/Github/kryptos/traces/filltime_steer_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/filltime_steer_atk_mid.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_mid_flat -o atk_mid_flat.out -e atk_mid_flat.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/flat.ini  -traces /home/agam/Github/kryptos/traces/filltime_steer_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/filltime_steer_atk_mid.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_hi_aware -o atk_hi_aware.out -e atk_hi_aware.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/aware.ini  -traces /home/agam/Github/kryptos/traces/filltime_steer_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/filltime_steer_atk_hi.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J atk_hi_flat -o atk_hi_flat.out -e atk_hi_flat.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=3000000 --simulation_instructions=12000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/filltime_steer/flat.ini  -traces /home/agam/Github/kryptos/traces/filltime_steer_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/filltime_steer_atk_hi.champsimtrace.xz"
