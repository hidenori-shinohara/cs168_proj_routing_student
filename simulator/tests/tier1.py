import sim
import examples.base_node as base_node
from examples.validator import Validator
from examples.watcher import Watcher
import sim.api as api
import sys
import networkx as nx
from collections import defaultdict
import random
from tests import utils

random.seed(0)

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
        run_tx_data = []
        run_scp_data = []
        run_validator_hops_data = []
        run_watcher_hops_data = []

        # try:
        if True:
            for validators, watchers, graph in utils.topology_generator(utils.GraphGeneration.ATLAS, selective_flooding, max_num_runs):

                api.simlog.info("========== Run %i BEGIN, graph size %i, selective flooding enabled %s ==========", run_number, len(
                    validators) + len(watchers), selective_flooding)

                # Submit txs from watcher or validator if no watchers are present
                w = validators[0]
                if watchers:
                    w = random.choice(watchers)

                for i in range(NUM_TXS_TO_SUBMIT):
                    w.submit_tx()
                    yield 1

                # make sure txs reach everyone
                for v in validators:
                    v.set_simulate_round(False)
                yield 10

                validators_total_tx_traffic, validators_total_scp_traffic, avg_hops_val, watchers_total_tx_traffic, watchers_total_scp_traffic, avg_hops_wat = utils.check_invariants(
                    validators, watchers, NUM_TXS_TO_SUBMIT)

                api.simlog.info("validators %i SCP traffic, %i TX traffic",
                                validators_total_scp_traffic, validators_total_tx_traffic)
                api.simlog.info("watchers %i SCP traffic, %i TX traffic",
                                watchers_total_scp_traffic, watchers_total_tx_traffic)

                run_validator_hops_data.append(
                    sum(avg_hops_val) / len(avg_hops_val))
                run_watcher_hops_data.append(
                    sum(avg_hops_wat) / len(avg_hops_wat))

                # Cleanup before the next run
                if max_num_runs > 1:
                    for w in watchers:
                        w.remove()
                    for v in validators:
                        v.remove()

                api.simlog.info(
                    "==================== Run %i DONE ====================", run_number)

                # just count watchers since we haven't implemented flooding policies on validators
                run_tx_data.append(watchers_total_tx_traffic)
                run_scp_data.append(watchers_total_scp_traffic)

                if run_number == max_num_runs:
                    break

                run_number += 1

            api.simlog.info("------ AVERAGED stats per run ------")
            api.simlog.info("Average transactions: %.2f",
                            sum(run_tx_data) / len(run_tx_data))
            api.simlog.info("Average SCP messages: %.2f",
                            sum(run_scp_data) / len(run_scp_data))
            api.simlog.info("------------------------------------")

            # With the current quality function, we probably won't see much difference,
            # With the new peer quality, we need to ensure that hop count doesn't go UP
            api.simlog.info("validators AVG hop count %.2f", sum(
                run_validator_hops_data) / len(run_validator_hops_data))
            api.simlog.info("watchers AVG hop count %.2f", sum(
                run_watcher_hops_data) / len(run_watcher_hops_data))

            api.simlog.info("\tSUCCESS!")
        # except Exception as e:
        #     api.simlog.error("Exception occurred: %s" % e)
        #     traceback.print_exc()
        # finally:
        #     sys.exit()

    api.run_tasklet(test_tasklet, selective_flooding, int(num_runs))
