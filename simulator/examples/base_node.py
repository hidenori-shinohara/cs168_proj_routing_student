import sim.api as api
from sim.basics import *
from collections import defaultdict
import operator
from enum import Enum
import math
import numpy as np
from scipy.cluster.vq import vq, kmeans, whiten

seq = 0
NUM_CLUSTERS=3

class Flooding(Enum):
  # basic all-to-all flooding
  FLOOD_ALL=1
  # selective flooding based on quality
  SELECTIVE=2
  # flood to all, but constantly disconnect low-quality peers
  PEER_SAMPLING=3

class BaseNode (api.Entity):

  def __init__(self, flood_strategy):
    # We need to initialize everyone
    # map port -> [quality, peer identity]
    # TODO: this base class should not know anything about ports, rely only on identity
    # TODO: peer quality is too harsh right now, give peer partial credit if duplicate arrives within a small grace period from unique packet
    # TODO: link goes down, send poison -> can also be solved with quality decay
    self.peer_quality = defaultdict(tuple)

    # We save trace of all unique traffic we received
    # instead of hops, get total latency
    self.latency_trace = []
    self.trace = []

    self.tx_duplicate_count = 0
    self.tx_unique_count = 0

    self.scp_duplicate_count = 0
    self.scp_unique_count = 0

    self.flood_strategy = flood_strategy

  def get_peers_to_flood_to(self, redundancy=None):
    # api.simlog.debug("%s Peer quality: %s", self.name, self.peer_quality)
    
    peers = list(self.peer_quality.items())

    if len(peers) == 1:
      return [port for port, qual in peers]

    quality_lst = [qual[0] for port, qual in peers]

    arr = np.array(quality_lst, dtype=np.float64)
    arr = whiten(arr)
    normalized_centroids, distortion = kmeans(arr, min(len(quality_lst), NUM_CLUSTERS))

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
    best_cluster = set(clusters[max(normalized_centroids)])
  
    ports = []
    for item in best_cluster:
      for idx in np.where(arr == item)[0]:
        if redundancy is None or len(ports) < redundancy:
          ports.append(peers[idx][0])
        else:
          break

    assert len(ports) == len(set(ports)), "duplicate ports %s" % ports
    #api.simlog.debug("Flood to ports: %s", ports)

    return ports
  
  def handle_link_down (self, port):
    """
    Called by the framework when a link attached to this Entity goes down.

    The port number used by the link is passed in.
    """

    # TODO: can we do something better? Right now peers do not regroup very well in terms of quality
    self.peer_quality.pop(port, None)
    # Reset quality to 0
    for qual in self.peer_quality:
      self.peer_quality[qual][0] = 0

    # Possibly connect to more peers

  def handle_link_up (self, port, latency):
    """
    Called by the framework when a link attached to this Entity goes up.

    The port attached to the link and the link latency are passed in.
    You may want to override it.
    """
    self.peer_quality[port] = [0, self.get_peer_identity(port)]

  def handle_rx (self, packet, in_port):
    # Record duplicate traffic
    def increase_count(packet):
      if packet.get_packet_key() in self.get_floodmap():
        if isinstance(packet, api.Transaction):
          self.tx_duplicate_count += 1
        else:
          self.scp_duplicate_count += 1
      else:
        if isinstance(packet, api.Transaction):
          self.tx_unique_count += 1  
        if isinstance(packet, api.SCPMessage):
          self.scp_unique_count += 1  
    
    increase_count(packet)

    # Increase quality
    if isinstance(packet, api.SCPMessage):
      if packet.get_packet_key() not in self.get_floodmap():
        self.peer_quality[in_port][0] += 2
      # Give peer partial credit if the message showed up after a small delay
      elif (api.current_time() - self.get_floodmap()[packet.get_packet_key()][1]) <= 0.5:
        self.peer_quality[in_port][0] += 1

    # Handle message
    self.handle_msg(packet, in_port)

  def submit_tx(self):
    global seq
    self.handle_rx(api.Transaction(seq,self), None)
    seq += 1

  def report(self, expect_txs=False):
    # First, report hop count
    # I wonder if calculating shortest paths is slow, we'd have to evaluate all latencies 
    if self.latency_trace:  
      api.simlog.info("%s Average hops: %.2f", self.name, sum(self.trace) / len(self.trace))

    # Report bandwidth utilized network-wide (unique vs duplicate traffic)
    if expect_txs:
      assert self.tx_unique_count > 0, "no unique transactions on %s" % self.name
      
    if self.tx_unique_count > 0:
      api.simlog.info("%s Duplicate TX traffic ratio to total traffic: %.2f (dup: %i, unique: %i)", self.name, self.tx_duplicate_count / (self.tx_unique_count + self.tx_duplicate_count), self.tx_duplicate_count, self.tx_unique_count)
        
    assert self.scp_unique_count > 0, "No unique SCP traffic recorded"
    api.simlog.info("%s Duplicate SCP traffic ratio to total traffic: %.2f (dup: %i, unique: %i)", self.name, self.scp_duplicate_count / (self.scp_unique_count + self.scp_duplicate_count), self.scp_duplicate_count, self.scp_unique_count)
