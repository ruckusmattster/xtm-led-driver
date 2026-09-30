#include "frame.h"
#include <string.h>

uint16_t crc16_ccitt(const uint8_t *p, size_t n)
{
    uint16_t crc = 0xFFFF;
    while (n--) {
        crc ^= (uint16_t)(*p++) << 8;
        for (int i = 0; i < 8; i++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}

size_t cobs_encode(const uint8_t *in, size_t n, uint8_t *out)
{
    size_t read = 0, write = 1, code_idx = 0;
    uint8_t code = 1;
    while (read < n) {
        if (in[read] == 0) {
            out[code_idx] = code;
            code = 1;
            code_idx = write++;
            read++;
        } else {
            out[write++] = in[read++];
            code++;
            if (code == 0xFF) {
                out[code_idx] = code;
                code = 1;
                code_idx = write++;
            }
        }
    }
    out[code_idx] = code;
    return write;
}

size_t cobs_decode(const uint8_t *in, size_t n, uint8_t *out)
{
    size_t read = 0, write = 0;
    while (read < n) {
        uint8_t code = in[read++];
        if (code == 0)
            return 0;
        for (uint8_t i = 1; i < code; i++) {
            if (read >= n)
                return 0;               /* truncated block */
            uint8_t b = in[read++];
            if (b == 0)
                return 0;
            out[write++] = b;
        }
        if (code != 0xFF && read < n)
            out[write++] = 0;           /* implied zero between blocks */
    }
    return write;
}

size_t frame_build(uint8_t type, uint8_t seq, const void *payload, size_t len, uint8_t *out, size_t out_cap)
{
    uint8_t raw[2 + 64 + 2];
    if (len > 64)
        return 0;
    raw[0] = type;
    raw[1] = seq;
    if (len)
        memcpy(&raw[2], payload, len);
    uint16_t crc = crc16_ccitt(raw, 2 + len);
    raw[2 + len] = (uint8_t)(crc & 0xFF);
    raw[3 + len] = (uint8_t)(crc >> 8);
    size_t raw_n = 4 + len;
    if (out_cap < raw_n + raw_n / 254 + 2)
        return 0;
    size_t n = cobs_encode(raw, raw_n, out);
    out[n++] = 0x00;
    return n;
}

size_t frame_rx_byte(frame_rx_t *rx, uint8_t byte, uint8_t *out, size_t out_cap)
{
    if (byte != 0x00) {
        if (rx->n < sizeof(rx->buf))
            rx->buf[rx->n++] = byte;
        else
            rx->n = sizeof(rx->buf) + 1;      /* overflow: drop until the delimiter */
        return 0;
    }
    size_t n = rx->n;
    rx->n = 0;
    if (n == 0)
        return 0;
    if (n > sizeof(rx->buf)) {
        rx->bad++;
        return 0;
    }
    uint8_t dec[80];
    size_t m = cobs_decode(rx->buf, n, dec);
    if (m < 4) {
        rx->bad++;
        return 0;
    }
    uint16_t crc = (uint16_t)(dec[m - 2] | (dec[m - 1] << 8));
    if (crc != crc16_ccitt(dec, m - 2) || m - 2 > out_cap) {
        rx->bad++;
        return 0;
    }
    memcpy(out, dec, m - 2);
    return m - 2;
}
