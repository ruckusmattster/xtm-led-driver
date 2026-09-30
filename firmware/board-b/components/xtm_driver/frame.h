/* COBS framing with CRC-16/CCITT-FALSE, shared by both boards. */
#ifndef FRAME_H
#define FRAME_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

uint16_t crc16_ccitt(const uint8_t *p, size_t n);
size_t cobs_encode(const uint8_t *in, size_t n, uint8_t *out);          /* out >= n + n/254 + 1 */
size_t cobs_decode(const uint8_t *in, size_t n, uint8_t *out);          /* returns 0 on error */

/* Build a complete wire frame (COBS + trailing 0x00). Returns bytes written. */
size_t frame_build(uint8_t type, uint8_t seq, const void *payload, size_t len, uint8_t *out, size_t out_cap);

/* Streaming receiver: feed bytes, get complete, CRC-checked frames. */
typedef struct {
    uint8_t buf[80];
    size_t n;
    uint32_t bad;             /* frames dropped: CRC, COBS or length errors */
} frame_rx_t;

/* Returns decoded length (type + seq + payload, CRC stripped) when a good frame ends
 * at this byte and copies it to out; 0 otherwise. */
size_t frame_rx_byte(frame_rx_t *rx, uint8_t byte, uint8_t *out, size_t out_cap);

#ifdef __cplusplus
}
#endif

#endif
