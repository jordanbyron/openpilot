import pytest

from cereal import car, log
from openpilot.selfdrive.selfdrived.events import Events
from openpilot.selfdrive.selfdrived.helpers import AlwaysOnLateralGate

EventName = log.OnroadEvent.EventName
GearShifter = car.CarState.GearShifter

# FrogPilot parity: only immediate-disable events cut always-on lateral (speedTooLow excepted).
# Soft-disable events do not; those are left to the engaged state machine, as in FrogPilot.
SOFT_DISABLE_EVENTS = (EventName.cameraMalfunction, EventName.processNotRunning, EventName.selfdrivedLagging,
                       EventName.modeldLagging, EventName.excessiveActuation, EventName.steerTempUnavailable)
IMMEDIATE_DISABLE_EVENTS = (EventName.controlsMismatch, EventName.canError, EventName.steerUnavailable)
USER_DISABLE_AND_NO_ENTRY_ONLY_EVENTS = (EventName.pedalPressed, EventName.buttonEnable)


def make_CS(**kwargs):
  CS = car.CarState.new_message()
  CS.canValid = True
  CS.cruiseState.available = True
  CS.gearShifter = GearShifter.drive
  CS.vEgo = 20.0
  for k, v in kwargs.items():
    if "." in k:
      head, tail = k.split(".")
      setattr(getattr(CS, head), tail, v)
    else:
      setattr(CS, k, v)
  return CS


class TestAlwaysOnLateralGate:
  def setup_method(self):
    self.gate = AlwaysOnLateralGate()
    self.events = Events()

  def _update(self, CS=None, cal_perc=100, pause_speed=0.0):
    CS = make_CS() if CS is None else CS
    return self.gate.update(CS, self.events, cal_perc, pause_speed)

  def test_allowed_when_armed_and_healthy(self):
    assert self._update()

  def test_allowed_immediately_no_cooldown(self):
    # FrogPilot has no warm-up: the first healthy frame arms it
    assert self._update()

  @pytest.mark.parametrize("kwargs", [
    {"canValid": False},
    {"cruiseState.available": False},
  ])
  def test_blocks_on_unavailable_car_state(self, kwargs):
    assert not self._update(make_CS(**kwargs))

  @pytest.mark.parametrize("gear", [GearShifter.unknown, GearShifter.park, GearShifter.neutral, GearShifter.reverse])
  def test_blocks_in_non_driving_gears(self, gear):
    assert not self._update(make_CS(gearShifter=gear))

  @pytest.mark.parametrize("gear", [GearShifter.drive, GearShifter.low])
  def test_allows_in_driving_gears(self, gear):
    assert self._update(make_CS(gearShifter=gear))

  def test_calibration_threshold_is_any_progress(self):
    # FrogPilot: liveCalibration.calPerc >= 1, so it steers while still calibrating
    assert not self._update(cal_perc=0)
    assert self._update(cal_perc=1)
    assert self._update(cal_perc=100)

  def test_blocks_on_brake_below_pause_speed(self):
    assert not self._update(make_CS(brakePressed=True, vEgo=5.0), pause_speed=10.0)

  def test_allows_on_brake_above_pause_speed(self):
    assert self._update(make_CS(brakePressed=True, vEgo=15.0), pause_speed=10.0)

  def test_allows_on_brake_at_standstill(self):
    assert self._update(make_CS(brakePressed=True, standstill=True, vEgo=0.0), pause_speed=10.0)

  def test_default_pause_speed_never_pauses(self):
    assert self._update(make_CS(brakePressed=True, vEgo=0.1))

  @pytest.mark.parametrize("event", IMMEDIATE_DISABLE_EVENTS)
  def test_blocks_on_immediate_disable_events(self, event):
    self.events.add(event)
    assert not self._update()
    self.events.clear()
    assert self._update()

  def test_speed_too_low_is_excepted(self):
    self.events.add(EventName.speedTooLow)
    assert self._update()

  @pytest.mark.parametrize("event", SOFT_DISABLE_EVENTS + USER_DISABLE_AND_NO_ENTRY_ONLY_EVENTS)
  def test_survives_soft_disable_user_disable_and_no_entry_events(self, event):
    self.events.add(event)
    assert self._update()

  @pytest.mark.parametrize("fault", ["steerFaultTemporary", "steerFaultPermanent"])
  def test_steer_faults_are_not_gated_here(self, fault):
    # as in FrogPilot, latActive in controlsd drops on a steer fault and returns on the next clean frame
    assert self._update(make_CS(**{fault: True}))
