# Fork changes — `crosstrek` branch

Three optional features on top of openpilot 0.11.1, all **default OFF**. With every toggle off the
device is byte-identical to stock: `safetyParam == 0`, `alternativeExperience == 0`, no new CAN
traffic. Each is a user toggle in *Settings → Toggles*, read once per ignition cycle in
`selfdrive/car/card.py` before `CarParams` is written, so panda and openpilot never disagree
mid-drive.

All three toggles, the Always-On Lateral pause-speed selector and the teal AOL border are present in
both UI trees: the comma 3/3X UI (`selfdrive/ui/`) and the comma 4 UI (`selfdrive/ui/mici/`). Both
share one set of visibility predicates and unit conversions in
`selfdrive/ui/layouts/settings/subaru.py` so they cannot drift apart.

Changes span two repos: `opendbc_repo` (car interface + panda safety) and this one. Panda firmware
picks up the safety headers from `opendbc_repo` automatically; `panda/` itself is untouched.

---

## 1. Impreza/Crosstrek increased steer torque

Raises the LKAS torque cap on `SUBARU_IMPREZA` from 2047 to 3071 (1.5x) and divides the PID gains
(`kf`, `kpV`, `kiV`) by 1.5, so torque per unit of error is unchanged and only the saturation point
moves. Gen2 and all other platforms keep their stock limits.

| | |
|---|---|
| Param | `SubaruImprezaTorque` `{PERSISTENT, BOOL}` |
| `SubaruSafetyFlags.IMPREZA_TORQUE` | `8` (into `safetyParam`) |
| `SubaruFlags.IMPREZA_TORQUE` | `128` (into `CP.flags`, runtime-only) |
| C | `SUBARU_PARAM_IMPREZA_TORQUE = 8`, `subaru_impreza_torque` |

Panda holds the real limit: `SUBARU_IMPREZA_STEERING_LIMITS` is selected in `subaru_tx_hook` only
when the safetyParam bit is set, and only on gen1. Rate (50/70), RT delta, driver
allowance/multiplier (60/50) and steer-req tolerance are untouched.

The flag is read **outside** `#ifdef ALLOW_DEBUG` in `subaru_init`, deliberately: a hypothetical
RELEASE build with the read gated would cap at 2047 while openpilot commanded 3071, rejecting every
LKAS frame.

## 2. Subaru stop-and-go auto-resume

On gen1 global cars running stock cruise, openpilot mirrors `Throttle` (0x40) and `Brake_Pedal`
(0x139) onto the camera bus, pulsing throttle and releasing brake so EyeSight resumes from a stop
instead of requiring a driver input. Panda blocks the stock copies through the relay for the whole
drive, so the mirror must transmit continuously — it cannot be gated on `controls_allowed`.

| | |
|---|---|
| Param | `SubaruSNG` `{PERSISTENT, BOOL}` |
| `SubaruSafetyFlags.SNG` | `16` |
| `SubaruFlags.SNG` | `256` |
| C | `SUBARU_PARAM_SNG = 16` (inside `ALLOW_DEBUG`), `subaru_sng` |

**FrogPilot parity (branch `crosstrek-fp-parity`).** The panda side matches FrogPilot's
`safety_subaru.h`: the two mirrors are on the SNG TX allowlist, `subaru_tx_hook` rejects them only
when SNG is off, and a `subaru_fwd_hook` blocks the stock 0x40/0x139 main->cam while SNG is on. No
field bounds, no `Brake_Pedal` RX check, and the mirror entries are not relay-checked, exactly as in
FrogPilot. The car side matches FrogPilot's `carcontroller.stop_and_go` and `subarucan` builders:
`Throttle_Pedal = 5` and `Brake_Pedal = 5` replace the reported values outright, `Speed = 3` km/h
(FrogPilot's value; an earlier revision of this fork sent 3 raw counts, 0.17 km/h, by mistake),
the throttle mirror re-bases its counter off the last stock frame, and the resume pulse uses
FrogPilot's `sng_acc_resume` state machine including its rest-at-minus-one quirk. The pulse is not
masked on a driver gas press.

The stricter panda bounding that this fork originally added (rolling-max limits on the mirrored
fields plus a 50 Hz `Brake_Pedal` RX check) lives in the `crosstrek-fp` branch history if it is
ever wanted back. It was dropped so the road-tested FrogPilot behavior is what gets driven first.

Eligibility (`CarInterface.enable_stop_and_go`) excludes gen2, hybrid, preglobal, LKAS-angle, and
any car with openpilot longitudinal.

## 3. Always On Lateral (AOL)

Keeps openpilot steering whenever the car's cruise main switch is on, even when openpilot is not
engaged or after a brake press. Scoped to Subaru — the only mode it has been validated on.

| | |
|---|---|
| Params | `AlwaysOnLateral` `{PERSISTENT, BOOL}`, `AlwaysOnLateralPauseSpeed` `{PERSISTENT, FLOAT, "0.0"}` (m/s) |
| Alt experience | `ALT_EXP_ALWAYS_ON_LATERAL` / `ALTERNATIVE_EXPERIENCE.ALWAYS_ON_LATERAL` = `32` |
| cereal | `SelfdriveState.alwaysOnLateral @13 :Bool` |
| C | `aol_allowed`, `aol_supported`; accessor `get_aol_allowed` |

**Panda.** The may-steer gate in `lateral.h` becomes `(aol_allowed || controls_allowed)`.
`aol_allowed` requires `aol_supported` (set only by `subaru_init`) AND alt-experience bit 32 AND ACC
main on AND valid RX checks AND no steering disengage. Every torque, rate, driver-override and
steer-req limit is untouched, and longitudinal checks still key off `controls_allowed` alone — AOL
never enables longitudinal.

`safety_tick` also closes `aol_allowed` directly whenever the RX checks go invalid: the gate is
otherwise only recomputed on RX, so total CAN loss would leave a stale "allowed" in place.

The `!steering_disengage` term is carried for future modes; Subaru never sets `steering_disengage`,
so on this car driver override is handled entirely by the unchanged driver-torque limits.

One bad whitelisted frame sets the shared `safety_rx_checks_invalid` until the next `safety_tick`
(FrogPilot devnew's line verbatim); see the policy notes below for why this is the shared flag.

**openpilot.** `selfdrived` is the sole authority for "AOL active" and publishes
`SelfdriveState.alwaysOnLateral`; controlsd, driver monitoring and the UI consume it. No new
sockets. Both UIs draw a teal border while AOL steers and openpilot is disengaged.

`AlwaysOnLateralGate` (`selfdrive/selfdrived/helpers.py`) mirrors FrogPilot's
`frogpilot_card` gating exactly: cuts AOL on CAN invalid, cruise unavailable,
park/reverse/neutral/unknown gear, `liveCalibration.calPerc < 1`, any `ET.IMMEDIATE_DISABLE` event
other than `speedTooLow`, and brake pressed below `AlwaysOnLateralPauseSpeed` while moving.

Policy notes:
- **SOFT_DISABLE does not cut AOL**, as in FrogPilot. Steer faults drop `latActive` in controlsd and
  it returns on the next clean frame, as in FrogPilot; there is no cooldown.
- **A gas-pedal press (`ET.USER_DISABLE`) does not stop AOL**, and the default pause speed is `0.0`,
  meaning a brake press never pauses steering. Pause options are 0/5/10/15 mph.
- The panda-side bad-frame latch is FrogPilot devnew's line verbatim: one bad whitelisted frame sets
  the shared `safety_rx_checks_invalid` until the next `safety_tick`. That flag reaches
  `pandaState.safetyRxChecksInvalid`, which is what lets openpilot drop AOL and re-ramp torque from
  zero in step with the panda's own `desired_torque_last` reset. An earlier revision used a private
  latch here; review showed it left LKAS silently blocked after a bad frame during AOL-only steering,
  and that the engaged-mode `controlsMismatch` it was meant to avoid happens on stock anyway (the
  safety core clears `controls_allowed` on any invalid frame), just two seconds later.
- The dash LKAS indicator and lane-line enables in `ES_LKAS_State` key on `latActive` rather than
  `enabled`, as in FrogPilot stable, so the cluster shows LKAS while AOL steers.
- The SNG throttle mirror carries every stock bit: the 0.11.1 DBC had no signal for bits 29-30 of
  `Throttle`, so a `Signal2` was added to the generator source to mirror them as FrogPilot's DBC does.

The stricter gating this fork originally had (SOFT_DISABLE cut, 1 s steer-fault cooldown, full
calibration required) is in the `crosstrek-fp` branch history.

---

## Bit allocation

`SubaruSafetyFlags` 1/2/4 (GEN2 / LONG / PREGLOBAL_REVERSED_DRIVER_TORQUE) are untouched.
Torque and SNG are live simultaneously on a Crosstrek, so they must not alias — an earlier draft
gave both `SubaruFlags` bit 128, which would have silently enabled one from the other.

| Feature | `SubaruSafetyFlags` | `SubaruFlags` |
|---|---|---|
| Impreza torque | `8` | `128` |
| SNG | `16` | `256` |

All three on ⇒ `safetyParam == 24`, `alternativeExperience == 32`, `CP.flags` includes `384`.
This is the pair `selfdrived.py` compares against `pandaStates` every cycle; a mismatch raises
`controlsMismatch`.

Runtime `SubaruFlags` bits are set only in `interface.py` / `card.py`, never via
`platform.config.flags` — `opendbc/car/interfaces.py` ORs that for every brand, so a user bit there
would corrupt other brands' `CarParams`.

---

## On-device validation order

**Do not reorder, and do not skip to public roads.** Enable one feature per drive; only after each
has passed alone should all three run together.

**0. All toggles off.** Confirm byte-identical stock behavior: `safetyParam == 0`,
`alternativeExperience == 0`, no `controlsMismatch`, no `relayMalfunction`, no EyeSight
`Cruise_Fault`, `pandaStates[0]` matching `carParams`.

**1. Impreza torque.** Toggle on, restart, confirm `pandaStates[0].safetyParam & 8` and no
`controlsMismatch`. Then the **required hardware gate**: 3071 is an empirical community value, not
an OEM EPS spec, and no software test can show the EPS tolerates sustained torque above 2047 without
faulting or thermally derating. Validate empty-lot / low-speed first, then a tight curve that
saturates stock 2047, watching `LKAS_Output` vs commanded torque, `steerSaturated`, and both steer
fault flags. Only after a clean run at sustained saturation should the toggle be used in normal
driving.

**2. SNG.** Toggle off first: confirm no 0x40/0x139 from openpilot on bus 2 (`can_printer.py -b 2`).
Toggle on: bus 2 carries openpilot's 0x40 at 100 Hz and 0x139 at 50 Hz with monotonic counters and
no gaps; no `controlsMismatch`, `relayMalfunction`, or `Cruise_Fault`. Soak at least one full 30+
minute drive with varied throttle and braking, watching `accFaulted` / `Cruise_Fault` / blocked-TX
counts. Only then the parking-lot test: stop behind a cooperative lead, the car should creep off
when the lead moves; after a driver-braked stop with no lead it must not.

**3. AOL.** Confirm pandad reflashed and `pandaStates[0].alternativeExperience == 32`. Cruise main
on and not engaged ⇒ teal border, `carControl.latActive` true, ES_LKAS torque non-zero. Brake press
keeps steering (pause speed honored, standstill exempt); park/reverse/main-off/uncalibrated ⇒ no
steering; toggle off ⇒ bit clear and stock behavior. **Before wide use**, run a controlled session
(bench or empty road) watching `Steer_Warning` / `Steer_Error_1` with ACC main on and cruise
inactive across speeds and steering inputs, checking whether a marginal EPS fault chatters (FrogPilot
has no cooldown; if chatter shows up on this car, that is the one place a deviation is justified).

---

## Test commands

opendbc (`opendbc_repo`, its own venv, `unittest` — pytest is not installed there):

```bash
source opendbc_repo/.venv/bin/activate && export PYTHONPATH=$PWD/opendbc_repo && cd opendbc_repo
unittest-parallel -j4                              # whole suite; required, lateral.h is shared by every brand
python -m unittest opendbc.safety.tests.test_subaru
python -m unittest discover -s opendbc/car/subaru/tests -t .
bash opendbc/safety/tests/test.sh                  # all modes + 100% line coverage gate
bash opendbc/safety/tests/misra/test_misra.sh
python opendbc/safety/tests/mutation.py
ruff check opendbc/car opendbc/safety && ty check opendbc/car opendbc/safety
```

`test.sh` needs `llvm-cov` on PATH (macOS: `/Library/Developer/CommandLineTools/usr/bin`). It reads
**every** `.gcno` in `opendbc/safety/tests/libsafety/`, and only deletes `.gcda` between runs — stale
`.gcno` files from earlier builds merge into the report and produce bogus sub-100% coverage. Clear
them first:

```bash
find opendbc/safety/tests/libsafety -maxdepth 1 \( -name 'tmp*.gcno' -o -name 'tmp*.gcda' -o -name 'tmp*.os' \) -delete
```

Panda firmware (must stay warning-free; `-Wall -Wextra -Werror`):

```bash
export PATH=<arm-gnu-toolchain>/bin:$PATH
source opendbc_repo/.venv/bin/activate && cd panda && scons -j8
```

openpilot:

```bash
source .venv/bin/activate
python -m pytest selfdrive/selfdrived/tests selfdrive/car/tests/test_always_on_lateral_param.py \
                 selfdrive/car/tests/test_subaru_sng.py selfdrive/car/tests/test_subaru_feature_integration.py \
                 common/tests/test_params.py selfdrive/ui/tests/test_translations.py -q
ruff check . && ty check selfdrive/selfdrived selfdrive/controls selfdrive/car
```

`selfdrive/car/tests/test_subaru_feature_integration.py` is the cross-feature guard: all three
toggles off ⇒ stock, all three on ⇒ `safetyParam == 24` / `alternativeExperience == 32`, and the two
`SubaruFlags` bits are disjoint.

On the safety side `TestSubaruGen1ImprezaTorqueSngSafety` is the only class matching the real device
config (AOL via alt-experience + torque + SNG). It pins the cross-feature behaviors: the Impreza
3071 cap still applies under `aol_allowed` with `controls_allowed` false, and AOL is independent of
whether `Brake_Pedal` (0x139) was ever received, since SNG adds no RX check.
