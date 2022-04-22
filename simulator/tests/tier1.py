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

# TODO: refactor topology generator, remove duplication with tests.tier1

def topology_generator_helper(num_validators, selective_flooding, num_runs):

    graph_list = nx.generators.graph_atlas_g()
    assert graph_list is not None, "invalid graph list"
    assert len(graph_list) > 0, "no graphs"

    flood = base_node.Flooding.SELECTIVE if selective_flooding else base_node.Flooding.FLOOD_ALL
    for graph in random.sample(graph_list, min(num_runs, len(graph_list))):

        # Setup validators first
        validators = []
        for i in range(num_validators):
            s = Validator.create('val' + str(i), flood)
            validators.append(s)

        def connectAll(nodes):
            visited = []
            for v in nodes:
                for v_inner in nodes:
                    if v == v_inner or v_inner in visited:
                        continue
                    else:
                        v.linkTo(v_inner)
                visited.append(v)

        connectAll(validators)

        watchers = []
        for node in graph.nodes():
            s = Watcher.create('wat' + str(node), flood)
            watchers.append(s)

        # Now connect
        for edge in graph.edges.data():
            wat1 = watchers[edge[0]]
            wat2 = watchers[edge[1]]
            wat1.linkTo(wat2)

        # Finally connect to validators
        if watchers:
            if not nx.is_connected(graph):
                for cc in nx.connected_components(graph):
                    node = cc.pop()
                    watchers[node].linkTo(random.choice(validators))

            else:
                random.choice(watchers).linkTo(random.choice(validators))

        yield validators, watchers


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
            for validators, watchers in topology_generator_helper(NUM_VALIDATORS_TIER_1, selective_flooding, max_num_runs):

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
                yield 15

                # all flood traffic made it to all nodes
                def get_count(floodmap, type): return len(
                    [item for item in floodmap if type in item])
                validators_total_tx_traffic = 0
                validators_total_scp_traffic = 0
                avg_hops_val = []
                num_scp_msgs_generated = validators[0].rounds_simulated * len(
                    validators)

                for validator in validators:
                    # Ensure all transactions and SCP messages made it
                    floodmap = validator.get_floodmap()
                    num_txs = get_count(floodmap, "Tx")
                    num_scp = get_count(floodmap, "SCP")

                    assert num_txs == NUM_TXS_TO_SUBMIT, "validator missing TXs, expected %i, actual %i" % (
                        NUM_TXS_TO_SUBMIT, num_txs)
                    assert num_scp >= num_scp_msgs_generated, "validator missing SCP, expected %i, actual %i" % (
                        num_scp_msgs_generated, num_scp)

                    # Report traffic stats
                    validator.report(True)
                    validators_total_scp_traffic += validator.scp_unique_count + \
                        validator.scp_duplicate_count
                    validators_total_tx_traffic += validator.tx_unique_count + \
                        validator.tx_duplicate_count
                    avg_hops_val.append(
                        sum(validator.trace) / len(validator.trace))

                watchers_total_tx_traffic = 0
                watchers_total_scp_traffic = 0
                avg_hops_wat = []

                for watcher in watchers:
                    # Ensure all SCP messages made it to all watchers
                    assert get_count(watcher.get_floodmap(
                    ), "SCP") == num_scp_msgs_generated, "watcher missing SCP messages"

                    # Report traffic stats
                    # TODO: add shortest path
                    watcher.report(False)
                    watchers_total_scp_traffic += watcher.scp_unique_count + watcher.scp_duplicate_count
                    watchers_total_tx_traffic += watcher.tx_unique_count + watcher.tx_duplicate_count
                    avg_hops_wat.append(
                        sum(watcher.trace) / len(watcher.trace))

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
