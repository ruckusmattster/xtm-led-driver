import esphome.codegen as cg
from esphome.components import button
import esphome.config_validation as cv
from esphome.const import (
    DEVICE_CLASS_IDENTIFY,
    DEVICE_CLASS_RESTART,
    ENTITY_CATEGORY_CONFIG,
    ENTITY_CATEGORY_DIAGNOSTIC,
)

from . import CONF_XTM_DRIVER_ID, XtmDriver, xtm_ns

DEPENDENCIES = ["xtm_driver"]

XtmButton = xtm_ns.class_("XtmButton", button.Button)

# key -> (C++ ButtonKind, schema)
TYPES = {
    "clear_fault": (
        "BUTTON_CLEAR_FAULT",
        button.button_schema(
            XtmButton, icon="mdi:alert-remove", entity_category=ENTITY_CATEGORY_CONFIG
        ),
    ),
    "identify": (
        "BUTTON_IDENTIFY",
        button.button_schema(XtmButton, device_class=DEVICE_CLASS_IDENTIFY),
    ),
    "restart_board_a": (
        "BUTTON_RESTART_BOARD_A",
        button.button_schema(
            XtmButton,
            device_class=DEVICE_CLASS_RESTART,
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
            btn = await button.new_button(conf)
            cg.add(btn.set_parent(hub))
            cg.add(btn.set_kind(getattr(xtm_ns, kind)))
