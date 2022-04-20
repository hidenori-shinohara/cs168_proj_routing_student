import sim.api as api
from sim.basics import *
from collections import defaultdict
import operator
from examples import base_node
import math
import numpy as np
from scipy.cluster.vq import vq, kmeans, whiten

class Watcher (base_node.BaseNode):

  NUM_CLUSTERS=3

  def get_peers_to_flood_to(self):
    # api.simlog.debug("%s Peer quality: %s", self.name, self.peer_quality)
    
    peers = list(self.peer_quality.items())

    if len(peers) == 1:
      return [port for port, qual in peers]

    quality_lst = [qual[0] for port, qual in peers]

    arr = np.array(quality_lst, dtype=np.float64)
    arr = whiten(arr)
    normalized_centroids, distortion = kmeans(arr, min(len(quality_lst), self.NUM_CLUSTERS))

    clusters = defaultdict(list)
    for point in arr:
      best_centroid = normalized_centroids[0]
      for c in normalized_centroids[1:]:
        if abs(point - c) < abs(point - best_centroid):
          best_centroid = c
      clusters[best_centroid].append(point)

    # Performance computing peer quality every time is expensive. In reality, we probably want this 
    # in the background thread, and updated every few minutes

    # Now map back to points
    best_cluster = clusters[max(normalized_centroids)]

    ports = []
    for item in best_cluster:
      idx = np.where(arr == item)[0][0]
      ports.append(peers[idx][0])

    # api.simlog.debug("Flood to ports: %s", ports)

    return ports

  def handle_msg(self, packet, in_port):

    # api.simlog.debug("%s recv msg %s on port %i", self.name, packet, in_port)

    if isinstance(packet, api.Transaction):

      # Forward to nodes based on quality
      if any(quality > 0 for quality, node in self.peer_quality.values()):
        if self.flood_strategy == base_node.Flooding.SELECTIVE:
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
        # How many hops before unique SCP message reached here?
        self.trace.append(len(packet.trace))

      # Flood SCP message to everyone
      self.flood(packet, in_port)
    
    elif isinstance(packet, api.FloodAdvert) and packet.get_packet_key() not in self.get_floodmap():
      # How many hops before the advert reached here?
      self.trace.append(len(packet.trace))
#      self.demandMissing(packet, in_port)
    elif isinstance(packet, api.FloodDemand) and packet.get_packet_key() not in self.get_floodmap():
      # How many hops before the demand reached here?
      self.trace.append(len(packet.trace))
      self.fulfillDemand(packet, in_port)

    else:
      pass
      # assert False, "unknown message type"

