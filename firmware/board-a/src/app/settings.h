/* Parameter get/set by id (enum link_param), shared by the link and the console. */
#ifndef SETTINGS_H
#define SETTINGS_H

#include <stdint.h>
#include "params.h"

int settings_set(params_t *p, uint8_t id, float v);     /* 0 ok, -1 bad id / read-only, -2 out of range */
int settings_get(const params_t *p, uint8_t id, float *v);
const char *settings_name(uint8_t id);
params_t *app_params(void);                              /* the live parameter block (main.c) */

#endif
