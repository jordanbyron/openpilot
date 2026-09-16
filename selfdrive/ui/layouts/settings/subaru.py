"""Visibility gating and unit conversion for the fork's Subaru toggles, shared by the 3X and comma 4 settings UIs."""
from opendbc.car.subaru.values import SubaruFlags
from openpilot.common.constants import CV

AOL_PAUSE_SPEEDS_MPH = [0, 5, 10, 15]


def nearest_pause_speed_index(stored_ms: float) -> int:
  speeds = [s * CV.MPH_TO_MS for s in AOL_PAUSE_SPEEDS_MPH]
  return min(range(len(speeds)), key=lambda i: abs(speeds[i] - stored_ms))


def pause_speed_ms(index: int) -> float:
  return AOL_PAUSE_SPEEDS_MPH[index] * CV.MPH_TO_MS


def aol_available(CP) -> bool:
  # panda only honors ALT_EXP_ALWAYS_ON_LATERAL on Subaru, so the toggle is a no-op anywhere else
  return CP is not None and CP.brand == "subaru"


def impreza_torque_available(CP) -> bool:
  return CP is not None and CP.carFingerprint == "SUBARU_IMPREZA"


def sng_available(CP) -> bool:
  # mirrors CarInterface.enable_stop_and_go exactly, so the toggle is never offered where it is a no-op
  return CP is not None and CP.brand == "subaru" and \
         not CP.openpilotLongitudinalControl and \
         not (CP.flags & (SubaruFlags.GLOBAL_GEN2 | SubaruFlags.HYBRID |
                          SubaruFlags.PREGLOBAL | SubaruFlags.LKAS_ANGLE))
