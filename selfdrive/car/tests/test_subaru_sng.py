import pytest

from opendbc.car import gen_empty_fingerprint
from opendbc.car.subaru.interface import CarInterface
from opendbc.car.subaru.values import CAR, SubaruFlags, SubaruSafetyFlags
from openpilot.common.params import Params


@pytest.fixture
def params():
  p = Params()
  p.remove("SubaruSNG")
  yield p
  p.remove("SubaruSNG")


def fresh_cp():
  return CarInterface.get_params(CAR.SUBARU_IMPREZA, gen_empty_fingerprint(), [], alpha_long=False,
                                 is_release=False, docs=False)


def apply_card_init_gate(params, CP):
  if CP.brand == "subaru" and params.get_bool("SubaruSNG"):
    CarInterface.enable_stop_and_go(CP)


def test_default_off(params):
  assert not params.get_bool("SubaruSNG")


def test_card_init_gate_is_noop_by_default(params):
  CP = fresh_cp()
  apply_card_init_gate(params, CP)

  assert not CP.flags & SubaruFlags.SNG
  assert not CP.safetyConfigs[0].safetyParam & SubaruSafetyFlags.SNG


def test_card_init_gate_applies_when_set(params):
  params.put_bool("SubaruSNG", True, block=True)
  CP = fresh_cp()
  apply_card_init_gate(params, CP)

  assert CP.flags & SubaruFlags.SNG
  assert CP.safetyConfigs[0].safetyParam & SubaruSafetyFlags.SNG
