"""XTM LED driver: Board B's side of the link to Board A, plus the knob and group sync.

The hub owns the UART link to Board A. Platforms (light, sensor, text_sensor,
binary_sensor, button, number, switch) attach entities to it with `xtm_driver_id`.
"""

from esphome import pins
import esphome.codegen as cg
from esphome.components import espnow, output, uart
import esphome.config_validation as cv
from esphome.const import (
    CONF_BLUE,
    CONF_BRIGHTNESS,
    CONF_GREEN,
    CONF_ID,
    CONF_KEY,
    CONF_RED,
    CONF_STEP,
    CONF_TRANSITION_LENGTH,
    CONF_UPDATE_INTERVAL,
)

CODEOWNERS = []
DEPENDENCIES = ["uart"]
MULTI_CONF = False

CONF_XTM_DRIVER_ID = "xtm_driver_id"
CONF_BOOT0_PIN = "boot0_pin"
CONF_NRST_PIN = "nrst_pin"
CONF_STATUS_LED = "status_led"
CONF_ENCODER = "encoder"
CONF_MINIMUM = "minimum"
CONF_SYNC = "sync"
CONF_ESPNOW_ID = "espnow_id"
CONF_PING_INTERVAL = "ping_interval"
CONF_LINK_TIMEOUT = "link_timeout"
CONF_RESYNC_TRANSITION = "resync_transition"

xtm_ns = cg.esphome_ns.namespace("xtm_driver")
XtmDriver = xtm_ns.class_("XtmDriver", cg.Component, uart.UARTDevice)
XtmSync = xtm_ns.class_("XtmSync")


def AUTO_LOAD(config):
    loads = ["light", "output"]
    if CONF_SYNC in config:
        loads.append("hmac_sha256")
    return loads


SYNC_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(XtmSync),
        cv.GenerateID(CONF_ESPNOW_ID): cv.use_id(espnow.ESPNowComponent),
        # Shared by every fixture in the group; packets without a valid tag are ignored.
        cv.Required(CONF_KEY): cv.All(cv.string_strict, cv.Length(min=12, max=64)),
    }
)

STATUS_LED_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_RED): cv.use_id(output.FloatOutput),
        cv.Required(CONF_GREEN): cv.use_id(output.FloatOutput),
        cv.Required(CONF_BLUE): cv.use_id(output.FloatOutput),
        cv.Optional(CONF_BRIGHTNESS, default="30%"): cv.percentage,
    }
)

ENCODER_SCHEMA = cv.Schema(
    {
        # One detent moves this far along the brightness scale (1% = a 13% change in light).
        cv.Optional(CONF_STEP, default="1%"): cv.All(
            cv.percentage, cv.Range(min=0.001, max=0.2)
        ),
        # Turning up from off starts here; turning down stops here.
        cv.Optional(CONF_MINIMUM, default="1%"): cv.All(
            cv.percentage, cv.Range(min=0.0001, max=0.5)
        ),
        cv.Optional(
            CONF_TRANSITION_LENGTH, default="80ms"
        ): cv.positive_time_period_milliseconds,
    }
)

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(XtmDriver),
            cv.Optional(CONF_BOOT0_PIN): pins.gpio_output_pin_schema,
            cv.Optional(CONF_NRST_PIN): pins.gpio_output_pin_schema,
            cv.Optional(CONF_STATUS_LED): STATUS_LED_SCHEMA,
            cv.Optional(CONF_ENCODER, default={}): ENCODER_SCHEMA,
            cv.Optional(CONF_SYNC): SYNC_SCHEMA,
            # Board A declares the link lost after its link_timeout (1.5 s by default).
            cv.Optional(CONF_PING_INTERVAL, default="200ms"): cv.All(
                cv.positive_time_period_milliseconds,
                cv.Range(
                    min=cv.TimePeriod(milliseconds=50),
                    max=cv.TimePeriod(milliseconds=500),
                ),
            ),
            cv.Optional(
                CONF_LINK_TIMEOUT, default="1s"
            ): cv.positive_time_period_milliseconds,
            cv.Optional(
                CONF_RESYNC_TRANSITION, default="1s"
            ): cv.positive_time_period_milliseconds,
            cv.Optional(
                CONF_UPDATE_INTERVAL, default="1s"
            ): cv.positive_time_period_milliseconds,
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(uart.UART_DEVICE_SCHEMA)
)

FINAL_VALIDATE_SCHEMA = uart.final_validate_device_schema(
    "xtm_driver",
    baud_rate=115200,
    require_tx=True,
    require_rx=True,
    data_bits=8,
    parity="NONE",
    stop_bits=1,
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await uart.register_uart_device(var, config)

    if CONF_BOOT0_PIN in config:
        pin = await cg.gpio_pin_expression(config[CONF_BOOT0_PIN])
        cg.add(var.set_boot0_pin(pin))
    if CONF_NRST_PIN in config:
        pin = await cg.gpio_pin_expression(config[CONF_NRST_PIN])
        cg.add(var.set_nrst_pin(pin))

    if led := config.get(CONF_STATUS_LED):
        red = await cg.get_variable(led[CONF_RED])
        green = await cg.get_variable(led[CONF_GREEN])
        blue = await cg.get_variable(led[CONF_BLUE])
        cg.add(var.set_status_leds(red, green, blue, led[CONF_BRIGHTNESS]))

    enc = config[CONF_ENCODER]
    cg.add(
        var.set_encoder(enc[CONF_STEP], enc[CONF_MINIMUM], enc[CONF_TRANSITION_LENGTH])
    )
    cg.add(
        var.set_timing(
            config[CONF_PING_INTERVAL],
            config[CONF_LINK_TIMEOUT],
            config[CONF_RESYNC_TRANSITION],
        )
    )

    if sync := config.get(CONF_SYNC):
        bus = await cg.get_variable(sync[CONF_ESPNOW_ID])
        sync_var = cg.new_Pvariable(sync[CONF_ID], var, bus, sync[CONF_KEY])
        cg.add(var.set_sync(sync_var))
