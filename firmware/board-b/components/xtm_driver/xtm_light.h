#pragma once

#include "esphome/components/light/light_output.h"
#include "esphome/components/light/light_state.h"
#include "esphome/components/light/light_transformer.h"
#include "esphome/core/helpers.h"

namespace esphome {
namespace xtm_driver {

class XtmDriver;

/// The fixture as an ESPHome light. Board A owns the curve and runs every fade itself, so
/// brightness goes to Board A as a 16-bit level on its own curve (no gamma here) and a
/// transition goes as one "fade to X over T" command.
class XtmLightOutput : public light::LightOutput, public Parented<XtmDriver> {
 public:
  light::LightTraits get_traits() override {
    auto traits = light::LightTraits();
    traits.set_supported_color_modes({light::ColorMode::BRIGHTNESS});
    return traits;
  }
  std::unique_ptr<light::LightTransformer> create_default_transition() override;
  void setup_state(light::LightState *state) override { this->state_ = state; }
  void write_state(light::LightState *state) override;
  light::LightState *get_state() const { return this->state_; }

 protected:
  light::LightState *state_{nullptr};
};

/// Sends the transition to Board A when it starts, then moves ESPHome's idea of the present
/// brightness linearly in time, as Board A does, so the knob and automations start from
/// where the light really is. Nothing is written to Board A while it runs.
class XtmTransition : public light::LightTransformer {
 public:
  explicit XtmTransition(XtmLightOutput *output) : output_(output) {}
  void start() override;
  optional<light::LightColorValues> apply() override;

 protected:
  XtmLightOutput *output_;
  light::LightColorValues end_values_{};
};

}  // namespace xtm_driver
}  // namespace esphome
