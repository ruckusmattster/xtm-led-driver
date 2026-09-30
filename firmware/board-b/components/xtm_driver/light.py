import esphome.codegen as cg
from esphome.components import light
import esphome.config_validation as cv
from esphome.const import CONF_GAMMA_CORRECT, CONF_OUTPUT_ID

from . import CONF_XTM_DRIVER_ID, XtmDriver, xtm_ns

DEPENDENCIES = ["xtm_driver"]

XtmLightOutput = xtm_ns.class_("XtmLightOutput", light.LightOutput)

CONFIG_SCHEMA = light.BRIGHTNESS_ONLY_LIGHT_SCHEMA.extend(
    {
        cv.GenerateID(CONF_OUTPUT_ID): cv.declare_id(XtmLightOutput),
        cv.GenerateID(CONF_XTM_DRIVER_ID): cv.use_id(XtmDriver),
        # Board A applies the brightness curve; anything but 1.0 would bend it twice.
        cv.Optional(CONF_GAMMA_CORRECT, default=1.0): cv.one_of(1.0, float=True),
    }
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_OUTPUT_ID])
    await light.register_light(var, config)
    hub = await cg.get_variable(config[CONF_XTM_DRIVER_ID])
    cg.add(var.set_parent(hub))
    cg.add(hub.set_light(var))
