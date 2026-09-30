/*
 * Board A <-> Board B link protocol. Shared verbatim by the STM32 firmware and the
 * ESPHome component (both little-endian).
 *
 * UART 115200 8N1. Each frame: [type][seq][payload...][crc16 lo][crc16 hi], COBS-encoded,
 * terminated by 0x00. CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) over type..payload.
 * B sends PING at least every 500 ms; A answers each PING and each command with STATUS
 * (or ACK/PARAM), and also sends STATUS every 100 ms unprompted.
 *
 * Level ownership: B decides the level. STATUS.level_link echoes the last level A received
 * from B, so B can tell a lost SET_LEVEL (level_link differs), a reset of A (level_link = 0,
 * uptime restarted) and a link-loss fallback (LFLAG_FALLBACK) apart, and re-send only then.
 * A console `lvl` changes level_target but not level_link, so B leaves it alone.
 */
#ifndef LINK_PROTOCOL_H
#define LINK_PROTOCOL_H

#include <stdint.h>

#define LINK_BAUD        115200
#define LINK_MAX_PAYLOAD 48
#define LINK_MAX_FRAME   (2 + LINK_MAX_PAYLOAD + 2)
#define LINK_MAX_ENCODED (LINK_MAX_FRAME + LINK_MAX_FRAME / 254 + 2)

enum link_msg {
    MSG_SET_LEVEL   = 0x01,   /* B->A: level 0..65535 (0 = off), fade time */
    MSG_PING        = 0x02,   /* B->A: keep-alive, A answers with STATUS */
    MSG_HOLD        = 0x03,   /* B->A: suppress link-loss handling for N seconds (planned reboot) */
    MSG_CLEAR_FAULT = 0x04,
    MSG_SET_PARAM   = 0x05,
    MSG_GET_PARAM   = 0x06,
    MSG_IDENTIFY    = 0x07,   /* B->A: blink N times */
    MSG_STATUS      = 0x81,   /* A->B */
    MSG_ACK         = 0x82,
    MSG_PARAM       = 0x83,
};

enum link_state {
    LSTATE_BOOT = 0, LSTATE_OFF = 1, LSTATE_ON = 2, LSTATE_FAULT = 3, LSTATE_STARTING = 4, LSTATE_TAIL = 5,
};

enum link_fault {
    LFAULT_NONE = 0, LFAULT_SHORT = 1, LFAULT_OPEN = 2, LFAULT_OVERTEMP = 3, LFAULT_UNDERVOLT = 4,
    LFAULT_DAC = 5, LFAULT_BUCK = 6,
};

enum link_flag {
    LFLAG_FADING = 1u << 0, LFLAG_LINK_LOST = 1u << 1, LFLAG_HOLD = 1u << 2, LFLAG_DERATING = 1u << 3,
    LFLAG_LUX_MATCH = 1u << 4, LFLAG_CALIBRATED = 1u << 5,
    LFLAG_SEQUENCE = 1u << 6, /* a blink sequence (identify or link loss) is running; level_target moves by itself */
    LFLAG_FALLBACK = 1u << 7, /* A lost the link and dropped to its fallback level; cleared by the next SET_LEVEL */
    LFLAG_ARMED_SHIFT = 8,    /* bits 8..11: channel 1..4 armed */
};

enum link_param {
    PARAM_FALLBACK_B = 0,     /* link-loss level, 0..1 on the brightness scale (default 0.2) */
    PARAM_TAIL_END_A = 1,     /* bottom of the curve, amps (default 5e-6) */
    PARAM_LUX_I0 = 2, PARAM_LUX_V0 = 3,   /* light calibration point 1: amps, lux */
    PARAM_LUX_I1 = 4, PARAM_LUX_V1 = 5,   /* light calibration point 2: amps, lux */
    PARAM_LUX_REF = 6,        /* fleet reference lux at full scale; 0 = match on current */
    PARAM_HEADROOM_HI = 7, PARAM_HEADROOM_LO = 8,
    PARAM_I_MAX = 9,          /* amps at full scale, <= 1.4 */
    PARAM_LINK_TIMEOUT_S = 10,
    PARAM_VF_CORR = 11,       /* read-only: mean learned V_f correction */
    PARAM_LUX_AT_MAX = 12,    /* read-only: this fixture's lux at I_MAX from its calibration */
    PARAM_COUNT = 13,
};

enum link_result { RESULT_OK = 0, RESULT_BAD_FRAME = 1, RESULT_BAD_PARAM = 2, RESULT_BUSY = 3, RESULT_FAULT = 4 };

typedef struct __attribute__((packed)) { uint16_t level; uint32_t fade_ms; uint8_t flags; } msg_set_level_t;
typedef struct __attribute__((packed)) { uint16_t seconds; } msg_hold_t;
typedef struct __attribute__((packed)) { uint8_t id; float value; uint8_t save; } msg_set_param_t;
typedef struct __attribute__((packed)) { uint8_t id; } msg_get_param_t;
typedef struct __attribute__((packed)) { uint8_t count; } msg_identify_t;
typedef struct __attribute__((packed)) {
    uint16_t level_target;    /* last commanded level */
    uint16_t level_now;       /* where the fade is now */
    uint8_t state;            /* enum link_state */
    uint8_t fault;            /* enum link_fault */
    uint16_t flags;           /* enum link_flag */
    float i_led;              /* A, from the calibrated sink model */
    float v_led;              /* V, V_out - V_cathode (0 when not measurable) */
    float v_out;              /* V */
    float v_in;               /* V, the 48 V rail */
    int16_t temp_c10[4];      /* NTCs x10: FET, main buck, aux rails, precision section */
    uint16_t fw_version;
    uint32_t uptime_s;
    uint16_t level_link;      /* last level Board B commanded (0 after A's reset); survives A's link-loss fallback */
} msg_status_t;
typedef struct __attribute__((packed)) { uint8_t seq; uint8_t result; } msg_ack_t;
typedef struct __attribute__((packed)) { uint8_t id; float value; } msg_param_t;

#endif
