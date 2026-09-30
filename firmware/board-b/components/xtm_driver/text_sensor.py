import esphome.codegen as cg
from esphome.components import text_sensor
import esphome.config_validation as cv
from esphome.const import ENTITY_CATEGORY_DIAGNOSTIC

from . import CONF_XTM_DRIVER_ID, XtmDriver, xtm_ns

DEPENDENCIES = ["xtm_driver"]

# key -> (C++ TextKind, schema)
TYPES = {
    "driver_state": ("TEXT_STATE", text_sensor.text_sensor_schema(icon="mdi:led-on")),
    "fault": ("TEXT_FAULT", text_sensor.text_sensor_schema(icon="mdi:alert-circle-outline")),
    "sync_role": ("TEXT_SYNC_ROLE", text_sensor.text_sensor_schema(icon="mdi:link-variant")),
    "board_a_firmware": (
        "TEXT_FIRMWARE",
        text_sensor.text_sensor_schema(
            icon="mdi:chip", entity_category=ENTITY_CATEGORY_DIAGNOSTIC
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
            sens = await text_sensor.new_text_sensor(conf)
            cg.add(hub.set_text_sensor(getattr(xtm_ns, kind), sens))
