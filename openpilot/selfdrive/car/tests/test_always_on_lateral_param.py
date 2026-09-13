import ast
import pathlib

import pytest

from opendbc.car import gen_empty_fingerprint
from opendbc.car.subaru.interface import CarInterface
from opendbc.car.subaru.values import CAR
from opendbc.safety import ALTERNATIVE_EXPERIENCE
from openpilot.common.basedir import BASEDIR
from openpilot.common.params import Params

CARD_PY = pathlib.Path(BASEDIR) / "selfdrive" / "car" / "card.py"

MIRRORED_CARD_INIT_GATE = "controller_available and self.params.get_bool('AlwaysOnLateral')"


@pytest.fixture
def params():
  p = Params()
  p.remove("AlwaysOnLateral")
  yield p
  p.remove("AlwaysOnLateral")


def fresh_cp():
  CP = CarInterface.get_params(CAR.SUBARU_IMPREZA, gen_empty_fingerprint(), [], alpha_long=False,
                               is_release=False, docs=False)
  CP.alternativeExperience = 0
  return CP


def apply_card_init_gate(params, CP, controller_available=True):
  if controller_available and params.get_bool("AlwaysOnLateral"):
    CP.alternativeExperience |= ALTERNATIVE_EXPERIENCE.ALWAYS_ON_LATERAL


def card_init_gate_source():
  tree = ast.parse(CARD_PY.read_text())
  tests = [ast.unparse(node.test) for node in ast.walk(tree)
           if isinstance(node, ast.If) and "ALWAYS_ON_LATERAL" in ast.unparse(node)]
  assert len(tests) == 1, f"expected exactly one ALWAYS_ON_LATERAL gate in card.py, found {len(tests)}"
  return tests[0]


def test_default_off(params):
  assert not params.get_bool("AlwaysOnLateral")


def test_local_gate_mirrors_card_py():
  assert card_init_gate_source() == MIRRORED_CARD_INIT_GATE


def test_card_init_gate_is_noop_by_default(params):
  CP = fresh_cp()
  apply_card_init_gate(params, CP)
  assert CP.alternativeExperience & ALTERNATIVE_EXPERIENCE.ALWAYS_ON_LATERAL == 0


def test_card_init_gate_sets_bit_when_enabled(params):
  params.put_bool("AlwaysOnLateral", True, block=True)
  CP = fresh_cp()
  apply_card_init_gate(params, CP)
  assert CP.alternativeExperience & ALTERNATIVE_EXPERIENCE.ALWAYS_ON_LATERAL


def test_card_init_gate_needs_a_controller(params):
  params.put_bool("AlwaysOnLateral", True, block=True)
  CP = fresh_cp()
  apply_card_init_gate(params, CP, controller_available=False)
  assert CP.alternativeExperience & ALTERNATIVE_EXPERIENCE.ALWAYS_ON_LATERAL == 0


def test_bit_value_matches_panda():
  assert ALTERNATIVE_EXPERIENCE.ALWAYS_ON_LATERAL == 32
