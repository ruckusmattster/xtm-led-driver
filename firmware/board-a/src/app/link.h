/* Board B link: frame handling, status reports, link-loss detection. */
#ifndef LINK_H
#define LINK_H

#include <stdint.h>

void link_init(void);
void link_poll(void);          /* main loop */
int link_is_lost(void);
uint32_t link_bad_frames(void);

#endif
