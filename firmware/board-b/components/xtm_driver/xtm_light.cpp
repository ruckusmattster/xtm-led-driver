#include "xtm_light.h"
#include "xtm_driver.h"

namespace esphome {
namespace xtm_driver {

std::unique_ptr<light::LightTransformer> XtmLightOutput::create_default_transition() {
  return make_unique<XtmTransition>(this);
}

void XtmLightOutput::write_state(light::LightState *state) {
  if (state->is_transformer_active())
    return;  // the whole transition already went to Board A when it started
  const auto &v = state->current_values;
  this->parent_->light_target(level_from_brightness(v.is_on(), v.get_brightness()), 0);
}

void XtmTransition::start() {
  // Same start and end points as ESPHome's own transition: brightness rises from zero when
  // turning on and falls to zero before switching off.
  if (!this->start_values_.is_on() && this->target_values_.is_on()) {
    this->start_values_ = light::LightColorValues(this->target_values_);
    this->start_values_.set_brightness(0.0f);
  }
  if (this->start_values_.is_on() && !this->target_values_.is_on()) {
    this->end_values_ = light::LightColorValues(this->start_values_);
    this->end_values_.set_brightness(0.0f);
  } else {
    this->end_values_ = light::LightColorValues(this->target_values_);
  }
  const auto &t = this->target_values_;
  this->output_->get_parent()->light_target(level_from_brightness(t.is_on(), t.get_brightness()), this->length_);
}

optional<light::LightColorValues> XtmTransition::apply() {
  // Linear, not ESPHome's smoothstep: Board A moves the curve position at a constant rate.
  return light::LightColorValues::lerp(this->start_values_, this->end_values_, this->get_progress_());
}

}  // namespace xtm_driver
}  // namespace esphome
