import sim.api as api
from sim.basics import *
from collections import defaultdict
import operator
from enum import Enum

seq = 0

class Flooding(Enum):
  # basic all-to-all flooding
  FLOOD_ALL=1
  # selective flooding based on quality
  SELECTIVE=2
  # flood to all, but constantly disconnect low-quality peers
  PEER_SAMPLING=3

class BaseNode (api.Entity):
  # better to use clusters
  PEER_QUALITY_PERCENT_FLOOD = 50

  def __init__(self, flood_strategy):
    # We need to initialize everyone
    # map port -> [quality, peer identity]
    # TODO: this base class should not know anything about ports, rely only on identity
    self.peer_quality = defaultdict(tuple)

    # We save trace of all unique traffic we received
    self.trace = []

    self.tx_duplicate_count = 0
    self.tx_unique_count = 0

    self.scp_duplicate_count = 0
    self.scp_unique_count = 0

    self.flood_strategy = flood_strategy
  
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
        else:
          self.scp_unique_count += 1  
    
    increase_count(packet)

    # Fill quality if needed
    # if not self.peer_quality:
    #   # Place all peers in the quality map
    #   for self_name, self_port, peer_name, peer_port in self.get_ports():
    #       self.peer_quality[self_port] = [0, self.get_peer_identity(self_port)]

    # Increase quality
    if isinstance(packet, api.SCPMessage):
      if packet.get_packet_key() not in self.get_floodmap():
        self.peer_quality[in_port][0] += 1

    # Handle message
    self.handle_msg(packet, in_port)

  def submit_tx(self):
    global seq
    self.handle_rx(api.Transaction(seq), None)
    seq += 1

  def report(self, expect_txs=False):
    # First, report hop count
    # I wonder if calculating shortest paths is slow, we'd have to evaluate all latencies 
    if self.trace:  
      api.simlog.info("%s Average hop count: %.2f", self.name, sum(self.trace) / len(self.trace))

    # Report bandwidth utilized network-wide (unique vs duplicate traffic)
    if expect_txs:
      assert self.tx_unique_count > 0, "no unique transactions on %s" % self.name
      
    if self.tx_unique_count > 0:
      api.simlog.info("%s Duplicate TX traffic ratio to total traffic: %.2f (dup: %i, unique: %i)", self.name, self.tx_duplicate_count / (self.tx_unique_count + self.tx_duplicate_count), self.tx_duplicate_count, self.tx_unique_count)
        
    assert self.scp_unique_count > 0, "No unique SCP traffic recorded"
    api.simlog.info("%s Duplicate SCP traffic ratio to total traffic: %.2f (dup: %i, unique: %i)", self.name, self.scp_duplicate_count / (self.scp_unique_count + self.scp_duplicate_count), self.scp_duplicate_count, self.scp_unique_count)
