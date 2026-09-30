#pragma once

#include "esphome/core/defines.h"
#include "esphome/core/helpers.h"
#include "xtm_driver.h"

#ifdef USE_BUTTON
#include "esphome/components/button/button.h"
#endif
#ifdef USE_NUMBER
#include "esphome/components/number/number.h"
#endif
#ifdef USE_SWITCH
#include "esphome/components/switch/switch.h"
#endif

namespace esphome {
namespace xtm_driver {

#ifdef USE_BUTTON
class XtmButton : public button::Button, public Parented<XtmDriver> {
 public:
  void set_kind(uint8_t kind) { this->kind_ = kind; }

 protected:
  void press_action() override {
    switch (this->kind_) {
      case BUTTON_CLEAR_FAULT:
        this->parent_->clear_fault();
        break;
      case BUTTON_IDENTIFY:
        this->parent_->identify(3);
        break;
      case BUTTON_RESTART_BOARD_A:
        this->parent_->restart_board_a();
        break;
      default:
        break;
    }
  }
  uint8_t kind_{0};
};
#endif

#ifdef USE_NUMBER
/// A Board A setting. Shown in `scale`-divided units (percent, microamps); the state is
/// published when Board A confirms the stored value, so a rejected value snaps back.
class XtmNumber : public number::Number, public Parented<XtmDriver> {
 public:
  void set_param(uint8_t id, float scale) {
    this->id_ = id;
    this->scale_ = scale;
  }
  uint8_t param_id() const { return this->id_; }
  float scale() const { return this->scale_; }

 protected:
  void control(float value) override { this->parent_->set_param(this->id_, value * this->scale_, true); }
  uint8_t id_{0};
  float scale_{1.0f};
};
#endif

#ifdef USE_SWITCH
/// On while this fixture leads the group. Turning it on takes the lead; off ends the group.
class XtmSyncSwitch : public switch_::Switch, public Parented<XtmDriver> {
 protected:
  void write_state(bool state) override { this->parent_->set_sync_lead(state); }
};
#endif

}  // namespace xtm_driver
}  // namespace esphome
