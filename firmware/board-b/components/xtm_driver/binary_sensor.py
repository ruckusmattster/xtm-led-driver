import esphome.codegen as cg
from esphome.components import binary_sensor
import esphome.config_validation as cv
from esphome.const import (
    DEVICE_CLASS_CONNECTIVITY,
    DEVICE_CLASS_PROBLEM,
    ENTITY_CATEGORY_DIAGNOSTIC,
)

from . import CONF_XTM_DRIVER_ID, XtmDriver, xtm_ns

DEPENDENCIES = ["xtm_driver"]

# key -> (C++ BinaryKind, schema)
TYPES = {
    "link": (
        "BINARY_LINK",
        binary_sensor.binary_sensor_schema(
            device_class=DEVICE_CLASS_CONNECTIVITY,
            entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
        ),
    ),
    # Board A is holding the current down because a heatsink is hot.
    "derating": (
        "BINARY_DERATING",
        binary_sensor.binary_sensor_schema(device_class=DEVICE_CLASS_PROBLEM),
    ),
    "calibrated": (
        "BINARY_CALIBRATED",
        binary_sensor.binary_sensor_schema(entity_category=ENTITY_CATEGORY_DIAGNOSTIC),
    ),
    "light_matched": (
        "BINARY_LIGHT_MATCHED",
        binary_sensor.binary_sensor_schema(entity_category=ENTITY_CATEGORY_DIAGNOSTIC),
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
            sens = await binary_sensor.new_binary_sensor(conf)
            cg.add(hub.set_binary_sensor(getattr(xtm_ns, kind), sens))
