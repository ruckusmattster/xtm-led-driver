/*
 * Board A link: framing and message layouts.
 *
 * frame.h, frame_c.h (Board A's frame.c) and link_protocol.h are verbatim copies of
 * firmware/board-a/src/core; `make -C tests` fails if they drift. The framing functions
 * are renamed here so their generic names cannot collide with anything in ESP-IDF.
 */
#pragma once

#define crc16_ccitt xtm_crc16_ccitt
#define cobs_encode xtm_cobs_encode
#define cobs_decode xtm_cobs_decode
#define frame_build xtm_frame_build
#define frame_rx_byte xtm_frame_rx_byte

#include "frame.h"
#include "link_protocol.h"
