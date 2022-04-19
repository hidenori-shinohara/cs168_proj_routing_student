import sim
from examples.validator import Validator
from examples.watcher import Watcher
import sim.api as api
import sys
import networkx as nx
from collections import defaultdict
import random
import examples.base_node as base_node
import numpy as np

random.seed(0)

NUM_TXS_TO_SUBMIT = 20
NUM_VALIDATORS_TIER_1 = 4
NUM_WATCHERS = 7


def topology_generator_helper(num_validators, selective_flooding):

    # use networkx utils to help determine properties of the graph
    # p = 2 * ln(n) / n
    # https://en.wikipedia.org/wiki/Erd%C5%91s%E2%80%93R%C3%A9nyi_model
    assert NUM_WATCHERS > 0, "Number of watchers must be positive"

    graph = nx.erdos_renyi_graph(
        NUM_WATCHERS, 2 * np.log(NUM_WATCHERS) / NUM_WATCHERS)

    flood = base_node.Flooding.SELECTIVE if selective_flooding else base_node.Flooding.FLOOD_ALL

    # Setup validators first
    validators = []
    for i in range(num_validators):
        s = Validator.create('val' + str(i), flood)
        validators.append(s)

    watchers = []
    for node in graph.nodes():
        s = Watcher.create('wat' + str(node), flood)
        watchers.append(s)

    # Connect validators fully regardless of the watcher topology
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

    # Now connect
    for edge in graph.edges.data():
        wat1 = watchers[edge[0]]
        wat2 = watchers[edge[1]]
        wat1.linkTo(wat2)

    random.choice(watchers).linkTo(random.choice(validators))

    return [(validators, watchers, graph), ]


def launch(selective_flooding=sim.config.selective_flooding, num_runs=sim.config.num_runs):
    """
    Generates several random topologies on watchers connected a fully-connected Tier1 structure. 
    """
    def test_tasklet(selective_flooding, max_num_runs=1):

        run_tx_data = []
        run_scp_data = []
        run_validator_hops_data = []
        run_watcher_hops_data = []
        num_to_disconnect = 2

        # Random 10 churns
        for i in range(max_num_runs):
            for validators, watchers_ref, graph in topology_generator_helper(NUM_VALIDATORS_TIER_1, selective_flooding):

                watchers = watchers_ref.copy()

                api.simlog.info("========== Run %i BEGIN, graph size %i, selective flooding enabled %s ==========", i, len(
                    validators) + len(watchers), selective_flooding)

                yield 2

                w = validators[0]
                if watchers:
                    w = random.choice(watchers)

                churn = True
                for i in range(NUM_TXS_TO_SUBMIT):
                    w.submit_tx()
                    yield 1

                    if churn and i > (NUM_TXS_TO_SUBMIT / 3):
                        for v in validators:
                            v.set_simulate_round(False)
                        # crank a bit to let the transaction propagate
                        yield 2

                        # bug in peer quality - quality needs to be recomputed when we disconnect
                        discon = [2, 5]
                        to_pop = []
                        for idx in discon:
                            graph.remove_node(idx)
                            watchers[idx].disconnect(True)
                            watchers[idx].remove()
                            to_pop.append(watchers[idx])

                        for wat in to_pop:
                            watchers.remove(wat)

                        rand_wat = random.choice(watchers)
                        rand_val = random.choice(validators)
                        if not (rand_wat.isConnectedTo(rand_val)):
                            rand_wat.linkTo(rand_val)

                        w = random.choice(watchers)
                        churn = False

                        # crank a bit more to complete disconnect/reconnect
                        yield 3

                        for v in validators:
                            v.set_simulate_round(True)

                for v in validators:
                    v.set_simulate_round(False)

                yield 10

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
                    watcher_count = get_count(watcher.get_floodmap(), "SCP")
                    assert watcher_count >= num_scp_msgs_generated, "watcher %s missing SCP, expected %i, actual %i" % (
                        watcher.name, num_scp_msgs_generated, watcher_count)

                    # Report traffic stats
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
                for w in watchers:
                    w.remove()
                for v in validators:
                    v.remove()

                api.simlog.info(
                    "==================== Run %i DONE ====================", i)

                # just count watchers since we haven't implemented flooding policies on validators
                run_tx_data.append(watchers_total_tx_traffic)
                run_scp_data.append(watchers_total_scp_traffic)

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

    api.run_tasklet(test_tasklet, selective_flooding, int(num_runs))
