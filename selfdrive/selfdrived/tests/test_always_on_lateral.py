import pytest

from cereal import car, log
from openpilot.selfdrive.selfdrived.events import Events
from openpilot.selfdrive.selfdrived.helpers import AlwaysOnLateralGate, AOL_STEER_FAULT_COOLDOWN

EventName = log.OnroadEvent.EventName
GearShifter = car.CarState.GearShifter
CALIBRATED = log.LiveCalibrationData.Status.calibrated

SOFT_DISABLE_EVENTS = (EventName.cameraMalfunction, EventName.processNotRunning, EventName.selfdrivedLagging,
                       EventName.modeldLagging, EventName.excessiveActuation, EventName.steerTempUnavailable)
IMMEDIATE_DISABLE_EVENTS = (EventName.controlsMismatch,)
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

  def _step_past_steer_fault_cooldown(self, CS=None, cal_status=CALIBRATED, pause_speed=0.0):
    CS = make_CS() if CS is None else CS
    for _ in range(AOL_STEER_FAULT_COOLDOWN):
      self.gate.update(CS, self.events, cal_status, pause_speed)

  def _update(self, CS=None, cal_status=CALIBRATED, pause_speed=0.0):
    CS = make_CS() if CS is None else CS
    return self.gate.update(CS, self.events, cal_status, pause_speed)

  def test_allowed_when_armed_and_healthy(self):
    self._step_past_steer_fault_cooldown()
    assert self._update()

  def test_not_allowed_before_cooldown(self):
    for _ in range(AOL_STEER_FAULT_COOLDOWN - 1):
      assert not self._update()
    assert self._update()

  @pytest.mark.parametrize("kwargs", [
    {"canValid": False},
    {"cruiseState.available": False},
  ])
  def test_blocks_on_unavailable_car_state(self, kwargs):
    self._step_past_steer_fault_cooldown()
    assert not self._update(make_CS(**kwargs))

  @pytest.mark.parametrize("gear", [GearShifter.unknown, GearShifter.park, GearShifter.neutral, GearShifter.reverse])
  def test_blocks_in_non_driving_gears(self, gear):
    self._step_past_steer_fault_cooldown()
    assert not self._update(make_CS(gearShifter=gear))

  @pytest.mark.parametrize("gear", [GearShifter.drive, GearShifter.low])
  def test_allows_in_driving_gears(self, gear):
    self._step_past_steer_fault_cooldown()
    assert self._update(make_CS(gearShifter=gear))

  @pytest.mark.parametrize("status", [s for s in log.LiveCalibrationData.Status.schema.enumerants.values() if s != CALIBRATED])
  def test_blocks_while_not_calibrated(self, status):
    self._step_past_steer_fault_cooldown()
    assert not self._update(cal_status=status)

  def test_blocks_on_brake_below_pause_speed(self):
    self._step_past_steer_fault_cooldown(pause_speed=10.0)
    assert not self._update(make_CS(brakePressed=True, vEgo=5.0), pause_speed=10.0)

  def test_allows_on_brake_above_pause_speed(self):
    self._step_past_steer_fault_cooldown(pause_speed=10.0)
    assert self._update(make_CS(brakePressed=True, vEgo=15.0), pause_speed=10.0)

  def test_allows_on_brake_at_standstill(self):
    self._step_past_steer_fault_cooldown(pause_speed=10.0)
    assert self._update(make_CS(brakePressed=True, standstill=True, vEgo=0.0), pause_speed=10.0)

  def test_default_pause_speed_never_pauses(self):
    self._step_past_steer_fault_cooldown()
    assert self._update(make_CS(brakePressed=True, vEgo=0.1))

  @pytest.mark.parametrize("event", SOFT_DISABLE_EVENTS + IMMEDIATE_DISABLE_EVENTS)
  def test_blocks_on_disable_events(self, event):
    self._step_past_steer_fault_cooldown()
    self.events.add(event)
    assert not self._update()

    self.events.clear()
    assert self._update()

  @pytest.mark.parametrize("event", USER_DISABLE_AND_NO_ENTRY_ONLY_EVENTS)
  def test_survives_user_disable_and_no_entry_events(self, event):
    self._step_past_steer_fault_cooldown()
    self.events.add(event)
    assert self._update()

  @pytest.mark.parametrize("fault", ["steerFaultTemporary", "steerFaultPermanent"])
  def test_steer_fault_restarts_cooldown(self, fault):
    self._step_past_steer_fault_cooldown()
    assert not self._update(make_CS(**{fault: True}))

    for _ in range(AOL_STEER_FAULT_COOLDOWN - 1):
      assert not self._update()
    assert self._update()
