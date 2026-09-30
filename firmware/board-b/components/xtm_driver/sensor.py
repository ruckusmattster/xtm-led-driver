import esphome.codegen as cg
from esphome.components import sensor
import esphome.config_validation as cv
from esphome.const import (
    DEVICE_CLASS_CURRENT,
    DEVICE_CLASS_DURATION,
    DEVICE_CLASS_ILLUMINANCE,
    DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_VOLTAGE,
    ENTITY_CATEGORY_DIAGNOSTIC,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    UNIT_AMPERE,
    UNIT_CELSIUS,
    UNIT_LUX,
    UNIT_SECOND,
    UNIT_VOLT,
)

from . import CONF_XTM_DRIVER_ID, XtmDriver, xtm_ns

DEPENDENCIES = ["xtm_driver"]


def _temp():
    return sensor.sensor_schema(
        unit_of_measurement=UNIT_CELSIUS,
        accuracy_decimals=1,
        device_class=DEVICE_CLASS_TEMPERATURE,
        state_class=STATE_CLASS_MEASUREMENT,
        entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    )


def _volt(category=cv.UNDEFINED):
    return sensor.sensor_schema(
        unit_of_measurement=UNIT_VOLT,
        accuracy_decimals=2,
        device_class=DEVICE_CLASS_VOLTAGE,
        state_class=STATE_CLASS_MEASUREMENT,
        entity_category=category,
    )


# key -> (C++ SensorKind, schema). Order and names match SensorKind in xtm_driver.h.
TYPES = {
    "led_current": (
        "SENSOR_LED_CURRENT",
        sensor.sensor_schema(
            unit_of_measurement=UNIT_AMPERE,
            accuracy_decimals=6,  # the dimmest setting is about 5 uA
            device_class=DEVICE_CLASS_CURRENT,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
    ),
    "led_voltage": ("SENSOR_LED_VOLTAGE", _volt()),
    "output_voltage": ("SENSOR_OUTPUT_VOLTAGE", _volt(ENTITY_CATEGORY_DIAGNOSTIC)),
    "input_voltage": ("SENSOR_INPUT_VOLTAGE", _volt(ENTITY_CATEGORY_DIAGNOSTIC)),
    "fet_temperature": ("SENSOR_TEMP_FET", _temp()),
    "buck_temperature": ("SENSOR_TEMP_BUCK", _temp()),
    "aux_temperature": ("SENSOR_TEMP_AUX", _temp()),
    "precision_temperature": ("SENSOR_TEMP_PRECISION", _temp()),
    "full_scale_light": (
        "SENSOR_FULL_SCALE_LUX",
        sensor.sensor_schema(
            unit_of_measurement=UNIT_LUX,
            accuracy_decimals=0,
            device_class=DEVICE_CLASS_ILLUMINANCE,
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
    ),
    "board_a_uptime": (
        "SENSOR_BOARD_A_UPTIME",
        sensor.sensor_schema(
            unit_of_measurement=UNIT_SECOND,
            accuracy_decimals=0,
            device_class=DEVICE_CLASS_DURATION,
            state_class=STATE_CLASS_TOTAL_INCREASING,
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
    ),
    "link_errors": (
        "SENSOR_LINK_ERRORS",
        sensor.sensor_schema(
            accuracy_decimals=0,
            state_class=STATE_CLASS_TOTAL_INCREASING,
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
    ),
}

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_XTM_DRIVER_ID): cv.use_id(XtmDriver),
        **{cv.Optional(key): schema for key, (_, schema) in TYPES.items()},
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_XTM_DRIVER_ID])
    for key, (kind, _) in TYPES.items():
        if conf := config.get(key):
            sens = await sensor.new_sensor(conf)
            cg.add(hub.set_sensor(getattr(xtm_ns, kind), sens))
