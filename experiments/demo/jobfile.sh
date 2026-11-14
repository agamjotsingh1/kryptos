#!/bin/bash -l
#
#
#
# Traces:
#    demo_attack
#    demo_idle
#
#
# Experiments:
#    nopref: --warmup_instructions=10000000 --simulation_instructions=40000000 --config=$(PYTHIA_HOME)/config/nopref.ini
#    pythia: --warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/demo/pythia_config.ini
#
#
#
#
sbatch -p debug --mincpus=1 -c 2 -J demo_attack_nopref -o demo_attack_nopref.out -e demo_attack_nopref.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --config=/home/agam/Github/kryptos/config/nopref.ini  -traces /home/agam/Github/kryptos/traces/demo_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/demo_attacker.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J demo_attack_pythia -o demo_attack_pythia.out -e demo_attack_pythia.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/demo/pythia_config.ini  -traces /home/agam/Github/kryptos/traces/demo_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/demo_attacker.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J demo_idle_nopref -o demo_idle_nopref.out -e demo_idle_nopref.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --config=/home/agam/Github/kryptos/config/nopref.ini  -traces /home/agam/Github/kryptos/traces/demo_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/idle.champsimtrace.xz"
sbatch -p debug --mincpus=1 -c 2 -J demo_idle_pythia -o demo_idle_pythia.out -e demo_idle_pythia.err /home/agam/Github/kryptos/wrapper.sh /home/agam/Github/kryptos/bin/perceptron-multi-multi-no-ship-2core "--warmup_instructions=10000000 --simulation_instructions=40000000 --l2c_prefetcher_types=scooby --config=/home/agam/Github/kryptos/codes/demo/pythia_config.ini  -traces /home/agam/Github/kryptos/traces/demo_victim.champsimtrace.xz /home/agam/Github/kryptos/traces/idle.champsimtrace.xz"
