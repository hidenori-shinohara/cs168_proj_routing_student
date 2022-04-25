import sim.api as api
from sim.basics import *
from collections import defaultdict
import operator
from examples import base_node
import math
import numpy as np
from scipy.cluster.vq import vq, kmeans, whiten

class Watcher (base_node.BaseNode):



  def handle_msg(self, packet, in_port):

    # api.simlog.debug("%s recv msg %s on port %i", self.name, packet, in_port)

    if isinstance(packet, api.Transaction):

      # Forward to nodes based on quality
      if any(quality > 0 for quality, node in self.peer_quality.values()):
        if self.flood_strategy == base_node.Flooding.SELECTIVE:
          # ports = self.get_peers_to_flood_to(redundancy=3)
          ports = self.get_peers_to_flood_to()

          peers = self.flood(packet, in_port, ports)
        elif self.flood_strategy == base_node.Flooding.PEER_SAMPLING:
          # TODO: implement
          pass
        else:
          self.flood(packet, in_port)

      else:
        peers = self.flood(packet, in_port)

      # api.simlog.debug("%s Flood %s to %s", self.name, packet, peers)

    elif isinstance(packet, api.SCPMessage):
      # api.simlog.debug("%s Trace %s, %s", self.name, packet, ','.join(x.name for x in packet.trace))
      if packet.get_packet_key() not in self.get_floodmap():
        # How long did it take for this message to reach us?
        self.latency_trace.append(api.current_time() - packet.timestamp)
        self.trace.append(len(packet.trace))

      # Flood SCP message to everyone
      self.flood(packet, in_port)
    
    else:
      assert False, "unknown message type"

