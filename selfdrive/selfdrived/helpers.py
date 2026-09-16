import math
from enum import StrEnum, auto

from cereal import car, log, messaging
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.locationd.helpers import Pose
from opendbc.car import ACCELERATION_DUE_TO_GRAVITY
from opendbc.car.lateral import ISO_LATERAL_ACCEL
from opendbc.car.interfaces import ACCEL_MIN, ACCEL_MAX
from openpilot.selfdrive.selfdrived.events import Events, ET, EVENTS

MIN_EXCESSIVE_ACTUATION_COUNT = int(0.25 / DT_CTRL)
MIN_LATERAL_ENGAGE_BUFFER = int(1 / DT_CTRL)

GearShifter = car.CarState.GearShifter
NON_DRIVING_GEARS = (GearShifter.unknown, GearShifter.park, GearShifter.neutral, GearShifter.reverse)
EventName = log.OnroadEvent.EventName


class ExcessiveActuationType(StrEnum):
  LONGITUDINAL = auto()
  LATERAL = auto()


class ExcessiveActuationCheck:
  def __init__(self):
    self._excessive_counter = 0
    self._engaged_counter = 0

  def update(self, sm: messaging.SubMaster, CS: car.CarState, calibrated_pose: Pose) -> ExcessiveActuationType | None:
    # CS.aEgo can be noisy to bumps in the road, transitioning from standstill, losing traction, etc.
    # longitudinal
    accel_calibrated = calibrated_pose.acceleration.x
    excessive_long_actuation = sm['carControl'].longActive and (accel_calibrated > ACCEL_MAX * 2 or accel_calibrated < ACCEL_MIN * 2)

    # lateral
    yaw_rate = calibrated_pose.angular_velocity.yaw
    roll = sm['liveParameters'].roll
    roll_compensated_lateral_accel = (CS.vEgo * yaw_rate) - (math.sin(roll) * ACCELERATION_DUE_TO_GRAVITY)

    # Prevent false positives after overriding
    excessive_lat_actuation = False
    self._engaged_counter = self._engaged_counter + 1 if sm['carControl'].latActive and not CS.steeringPressed else 0
    if self._engaged_counter > MIN_LATERAL_ENGAGE_BUFFER:
      if abs(roll_compensated_lateral_accel) > ISO_LATERAL_ACCEL * 2:
        excessive_lat_actuation = True

    # livePose acceleration can be noisy due to bad mounting or aliased livePose measurements
    livepose_valid = abs(CS.aEgo - accel_calibrated) < 2
    self._excessive_counter = self._excessive_counter + 1 if livepose_valid and (excessive_long_actuation or excessive_lat_actuation) else 0

    excessive_type = None
    if self._excessive_counter > MIN_EXCESSIVE_ACTUATION_COUNT:
      if excessive_long_actuation:
        excessive_type = ExcessiveActuationType.LONGITUDINAL
      else:
        excessive_type = ExcessiveActuationType.LATERAL

    return excessive_type


class AlwaysOnLateralGate:
  """Always On Lateral arming, mirroring FrogPilot's frogpilot_card gating: cruise main on, a driving gear,
  any calibration progress, no immediate-disable event (speedTooLow excepted), and not braking below the
  pause speed unless stopped. Steer faults are handled downstream in controlsd's latActive, as in FrogPilot."""

  @staticmethod
  def update(CS: car.CarState, events: Events, cal_perc: int, pause_speed: float) -> bool:
    if not (CS.canValid and CS.cruiseState.available):
      return False

    if CS.gearShifter in NON_DRIVING_GEARS:
      return False

    if cal_perc < 1:
      return False

    if any(ET.IMMEDIATE_DISABLE in EVENTS.get(e, {}) and e != EventName.speedTooLow for e in events.names):
      return False

    if CS.brakePressed and CS.vEgo < pause_speed and not CS.standstill:
      return False

    return True
