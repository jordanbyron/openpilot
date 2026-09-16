from openpilot.cereal import log

from openpilot.common.constants import CV
from openpilot.system.ui.widgets.scroller import NavScroller
from openpilot.selfdrive.ui.mici.widgets.button import BigParamControl, BigMultiParamToggle, BigMultiToggle
from openpilot.system.ui.lib.application import gui_app
from openpilot.selfdrive.ui.layouts.settings.common import restart_needed_callback
from openpilot.selfdrive.ui.layouts.settings.subaru import AOL_PAUSE_SPEEDS_MPH, nearest_pause_speed_index, \
                                                           pause_speed_ms, aol_available, impreza_torque_available, sng_available
from openpilot.selfdrive.ui.ui_state import ui_state

PERSONALITY_TO_INT = log.LongitudinalPersonality.schema.enumerants


class TogglesLayoutMici(NavScroller):
  def __init__(self):
    super().__init__()

    self._personality_toggle = BigMultiParamToggle("driving personality", "LongitudinalPersonality", ["aggressive", "standard", "relaxed"],
                                                   description="Standard is recommended.\n" +
                                                               "Aggressive follows closer, with firmer gas and braking.\n" +
                                                               "Relaxed leaves more space.\n" +
                                                               "Use the steering wheel distance button on supported cars.")
    self._experimental_btn = BigParamControl("experimental mode", "ExperimentalMode",
                                       description_icon=gui_app.texture("icons_mici/experimental_mode.png", 64, 64),
                                       description="Let the driving model control gas and brakes.\n" +
                                                   "Includes stopping for red lights and stop signs.\n" +
                                                   "Set speed is a maximum, not a target.\n" +
                                                   "These are alpha features. Expect mistakes.\n" +
                                                   "The path colors show acceleration and braking.")
    is_metric_toggle = BigParamControl("use metric units", "IsMetric")
    ldw_toggle = BigParamControl("lane departure warnings", "IsLdwEnabled",
                                 description="Warn when you drift across a detected lane line.\n" +
                                             "Only above 31 mph (50 km/h), with no turn signal.")
    always_on_dm_toggle = BigParamControl("always-on driver monitor", "AlwaysOnDM", description="Monitor the driver even when openpilot is not engaged.")
    self._always_on_lateral_toggle = BigParamControl("always-on lateral", "AlwaysOnLateral", toggle_callback=restart_needed_callback,
                                                     description="Keep steering whenever cruise main is on, even when openpilot\n" +
                                                                 "is not engaged. Stops in reverse/park and on any fault.")
    self._aol_pause_labels = self._pause_speed_labels()
    self._aol_pause_toggle = BigMultiToggle("always-on lateral pause speed", self._aol_pause_labels,
                                            select_callback=self._set_aol_pause_speed,
                                            description="Pause always-on lateral while braking below this speed.")
    self._impreza_torque_toggle = BigParamControl("increased steer torque", "SubaruImprezaTorque", toggle_callback=restart_needed_callback,
                                                  description="Raise Impreza/Crosstrek max steering torque by 50%.\n" +
                                                              "Exceeds the stock limit.")
    self._subaru_sng_toggle = BigParamControl("subaru stop and go", "SubaruSNG", toggle_callback=restart_needed_callback,
                                              description="Resume from an EyeSight hold when the lead car pulls away.\n" +
                                                          "Gen1 EyeSight with stock cruise only.")
    record_front = BigParamControl("record & upload cabin camera", "RecordFront",
                                   description_icon=gui_app.texture("icons_mici/settings/device/cameras.png", 64, 64),
                                   toggle_callback=restart_needed_callback, description="Upload cabin camera data to help improve driver monitoring.")
    record_mic = BigParamControl("record & upload mic audio", "RecordAudio", description_icon=gui_app.texture("icons_mici/microphone.png", 64, 64),
                                 toggle_callback=restart_needed_callback,
                                 description="Record microphone audio while driving.\n" +
                                             "Audio is included in dashcam videos in comma connect.")
    enable_openpilot = BigParamControl("enable openpilot", "OpenpilotEnabledToggle", toggle_callback=restart_needed_callback,
                                       description="Enable to use openpilot driver assistance.\n" +
                                                   "Disable to use your car's stock driver assistance.")

    self._scroller.add_widgets([
      self._personality_toggle,
      self._experimental_btn,
      is_metric_toggle,
      ldw_toggle,
      always_on_dm_toggle,
      self._always_on_lateral_toggle,
      self._aol_pause_toggle,
      self._impreza_torque_toggle,
      self._subaru_sng_toggle,
      record_front,
      record_mic,
      enable_openpilot,
    ])

    # Toggle lists
    self._refresh_toggles = (
      ("ExperimentalMode", self._experimental_btn),
      ("IsMetric", is_metric_toggle),
      ("IsLdwEnabled", ldw_toggle),
      ("AlwaysOnDM", always_on_dm_toggle),
      ("AlwaysOnLateral", self._always_on_lateral_toggle),
      ("SubaruImprezaTorque", self._impreza_torque_toggle),
      ("SubaruSNG", self._subaru_sng_toggle),
      ("RecordFront", record_front),
      ("RecordAudio", record_mic),
      ("OpenpilotEnabledToggle", enable_openpilot),
    )

    enable_openpilot.set_enabled(lambda: not ui_state.engaged)
    record_front.set_enabled(False if ui_state.params.get_bool("RecordFrontLock") else (lambda: not ui_state.engaged))
    record_mic.set_enabled(lambda: not ui_state.engaged)
    self._always_on_lateral_toggle.set_enabled(lambda: not (ui_state.engaged or self._aol_active))
    self._impreza_torque_toggle.set_enabled(lambda: not ui_state.engaged)
    self._subaru_sng_toggle.set_enabled(lambda: not ui_state.engaged)

    if ui_state.params.get_bool("ShowDebugInfo"):
      gui_app.set_show_touches(True)
      gui_app.set_show_fps(True)

    ui_state.add_engaged_transition_callback(self._update_toggles)

  @property
  def _aol_active(self) -> bool:
    return ui_state.started and ui_state.sm["selfdriveState"].alwaysOnLateral

  def _pause_speed_labels(self) -> list[str]:
    if ui_state.params.get_bool("IsMetric"):
      return ["off"] + [f"{round(mph * CV.MPH_TO_KPH)} km/h" for mph in AOL_PAUSE_SPEEDS_MPH[1:]]
    return ["off"] + [f"{mph} mph" for mph in AOL_PAUSE_SPEEDS_MPH[1:]]

  def _set_aol_pause_speed(self, label: str):
    ui_state.params.put("AlwaysOnLateralPauseSpeed", pause_speed_ms(self._aol_pause_labels.index(label)), block=True)

  def _update_state(self):
    super()._update_state()

    if ui_state.sm.updated["selfdriveState"]:
      personality = PERSONALITY_TO_INT[ui_state.sm["selfdriveState"].personality]
      if personality != ui_state.personality and ui_state.started:
        self._personality_toggle.set_value(self._personality_toggle._options[personality])
      ui_state.personality = personality

  def show_event(self):
    super().show_event()
    self._update_toggles()

  def _update_toggles(self):
    ui_state.update_params()

    # CP gating for experimental mode
    if ui_state.CP is not None:
      if ui_state.has_longitudinal_control:
        self._experimental_btn.set_visible(True)
        self._personality_toggle.set_visible(True)
      else:
        # no long for now
        self._experimental_btn.set_visible(False)
        self._experimental_btn.set_checked(False)
        self._personality_toggle.set_visible(False)
        ui_state.params.remove("ExperimentalMode")

    aol = aol_available(ui_state.CP)
    self._always_on_lateral_toggle.set_visible(aol)
    self._aol_pause_toggle.set_visible(aol)
    if ui_state.CP is not None and not aol:
      ui_state.params.remove("AlwaysOnLateral")

    impreza_torque = impreza_torque_available(ui_state.CP)
    self._impreza_torque_toggle.set_visible(impreza_torque)
    if ui_state.CP is not None and not impreza_torque:
      ui_state.params.remove("SubaruImprezaTorque")

    sng = sng_available(ui_state.CP)
    self._subaru_sng_toggle.set_visible(sng)
    if ui_state.CP is not None and not sng:
      ui_state.params.remove("SubaruSNG")

    # Refresh toggles from params to mirror external changes
    for key, item in self._refresh_toggles:
      item.set_checked(ui_state.params.get_bool(key))

    pause_index = nearest_pause_speed_index(ui_state.params.get("AlwaysOnLateralPauseSpeed", return_default=True))
    self._aol_pause_toggle.set_value(self._aol_pause_labels[pause_index])
