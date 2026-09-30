"""Board A settings as number entities. Each is read from Board A when the link comes up
and saved in Board A's flash when changed (the write waits until the light is off or dim)."""

import esphome.codegen as cg
from esphome.components import number
import esphome.config_validation as cv
from esphome.const import (
    CONF_MODE,
    ENTITY_CATEGORY_CONFIG,
    UNIT_AMPERE,
    UNIT_LUX,
    UNIT_PERCENT,
    UNIT_SECOND,
)

from . import CONF_XTM_DRIVER_ID, XtmDriver, xtm_ns

DEPENDENCIES = ["xtm_driver"]

XtmNumber = xtm_ns.class_("XtmNumber", number.Number)

UNIT_MICROAMPERE = "µA"

# Parameter ids from link_protocol.h (enum link_param).
PARAM_FALLBACK_B = 0
PARAM_TAIL_END_A = 1
PARAM_LUX_REF = 6
PARAM_I_MAX = 9
PARAM_LINK_TIMEOUT_S = 10

# key -> (param id, scale to Board A units, min, max, step, unit, icon)
TYPES = {
    # Where the light goes when Board B goes quiet; percent of the brightness scale.
    "link_loss_level": (PARAM_FALLBACK_B, 0.01, 0.0, 100.0, 1.0, UNIT_PERCENT, "mdi:lan-disconnect"),
    # The bottom of the brightness scale.
    "tail_end_current": (PARAM_TAIL_END_A, 1e-6, 0.5, 100.0, 0.5, UNIT_MICROAMPERE, "mdi:current-dc"),
    # Current at 100%; the XTM is rated 1.4 A.
    "full_scale_current": (PARAM_I_MAX, 1.0, 0.1, 1.4, 0.01, UNIT_AMPERE, "mdi:current-dc"),
    # Light at 100% that every fixture matches; 0 matches currents instead. Set it to the
    # lowest "full scale light" among the fixtures.
    "fleet_reference_light": (PARAM_LUX_REF, 1.0, 0.0, 1.0e6, 1.0, UNIT_LUX, "mdi:brightness-6"),
    "link_timeout": (PARAM_LINK_TIMEOUT_S, 1.0, 0.5, 30.0, 0.5, UNIT_SECOND, "mdi:timer-sand"),
}


def _schema(unit, icon):
    return number.number_schema(
        XtmNumber,
        unit_of_measurement=unit,
        icon=icon,
        entity_category=ENTITY_CATEGORY_CONFIG,
    ).extend({cv.Optional(CONF_MODE, default="BOX"): cv.enum(number.NUMBER_MODES, upper=True)})


CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_XTM_DRIVER_ID): cv.use_id(XtmDriver),
        **{
            cv.Optional(key): _schema(unit, icon)
            for key, (_, _, _, _, _, unit, icon) in TYPES.items()
        },
    }
)


async def to_code(config):
    hub = await cg.get_variable(config[CONF_XTM_DRIVER_ID])
    for key, (param, scale, lo, hi, step, _, _) in TYPES.items():
        if conf := config.get(key):
            num = await number.new_number(conf, min_value=lo, max_value=hi, step=step)
            cg.add(num.set_parent(hub))
            cg.add(num.set_param(param, scale))
            cg.add(hub.register_number(num))
