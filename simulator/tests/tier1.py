import sim
import examples.base_node as base_node
from examples.validator import Validator
from examples.watcher import Watcher
import sim.api as api
import sys
import networkx as nx
from collections import defaultdict
from tests import utils

NUM_TXS_TO_SUBMIT = 20
NUM_VALIDATORS_TIER_1 = 4

def launch(selective_flooding=sim.config.selective_flooding, num_runs=sim.config.num_runs):
    """
    Generates several random topologies on watchers connected a fully-connected Tier1 structure. 
    """
    def test_tasklet(selective_flooding, max_num_runs=1):

        # Allow simulator to fully boot
        yield 2

        run_number = 1
        run_tx_data_watchers = []
        run_scp_data_watchers = []
        run_tx_data_validators = []
        run_scp_data_validators = []
        run_validator_hops_data = []
        run_watcher_hops_data = []      
        run_validator_latency_data = []
        run_watcher_latency_data = []

        important_watchers_tx=[]

        import random
        random.seed(0)

        # try:
        if True:
            for validators, watchers, graph in utils.topology_generator(utils.GraphGeneration.ERDOS_RENYI_CONNECTED, selective_flooding, max_num_runs, num_validators=7, num_watchers=21):

                api.simlog.info("========== Run %i BEGIN, graph size %i, selective flooding enabled %s ==========", run_number, len(
                    validators) + len(watchers), selective_flooding)


                api.simlog.info("Graph %s", [d for n, d in graph.degree()])
                # Submit txs from watcher or validator if no watchers are present
                w = validators[0]
                if watchers:
                    w = random.choice(watchers)
                # w = watchers[-1]
                api.simlog.info("Submit from: %s", w)

                for i in range(NUM_TXS_TO_SUBMIT):
                    w.submit_tx()
                    yield 0.5

                # make sure txs reach everyone
                for v in validators:
                    v.set_simulate_round(False)

                yield 30

                validators_total_tx_traffic, validators_total_scp_traffic, avg_latency_val, watchers_total_tx_traffic, watchers_total_scp_traffic, avg_latency_wat, avg_hops_val, avg_hops_wat = utils.check_invariants(
                    validators, watchers, NUM_TXS_TO_SUBMIT)

                api.simlog.info("validators %i SCP traffic, %i TX traffic",
                                validators_total_scp_traffic, validators_total_tx_traffic)
                api.simlog.info("watchers %i SCP traffic, %i TX traffic",
                                watchers_total_scp_traffic, watchers_total_tx_traffic)

                run_validator_hops_data.append(
                    sum(avg_hops_val) / len(avg_hops_val))
                run_watcher_hops_data.append(
                    sum(avg_hops_wat) / len(avg_hops_wat))
                run_validator_latency_data.append(
                    sum(avg_latency_val) / len(avg_latency_val))
                run_watcher_latency_data.append(
                    sum(avg_latency_wat) / len(avg_latency_wat))

                important_watchers_tx.append(utils.report_high_quality_watchers(w))

                api.simlog.info(
                    "==================== Run %i DONE ====================", run_number)

                run_tx_data_watchers.append(watchers_total_tx_traffic)
                run_scp_data_watchers.append(watchers_total_scp_traffic)

                run_tx_data_validators.append(validators_total_tx_traffic)
                run_scp_data_validators.append(validators_total_scp_traffic)

                if run_number == max_num_runs:
                    break
                else:
                    # Cleanup before the next run
                    for w in watchers:
                        w.remove()
                    for v in validators:
                        v.remove()

                run_number += 1

            api.simlog.info("------------ AVERAGED stats per run ------------")
            api.simlog.info("-------------------  WATCHERS ------------------")

            api.simlog.info("Average transactions per RUN on all watchers: %.2f",
                            sum(run_tx_data_watchers) / len(run_tx_data_watchers))
            #num = sum(important_watchers_tx) / len(important_watchers_tx) if selective_flooding else sum(run_tx_data_watchers) / len(run_tx_data_watchers) / len(watchers)
            num = sum(important_watchers_tx) / len(important_watchers_tx)
            api.simlog.info("Average transactions per RUN on _IMPORTANT_ watchers: %.2f", num)
            api.simlog.info("Average SCP messages per watcher: %.2f",
                            sum(run_scp_data_watchers) / len(run_scp_data_watchers))
            api.simlog.info("-------------------  VALIDATORS ------------------")

            api.simlog.info("Average transactions per validator: %.2f",
                            sum(run_tx_data_validators) / len(run_tx_data_validators))
            api.simlog.info("Average SCP messages per validator: %.2f",
                            sum(run_scp_data_validators) / len(run_scp_data_validators))
            api.simlog.info("---------------------  HOPS   -------------------")

            # With the current quality function, we probably won't see much difference,
            # With the new peer quality, we need to ensure that hop count doesn't go UP
            api.simlog.info("Average hops to reach a validator %.2f", sum(
                run_validator_hops_data) / len(run_validator_hops_data))
            api.simlog.info("Average hops to reach a watcher %.2f", sum(
                run_watcher_hops_data) / len(run_watcher_hops_data))

            api.simlog.info("---------------------  LATENCY -------------------")

            # With the current quality function, we probably won't see much difference,
            # With the new peer quality, we need to ensure that hop count doesn't go UP
            api.simlog.info("Average latency to reach a validator %.2f", sum(
                run_validator_latency_data) / len(run_validator_latency_data))
            api.simlog.info("Average latency to reach a watcher %.2f", sum(
                run_watcher_latency_data) / len(run_watcher_latency_data))

            api.simlog.info("\tSUCCESS!")
        # except Exception as e:
        #     api.simlog.error("Exception occurred: %s" % e)
        #     traceback.print_exc()
        # finally:
        #     sys.exit()

    api.run_tasklet(test_tasklet, selective_flooding, int(num_runs))
