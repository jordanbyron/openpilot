import pytest

from opendbc.car import gen_empty_fingerprint
from opendbc.car.subaru.interface import CarInterface
from opendbc.car.subaru.values import CAR, SubaruFlags, SubaruSafetyFlags
from opendbc.safety import ALTERNATIVE_EXPERIENCE
from openpilot.common.params import Params
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
