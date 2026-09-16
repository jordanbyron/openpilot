import pytest

from opendbc.car import gen_empty_fingerprint
from opendbc.car.subaru.interface import CarInterface
from opendbc.car.subaru.values import CAR, SubaruFlags, SubaruSafetyFlags
from opendbc.car.honda.interface import CarInterface as HondaCarInterface
from opendbc.car.honda.values import CAR as HONDA_CAR
from opendbc.safety import ALTERNATIVE_EXPERIENCE
from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.selfdrive.ui.layouts.settings.subaru import AOL_PAUSE_SPEEDS_MPH, nearest_pause_speed_index, \
                                                           pause_speed_ms, aol_available, impreza_torque_available, sng_available
from openpilot.selfdrive.car.tests.test_always_on_lateral_param import apply_card_init_gate as apply_aol_gate
from openpilot.selfdrive.car.tests.test_subaru_sng import apply_card_init_gate as apply_sng_gate

TOGGLES = ("AlwaysOnLateral", "SubaruImprezaTorque", "SubaruSNG")


@pytest.fixture
def params():
  p = Params()
  for toggle in TOGGLES:
    p.remove(toggle)
  yield p
  for toggle in TOGGLES:
    p.remove(toggle)


def build_cp(params):
  """Reproduce Car.__init__ in card.py, in its order, for an Impreza."""
  CP = CarInterface.get_params(CAR.SUBARU_IMPREZA, gen_empty_fingerprint(), [], alpha_long=False,
                               is_release=False, docs=False,
                               increased_steer_torque=params.get_bool("SubaruImprezaTorque"))
  CP.alternativeExperience = 0
  CP.passive = False
  apply_aol_gate(params, CP)
  apply_sng_gate(params, CP)
  return CP


def test_all_toggles_off_is_byte_identical_to_stock(params):
  CP = build_cp(params)

  assert CP.safetyConfigs[0].safetyParam == 0
  assert CP.alternativeExperience == 0
  assert CP.flags & (SubaruFlags.IMPREZA_TORQUE | SubaruFlags.SNG) == 0


def test_all_toggles_on_matches_panda(params):
  for toggle in TOGGLES:
    params.put_bool(toggle, True, block=True)
  CP = build_cp(params)

  # the pair selfdrived.py compares against pandaStates for the whole ignition cycle
  assert CP.safetyConfigs[0].safetyParam == SubaruSafetyFlags.IMPREZA_TORQUE | SubaruSafetyFlags.SNG == 24
  assert CP.alternativeExperience == ALTERNATIVE_EXPERIENCE.ALWAYS_ON_LATERAL == 32
  assert CP.flags & SubaruFlags.IMPREZA_TORQUE
  assert CP.flags & SubaruFlags.SNG


def test_torque_and_sng_claim_different_bits():
  # both are live at once on a Crosstrek, so an alias would silently enable the other feature
  assert SubaruSafetyFlags.IMPREZA_TORQUE & SubaruSafetyFlags.SNG == 0
  assert SubaruFlags.IMPREZA_TORQUE & SubaruFlags.SNG == 0


class TestToggleVisibility:
  """The 3X and comma 4 settings UIs share these predicates, so one set of cases covers both."""

  def test_hidden_with_no_car(self):
    assert not aol_available(None)
    assert not impreza_torque_available(None)
    assert not sng_available(None)

  def test_shown_on_impreza(self, params):
    CP = build_cp(params)
    assert aol_available(CP)
    assert impreza_torque_available(CP)
    assert sng_available(CP)

  def test_hidden_on_non_subaru(self):
    CP = HondaCarInterface.get_params(HONDA_CAR.HONDA_CIVIC, gen_empty_fingerprint(), [], alpha_long=False,
                                      is_release=False, docs=False)
    assert not aol_available(CP)
    assert not impreza_torque_available(CP)
    assert not sng_available(CP)

  @pytest.mark.parametrize("platform", [c for c in CAR if c != CAR.SUBARU_IMPREZA])
  def test_impreza_torque_is_impreza_only(self, platform):
    CP = CarInterface.get_params(platform, gen_empty_fingerprint(), [], alpha_long=False, is_release=False, docs=False)
    assert not impreza_torque_available(CP)

  @pytest.mark.parametrize("platform", list(CAR))
  def test_sng_matches_car_interface_eligibility(self, platform):
    CP = CarInterface.get_params(platform, gen_empty_fingerprint(), [], alpha_long=False, is_release=False, docs=False)
    ineligible = CP.openpilotLongitudinalControl or bool(CP.flags & (SubaruFlags.GLOBAL_GEN2 | SubaruFlags.HYBRID |
                                                                     SubaruFlags.PREGLOBAL | SubaruFlags.LKAS_ANGLE))
    assert sng_available(CP) is not ineligible


class TestPauseSpeedPresets:
  def test_presets_round_trip(self):
    for index in range(len(AOL_PAUSE_SPEEDS_MPH)):
      assert nearest_pause_speed_index(pause_speed_ms(index)) == index

  def test_off_is_zero(self):
    assert pause_speed_ms(0) == 0.0

  @pytest.mark.parametrize("mph, expected_index", [(0, 0), (2, 0), (3, 1), (7, 1), (8, 2), (12, 2), (13, 3), (40, 3)])
  def test_stored_speed_snaps_to_nearest_preset(self, mph, expected_index):
    assert nearest_pause_speed_index(mph * CV.MPH_TO_MS) == expected_index

  def test_unset_param_default_is_off(self):
    assert nearest_pause_speed_index(Params().get("AlwaysOnLateralPauseSpeed", return_default=True)) == 0
