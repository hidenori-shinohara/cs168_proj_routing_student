import sim.api as api
from sim.basics import *
from collections import defaultdict
from examples import base_node

class Validator (base_node.BaseNode):

  DEFAULT_TIMER_INTERVAL = 1 # Default timer interval.
  NUM_ROUNDS_TO_SIMULATE = 2

  def __init__(self, selective_flooding):
    super(Validator,self).__init__(selective_flooding=selective_flooding)
    self.start_timer()
    self.timer_on = True
    self.rounds_simulated = 0

  def handle_msg(self, packet, in_port):
    if isinstance(packet, api.SCPMessage) and packet.get_packet_key() not in self.get_floodmap():
      # Do something interesting wrt quality
      pass
    elif isinstance(packet, api.Transaction) and packet.get_packet_key() not in self.get_floodmap():
      # How many hops before transaction reached here?
      self.trace.append(len(packet.trace))
      # api.simlog.debug("%s Trace %s, %s", self.name, packet, ','.join(x.name for x in packet.trace))

    self.flood(packet, in_port)

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
      self.flood(api.SCPMessage(None))
      self.rounds_simulated += 1

  def stop_timer (self):
    """
    Called periodically to emulate validator emitting an SCP message
    """
    self.timer_on = False