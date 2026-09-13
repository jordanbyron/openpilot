import ast
import pathlib

import pytest

from opendbc.car import gen_empty_fingerprint
from opendbc.car.subaru.interface import CarInterface
from opendbc.car.subaru.values import CAR, SubaruFlags, SubaruSafetyFlags
from openpilot.common.basedir import BASEDIR
from openpilot.common.params import Params

CARD_PY = pathlib.Path(BASEDIR) / "selfdrive" / "car" / "card.py"

MIRRORED_CARD_INIT_GATE = "not self.CP.passive and self.CP.brand == 'subaru' and self.params.get_bool('SubaruSNG')"


@pytest.fixture
def params():
  p = Params()
  p.remove("SubaruSNG")
  yield p
  p.remove("SubaruSNG")


def fresh_cp(passive=False):
  CP = CarInterface.get_params(CAR.SUBARU_IMPREZA, gen_empty_fingerprint(), [], alpha_long=False,
                               is_release=False, docs=False)
  CP.passive = passive
  return CP


def apply_card_init_gate(params, CP):
  if not CP.passive and CP.brand == "subaru" and params.get_bool("SubaruSNG"):
    CarInterface.enable_stop_and_go(CP)


def card_init_gate_source():
  tree = ast.parse(CARD_PY.read_text())
  tests = [ast.unparse(node.test) for node in ast.walk(tree)
           if isinstance(node, ast.If) and "enable_stop_and_go" in ast.unparse(node)]
  assert len(tests) == 1, f"expected exactly one enable_stop_and_go gate in card.py, found {len(tests)}"
  return tests[0]


def test_default_off(params):
  assert not params.get_bool("SubaruSNG")


def test_local_gate_mirrors_card_py():
  assert card_init_gate_source() == MIRRORED_CARD_INIT_GATE


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


def test_card_init_gate_skips_passive_car(params):
  params.put_bool("SubaruSNG", True, block=True)
  CP = fresh_cp(passive=True)
  apply_card_init_gate(params, CP)

  assert not CP.flags & SubaruFlags.SNG
  assert not CP.safetyConfigs[0].safetyParam & SubaruSafetyFlags.SNG
