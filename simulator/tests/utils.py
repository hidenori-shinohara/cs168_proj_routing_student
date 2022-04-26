import examples.base_node as base_node
from examples.validator import Validator
from examples.watcher import Watcher
import networkx as nx
from enum import Enum
import numpy as np
import sim.api as api

class GraphGeneration(Enum):
  # all possible graphs up to 7
  ATLAS=1
  # Erdos-Renyi model with p = 2 * ln(n) / n (most likely connected graph)
  # https://en.wikipedia.org/wiki/Erd%C5%91s%E2%80%93R%C3%A9nyi_model
  ERDOS_RENYI_CONNECTED=2

class Latency(Enum):
    FAST=0.03
    MEDIUM=0.1
    SLOW=0.4

def get_count(floodmap, type): 
    return len([item for item in floodmap if type in item])

def topology_generator(graph_generation, selective_flooding, num_runs, num_validators=4, num_watchers=7):

    import random
    random.seed(0)

    graph_list = []
    if graph_generation == GraphGeneration.ATLAS:
        graph_list = generate_graphs_atlas(num_runs, random)
    elif graph_generation == GraphGeneration.ERDOS_RENYI_CONNECTED:
        graph_list = generate_erdos_renyi(num_runs, num_watchers)


    flood = base_node.Flooding.SELECTIVE if selective_flooding else base_node.Flooding.FLOOD_ALL
    for graph in graph_list:

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
                        v.linkTo(v_inner, latency=Latency.FAST.value)
                        # v.linkTo(v_inner)
                visited.append(v)

        connectAll(validators)

        watchers = []
        for node in graph.nodes():
            s = Watcher.create('wat' + str(node), flood)
            watchers.append(s)

        # Now map graph edges to watcher connections
        for edge in graph.edges.data():
            wat1 = watchers[edge[0]]
            wat2 = watchers[edge[1]]
            # p=[0.6, 0.3, 0.1]
            helper_random_list = [Latency.SLOW.value] + [Latency.MEDIUM.value] * 3 + [Latency.FAST.value] * 6
            wat1.linkTo(wat2, latency=random.choice(helper_random_list))
            # wat1.linkTo(wat2)

        # Finally connect to tier1 to ensure the graph is fully connected
        if watchers:
            if not nx.is_connected(graph):
                for cc in nx.connected_components(graph):
                    node = cc.pop()
                    watchers[node].linkTo(random.choice(validators))

            else:
                for w in random.sample(watchers, num_validators):
                    for v in validators:
                        w.linkTo(v, latency=Latency.FAST.value)
                        # w.linkTo(v)


        yield validators, watchers, graph

def check_invariants(validators, watchers, total_txs):

    # all flood traffic made it to all nodes
    validators_total_tx_traffic = 0
    validators_total_scp_traffic = 0
    avg_latency_val = []
    avg_hops_val = []
    num_scp_msgs_generated = validators[0].rounds_simulated * len(
        validators)

    for validator in validators:
        # Ensure all transactions and SCP messages made it
        floodmap = validator.get_floodmap()
        num_txs = get_count(floodmap, "Tx")
        num_scp = get_count(floodmap, "SCP")

        assert num_txs == total_txs, "validator %s missing TXs, expected %i, actual %i" % (
            validator.name, total_txs, num_txs)
        assert num_scp >= num_scp_msgs_generated, "validator %s missing SCP, expected %i, actual %i" % (
            validator.name, num_scp_msgs_generated, num_scp)

        # Report traffic stats
        validator.report(True)
        validators_total_scp_traffic += validator.scp_unique_count + \
            validator.scp_duplicate_count
        validators_total_tx_traffic += validator.tx_unique_count + \
            validator.tx_duplicate_count
        avg_hops_val.append(
            sum(validator.trace) / len(validator.trace))
        avg_latency_val.append(sum(validator.latency_trace) / len(validator.latency_trace))

    watchers_total_tx_traffic = 0
    watchers_total_scp_traffic = 0
    avg_latency_wat = []
    avg_hops_wat = []

    for watcher in watchers:
        # Ensure all SCP messages made it to all watchers
        # For pull mode, ensure all txns messages made it to all watchers
        floodmap = watcher.get_floodmap()
        num_txs = get_count(floodmap, "Tx")
        num_scp = get_count(floodmap, "SCP")

        assert num_txs == total_txs, "watcher %s missing TXs, expected %i, actual %i" % (
            watcher.name, total_txs, num_txs)
        assert num_scp >= num_scp_msgs_generated, "watcher %s missing SCP, expected %i, actual %i" % (
            watcher.name, num_scp_msgs_generated, num_scp)

        # Report traffic stats
        # TODO: add shortest path
        watcher.report(False)
        watchers_total_scp_traffic += watcher.scp_unique_count + watcher.scp_duplicate_count
        watchers_total_tx_traffic += watcher.tx_unique_count + watcher.tx_duplicate_count
        avg_hops_wat.append(
            sum(watcher.trace) / len(watcher.trace))
        avg_latency_wat.append(sum(watcher.latency_trace) / len(watcher.latency_trace))

    return validators_total_tx_traffic, validators_total_scp_traffic, avg_latency_val, watchers_total_tx_traffic, watchers_total_scp_traffic, avg_latency_wat, avg_hops_val, avg_hops_wat


def generate_graphs_atlas(num_graphs, rand):
    graph_list = nx.generators.graph_atlas_g()
    assert graph_list is not None, "invalid graph list"
    assert len(graph_list) > 0, "no graphs"
    return rand.sample(graph_list, min(num_graphs, len(graph_list)))

def generate_erdos_renyi(num_graphs, num_watchers):
    graph_list = []
    while len(graph_list) < num_graphs:
        # use len(graph_list) as a seed
        graph = nx.erdos_renyi_graph(num_watchers, 2 * np.log(num_watchers) / num_watchers, len(graph_list))
        graph_list.append(graph)
    return graph_list

def report_high_quality_watchers(tx_submitter):
    total = 0

    # Walk the path backwards from the tx submitter, and calculate bandwidth on high-quality peers
    nodes = [tx_submitter]
    
    while True:
        next_nodes = []
        for node in nodes:
            # Record traffic measurements
            total += node.tx_unique_count + node.tx_duplicate_count
            peers = node.get_peers_to_flood_to()

            for p in peers:
                entity = node.peer_quality[p][1]
                if isinstance(entity, Validator):
                    # Tx reached validator, return
                    return total
                next_nodes.append(entity)

        nodes = next_nodes

