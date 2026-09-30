import esphome.codegen as cg
from esphome.components import switch
import esphome.config_validation as cv

from . import CONF_SYNC, CONF_XTM_DRIVER_ID, XtmDriver, xtm_ns

DEPENDENCIES = ["xtm_driver"]

XtmSyncSwitch = xtm_ns.class_("XtmSyncSwitch", switch.Switch)

CONF_SYNC_LEAD = "sync_lead"

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(CONF_XTM_DRIVER_ID): cv.use_id(XtmDriver),
        # On while this fixture leads the group; turn on to take the lead, off to end the group.
        cv.Optional(CONF_SYNC_LEAD): switch.switch_schema(
            XtmSyncSwitch, icon="mdi:link-variant", default_restore_mode="DISABLED"
        ),
    }
)


def _final_validate(config):
    import esphome.final_validate as fv

    if CONF_SYNC_LEAD in config:
        hubs = fv.full_config.get().get("xtm_driver", [])
        hubs = hubs if isinstance(hubs, list) else [hubs]
        if not any(CONF_SYNC in h for h in hubs):
            raise cv.Invalid("sync_lead needs 'sync:' configured under xtm_driver")
    return config


FINAL_VALIDATE_SCHEMA = _final_validate


async def to_code(config):
    hub = await cg.get_variable(config[CONF_XTM_DRIVER_ID])
    if conf := config.get(CONF_SYNC_LEAD):
        sw = await switch.new_switch(conf)
        cg.add(sw.set_parent(hub))
        cg.add(hub.set_sync_switch(sw))
