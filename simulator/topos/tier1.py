import sim
from examples.validator import Validator
from examples.watcher import Watcher
import sim.api as api
import sys
import networkx as nx
from collections import defaultdict
import random

NUM_TXS_TO_SUBMIT = 10
NUM_VALIDATORS_TIER_1 = 4

def topology_generator_helper(num_validators, selective_flooding):

  graph_list = nx.generators.graph_atlas_g()
  assert graph_list is not None, "invalid graph list"
  assert len(graph_list) > 0, "no graphs"

  # Map watcher topology
  # every 30th graph
  for graph in graph_list[100::30]:
  # for graph in graph_list[100:]:


    # Setup validators first
    validators = []
    for i in range(num_validators):
      s = Validator.create('val' + str(i), selective_flooding)
      validators.append(s)

    # Connect validators fully regardless of the watcher topology
    visited = []
    for v in validators:
      for v_inner in validators:
        if v == v_inner or v_inner in visited:
          continue
        else:
          v.linkTo(v_inner)
      visited.append(v)
    
    watchers = defaultdict(Watcher)
    for i, node in enumerate(graph.nodes()):
      s = Watcher.create('wat' + str(i), selective_flooding)
      watchers[i] = s

    # Now connect
    for edge in graph.edges.data():
      wat1 = watchers[edge[0]]
      wat2 = watchers[edge[1]]
      wat1.linkTo(wat2)

    # Finally connect to validators
    watchers_lst = [item[1] for item in watchers.items()]
    if watchers_lst:
      # Connect each watcher to a validator if the graph is disconnected
      if not nx.is_connected(graph):
        for i in range(len(watchers_lst)):
          # TODO: right now we only connect to 1 validator, can probably do something more interesting here
          watchers_lst[i].linkTo(validators[0])
      # Otherwise, connect one watcher to one validator
      else:
          watchers_lst[0].linkTo(validators[0])

    yield validators, watchers_lst

def launch (switch_type = sim.config.default_switch_type, host_type = sim.config.default_host_type, selective_flooding = sim.config.selective_flooding):
  """
  Generates several random topologies on watchers connected a fully-connected Tier1 structure. 
  """

  # add churn? random nodes disconnect and connect?

  # for now, count number of hops (use trace)
  # in the future, handle weighted links 

  assert type(selective_flooding) == bool, "type is wrong"

  def test_tasklet(selective_flooding, max_num_runs=100000):

    # Wait until the simulator starts
    yield 5

    run_number = 1
    run_tx_data = []
    run_scp_data = []

    # try:
    if True:
      for validators, watchers in topology_generator_helper(NUM_VALIDATORS_TIER_1, selective_flooding):

        api.simlog.info("========== Run %i BEGIN, graph size %i, selective flooding enabled %s ==========", run_number, len(validators) + len(watchers), selective_flooding)

        # Submit txs from watcher
        w = validators[0]
        if watchers:
          # w = random.choice(watchers)
          w = watchers[0]

        for i in range(NUM_TXS_TO_SUBMIT):
          w.submit_tx()
          yield 1

        # stop timers to get accurate counts
        for v in validators:
          v.stop_timer()

        # make sure txs reach everyone
        yield 10

        # all flood traffic made it to all nodes
        get_count = lambda floodmap, type : len([item for item in floodmap if type in item])

        floodmap = validators[0].get_floodmap()
        floodmap_size = get_count(floodmap, "Tx")
        assert floodmap_size == NUM_TXS_TO_SUBMIT, "validator missing messages, expected %i, actual %i" % (NUM_TXS_TO_SUBMIT, floodmap_size)

        validators_total_tx_traffic = 0
        validators_total_scp_traffic = 0

        for validator in validators:
          # Ensure all Txs made it
          other_floodmap = validator.get_floodmap()
          count = get_count(floodmap, "Tx")
          assert count == floodmap_size, "%s: validator missing messages, expected %i, actual %i" % (self.name, floodmap_size, count)

          # Ensure total floodmap size is right
          assert len(floodmap) == len(other_floodmap), "%s has different size floodmap %i, expected %i" % (self.name, len(other_floodmap), len(floodmap))

          # Report traffic stats
          validator.report(True)
          validators_total_scp_traffic += validator.scp_unique_count + validator.scp_duplicate_count
          validators_total_tx_traffic += validator.tx_unique_count + validator.tx_duplicate_count

        watchers_total_tx_traffic = 0
        watchers_total_scp_traffic = 0   

        for watcher in watchers:
          # Ensure all SCP messages made it to all watchers
          assert get_count(watcher.get_floodmap(), "SCP") == get_count(validators[0].get_floodmap(), "SCP"), "watcher missing SCP messages"

          # Report traffic stats
          # TODO: add shortest path
          watcher.report(False)
          watchers_total_scp_traffic += watcher.scp_unique_count + watcher.scp_duplicate_count
          watchers_total_tx_traffic += watcher.tx_unique_count + watcher.tx_duplicate_count

        api.simlog.info("TOTAL Stats: validators %i SCP traffic, %i TX traffic", validators_total_scp_traffic, validators_total_tx_traffic)
        api.simlog.info("TOTAL Stats: watchers %i SCP traffic, %i TX traffic", watchers_total_scp_traffic, watchers_total_tx_traffic)

        # Now verify quality, validator quality should be greater with the current definition
        # TODO: map quality function with some basic asserts
        # w0 should have the best quality out of all watchers
        # TODO: still need to map ports to identity
        # Inspect quality of a validator versus 

        # watchers closest to validators should have the best peer quality 

        # Cleanup before the next run
        for w in watchers:
          w.remove()
        for v in validators:
          v.remove()

        api.simlog.info("==================== Run %i DONE ====================", run_number)

        # just count watchers since we haven't implemented flooding policies on validators
        run_tx_data.append(watchers_total_tx_traffic)
        run_scp_data.append(watchers_total_scp_traffic)

        if run_number == max_num_runs:
          break

        run_number += 1

      api.simlog.info("Average TX traffic per run: %.2f", sum(run_tx_data) / len(run_tx_data))
      api.simlog.info("Average SCP traffic per run: %.2f", sum(run_scp_data) / len(run_scp_data))

      api.simlog.info("\tSUCCESS!")
    # except Exception as e:
    #     api.simlog.error("Exception occurred: %s" % e)
    #     traceback.print_exc()
    # finally:
    #     sys.exit()

  api.run_tasklet(test_tasklet, selective_flooding, 10)




