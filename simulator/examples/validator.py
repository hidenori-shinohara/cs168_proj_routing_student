import sim.api as api
from sim.basics import *
from collections import defaultdict
from examples import base_node

class Validator (base_node.BaseNode):

  DEFAULT_TIMER_INTERVAL = 3 # Default timer interval.
  NUM_ROUNDS_TO_SIMULATE = 100

  def __init__(self, flood_strategy):
    super(Validator,self).__init__(flood_strategy=flood_strategy)
    self.start_timer()
    self.timer_on = True
    self.rounds_simulated = 0

  def handle_msg(self, packet, in_port):
    if isinstance(packet, api.SCPMessage) and packet.get_packet_key() not in self.get_floodmap():
      # Do something interesting wrt quality
      self.flood(packet, in_port)
    elif isinstance(packet, api.Transaction) and packet.get_packet_key() not in self.get_floodmap():
      # How long did it take for this message to reach us?
      self.latency_trace.append(api.current_time() - packet.timestamp)
      self.trace.append(len(packet.trace))
      # api.simlog.debug("%s Trace %s, %s", self.name, packet, ','.join(x.name for x in packet.trace))
      if self.flood_strategy == base_node.Flooding.SELECTIVE and any(quality > 0 for quality, node in self.peer_quality.values()):
        ports = self.get_peers_to_flood_to()
        peers = self.flood(packet, in_port, ports)
      elif self.flood_strategy == base_node.Flooding.PEER_SAMPLING:
        # TODO: implement
        pass
      else:
        self.flood(packet, in_port)
    elif isinstance(packet, api.FloodAdvert) and packet.get_packet_key() not in self.get_floodmap():
      # How many hops before the advert reached here?
      self.trace.append(len(packet.trace))
      self.demandMissing(packet, in_port)
      api.simlog.debug("{} received {} with adverts = {}".format(self, packet, packet.adverts))
    elif isinstance(packet, api.FloodDemand) and packet.get_packet_key() not in self.get_floodmap():
      # How many hops before the demand reached here?
      self.trace.append(len(packet.trace))
      self.fulfillDemand(packet, in_port)
      api.simlog.debug("{} received demand {} with adverts = {}".format(self, packet, packet.adverts))

  def start_timer (self, interval = None):
    """
    Start the timer that calls handle_timer()
    This should get called in the constructor.  You shouldn't override this.
    """
    if interval is None:
      interval = self.DEFAULT_TIMER_INTERVAL
      if interval is None: return
    api.create_timer(interval, self.handle_timer)

  def handle_timer (self):
    """
    Called periodically to emulate validator emitting an SCP message
    """
    if self.timer_on and self.rounds_simulated < self.NUM_ROUNDS_TO_SIMULATE:
      self.flood(api.SCPMessage(self.rounds_simulated, self))
      self.rounds_simulated += 1

  def set_simulate_round(self, val):
    """
    Called periodically to emulate validator emitting an SCP message
    """
    self.timer_on = val