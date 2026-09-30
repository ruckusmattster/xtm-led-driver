#pragma once

#include "esphome/core/component.h"
#include "esphome/core/defines.h"
#include "esphome/core/gpio.h"
#include "esphome/core/hal.h"
#include "esphome/core/helpers.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/light/light_state.h"
#include "esphome/components/output/float_output.h"
#ifdef USE_SENSOR
#include "esphome/components/sensor/sensor.h"
#endif
#ifdef USE_TEXT_SENSOR
#include "esphome/components/text_sensor/text_sensor.h"
#endif
#ifdef USE_BINARY_SENSOR
#include "esphome/components/binary_sensor/binary_sensor.h"
#endif

#include "link_client.h"
#include "sync_core.h"

#include <vector>

namespace esphome {
namespace xtm_driver {

class XtmLightOutput;
class XtmNumber;
class XtmSyncSwitch;
class XtmSync;

// Keep these in step with the key lists in sensor.py, text_sensor.py and binary_sensor.py.
enum SensorKind : uint8_t {
  SENSOR_LED_CURRENT = 0,
  SENSOR_LED_VOLTAGE,
  SENSOR_OUTPUT_VOLTAGE,
  SENSOR_INPUT_VOLTAGE,
  SENSOR_TEMP_FET,
  SENSOR_TEMP_BUCK,
  SENSOR_TEMP_AUX,
  SENSOR_TEMP_PRECISION,
  SENSOR_FULL_SCALE_LUX,
  SENSOR_BOARD_A_UPTIME,
  SENSOR_LINK_ERRORS,
  SENSOR_COUNT,
};
enum TextKind : uint8_t { TEXT_STATE = 0, TEXT_FAULT, TEXT_SYNC_ROLE, TEXT_FIRMWARE, TEXT_COUNT };
enum BinaryKind : uint8_t { BINARY_LINK = 0, BINARY_DERATING, BINARY_CALIBRATED, BINARY_LIGHT_MATCHED, BINARY_COUNT };
enum ButtonKind : uint8_t { BUTTON_CLEAR_FAULT = 0, BUTTON_IDENTIFY, BUTTON_RESTART_BOARD_A };

class XtmDriver : public Component, public uart::UARTDevice, public LinkHost {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }
  void on_shutdown() override;

  // ---- set up by code generation
  void set_light(XtmLightOutput *light) { this->light_ = light; }
  void set_boot0_pin(GPIOPin *pin) { this->boot0_pin_ = pin; }
  void set_nrst_pin(GPIOPin *pin) { this->nrst_pin_ = pin; }
  void set_status_leds(output::FloatOutput *red, output::FloatOutput *green, output::FloatOutput *blue,
                       float brightness) {
    this->led_[0] = red;
    this->led_[1] = green;
    this->led_[2] = blue;
    this->led_brightness_ = brightness;
  }
  void set_encoder(float step, float minimum, uint32_t transition_ms) {
    this->enc_step_ = step;
    this->enc_min_ = minimum;
    this->enc_transition_ms_ = transition_ms;
  }
  void set_timing(uint32_t ping_ms, uint32_t timeout_ms, uint32_t resync_ms) {
    this->ping_ms_ = ping_ms;
    this->timeout_ms_ = timeout_ms;
    this->resync_ms_ = resync_ms;
  }
  /// How often the measurement sensors publish (register_component sets it from update_interval).
  void set_update_interval(uint32_t ms) { this->update_ms_ = ms; }
#ifdef USE_SENSOR
  void set_sensor(uint8_t kind, sensor::Sensor *s) {
    if (kind < SENSOR_COUNT)
      this->sensors_[kind] = s;
  }
#endif
#ifdef USE_TEXT_SENSOR
  void set_text_sensor(uint8_t kind, text_sensor::TextSensor *s) {
    if (kind < TEXT_COUNT)
      this->texts_[kind] = s;
  }
#endif
#ifdef USE_BINARY_SENSOR
  void set_binary_sensor(uint8_t kind, binary_sensor::BinarySensor *s) {
    if (kind < BINARY_COUNT)
      this->binaries_[kind] = s;
  }
#endif
  void register_number(XtmNumber *number) { this->numbers_.push_back(number); }
  void set_sync_switch(XtmSyncSwitch *sw) { this->sync_switch_ = sw; }
  void set_sync(XtmSync *sync) { this->sync_ = sync; }

  // ---- actions: YAML lambdas, buttons, the sync switch
  /// One encoder detent; +1 is brighter.
  void encoder_step(int direction);
  /// The sync button: take the lead, or end the group if this fixture already leads it.
  void sync_press();
  void set_sync_lead(bool lead);
  /// Tell Board A not to treat silence as a lost link for this long (planned reboots, OTA).
  void hold(uint16_t seconds);
  void identify(uint8_t count = 3);
  void clear_fault();
  void restart_board_a();
  void set_param(uint8_t id, float value, bool save = true);

  // ---- from the light output
  void light_target(uint16_t level, uint32_t fade_ms);
  light::LightState *light_state() const;

  // ---- from the sync glue
  void apply_sync_level(uint16_t level, uint32_t fade_ms);
  void on_sync_role(SyncRole role);
  SyncRole sync_role() const;

  bool link_up() const { return this->link_.link_up(); }
  const DriverStatus &status() const { return this->link_.status(); }

  // ---- LinkHost
  void link_write(const uint8_t *data, size_t len) override;
  void on_status(const DriverStatus &st) override;
  void on_param(uint8_t id, float value) override;
  void on_link_change(bool up) override;
  void on_adopt(uint16_t level) override;
  void on_board_a_restart() override;
  void on_command_failed(uint8_t type, uint8_t result) override;
  void on_resync(uint16_t level, uint32_t fade_ms, const char *why) override;

 protected:
  void set_light_quietly_(uint16_t level, uint32_t fade_ms);
  void publish_measurements_();
  void publish_text_(uint8_t kind, const char *value);
  void publish_binary_(uint8_t kind, bool value);
  void update_leds_(uint32_t now);
  void request_params_();

  LinkClient link_{this};
  XtmLightOutput *light_{nullptr};
  GPIOPin *boot0_pin_{nullptr};
  GPIOPin *nrst_pin_{nullptr};
  output::FloatOutput *led_[3]{nullptr, nullptr, nullptr};
  float led_brightness_{0.3f};
  float led_last_[3]{-1.0f, -1.0f, -1.0f};
  uint32_t led_last_ms_{0};

  float enc_step_{0.01f};
  float enc_min_{0.01f};
  uint32_t enc_transition_ms_{80};
  uint32_t enc_last_ms_{0};

  uint32_t ping_ms_{200};
  uint32_t timeout_ms_{1000};
  uint32_t resync_ms_{1000};
  uint32_t update_ms_{1000};
  uint32_t last_publish_ms_{0};

  // The light's present target, and the one change that was not made locally.
  uint16_t target_level_{0};
  uint32_t target_end_ms_{0};
  bool expect_active_{false};
  uint16_t expect_level_{0};
  uint32_t expect_ms_{0};

  // Last published text and binary states, so they are sent on change only.
  uint8_t last_state_{0xFF};
  uint8_t last_fault_{0xFF};
  uint16_t last_flags_{0xFFFF};
  uint16_t last_fw_{0xFFFF};

#ifdef USE_SENSOR
  sensor::Sensor *sensors_[SENSOR_COUNT]{};
#endif
#ifdef USE_TEXT_SENSOR
  text_sensor::TextSensor *texts_[TEXT_COUNT]{};
#endif
#ifdef USE_BINARY_SENSOR
  binary_sensor::BinarySensor *binaries_[BINARY_COUNT]{};
#endif
  std::vector<XtmNumber *> numbers_;
  XtmSyncSwitch *sync_switch_{nullptr};
  XtmSync *sync_{nullptr};
};

const char *state_name(uint8_t state);
const char *fault_name(uint8_t fault);

}  // namespace xtm_driver
}  // namespace esphome
