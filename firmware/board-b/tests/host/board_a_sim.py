"""A stand-in for Board A on a pseudo-terminal, speaking the link protocol of
firmware/board-a/src/core/link_protocol.h, for testing the ESPHome component on a PC.

It models what Board B can see: the level and its fade, level_link, the link-loss fallback,
HOLD, identify sequences, parameters and restarts. It logs every command it receives.
"""
import os
import struct
import threading
import time
import tty

MSG_SET_LEVEL, MSG_PING, MSG_HOLD, MSG_CLEAR_FAULT = 0x01, 0x02, 0x03, 0x04
MSG_SET_PARAM, MSG_GET_PARAM, MSG_IDENTIFY = 0x05, 0x06, 0x07
MSG_STATUS, MSG_ACK, MSG_PARAM = 0x81, 0x82, 0x83
LSTATE_OFF, LSTATE_ON, LSTATE_FAULT = 1, 2, 3
LFLAG_FADING, LFLAG_LINK_LOST, LFLAG_HOLD = 1, 2, 4
LFLAG_CALIBRATED, LFLAG_SEQUENCE, LFLAG_FALLBACK = 32, 64, 128
STATUS_FMT = "<HHBBHffff4hHIH"  # msg_status_t, packed, 40 bytes
assert struct.calcsize(STATUS_FMT) == 40


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    out, block = bytearray(), bytearray()
    for b in data:
        if b == 0:
            out += bytes([len(block) + 1]) + block
            block = bytearray()
        else:
            block.append(b)
            if len(block) == 254:
                out += bytes([255]) + block
                block = bytearray()
    out += bytes([len(block) + 1]) + block
    return bytes(out)


def cobs_decode(data: bytes) -> bytes | None:
    out, i, n = bytearray(), 0, len(data)
    while i < n:
        code = data[i]
        if code == 0:
            return None
        end = i + code
        if end > n:
            return None
        out += data[i + 1:end]
        i = end
        if code != 0xFF and i < n:
            out.append(0)
    return bytes(out)


def frame(type_: int, seq: int, payload: bytes = b"") -> bytes:
    body = bytes([type_, seq]) + payload
    c = crc16(body)
    return cobs_encode(body + bytes([c & 0xFF, c >> 8])) + b"\x00"


def level_to_b(level: int) -> float:
    return -1.0 if level == 0 else (level - 1) / 65534


def b_to_level(b: float) -> int:
    return 0 if b < 0 else 1 + round(min(max(b, 0.0), 1.0) * 65534)


class BoardA:
    PARAM_DEFAULTS = {0: 0.2, 1: 5e-6, 2: 0.14, 3: 85.0, 4: 1.4, 5: 850.0, 6: 0.0, 7: 1.0, 8: 0.7,
                      9: 1.4, 10: 1.5, 11: 0.0, 12: 850.0}

    def __init__(self, link: str = "/tmp/xtm-sim-pty", uptime_s: float = 0.0):
        self.master, self.slave = os.openpty()
        tty.setraw(self.slave)
        os.set_blocking(self.master, False)
        self.link = link
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink(os.ttyname(self.slave), link)
        self.lock = threading.RLock()
        self.log: list[tuple[float, int, tuple]] = []  # (time, type, decoded payload)
        self.params = dict(self.PARAM_DEFAULTS)
        self.seq = 0
        self.drop_next_set_level = False
        self.silent = False
        self.reset(uptime_s)
        self.running = True
        self.rx = bytearray()
        threading.Thread(target=self._rx_loop, daemon=True).start()
        threading.Thread(target=self._tx_loop, daemon=True).start()

    # ------------------------------------------------------------------ model
    def reset(self, uptime_s: float = 0.0):
        with self.lock:
            self.t0 = time.monotonic() - uptime_s
            self.state = LSTATE_OFF
            self.fault = 0
            self.level_target = 0
            self.level_link = 0
            self.fallback = False
            self.lost = False
            self.ever = False
            self.last_rx = time.monotonic()
            self.hold_until = 0.0
            self.seq_until = 0.0
            self._fade(0, 0.0)

    def _fade(self, level: int, fade_s: float):
        now = time.monotonic()
        self.f_from = max(self.b_now(), 0.0) if hasattr(self, "f_to") else 0.0
        self.f_to = level_to_b(level)
        self.f_t0, self.f_dur = now, fade_s
        self.level_target = level

    def b_now(self) -> float:
        now = time.monotonic()
        if self.f_to < 0:
            return -1.0 if now - self.f_t0 >= self.f_dur else self.f_from * (1 - (now - self.f_t0) / self.f_dur)
        if self.f_dur <= 0 or now - self.f_t0 >= self.f_dur:
            return self.f_to
        return self.f_from + (self.f_to - self.f_from) * (now - self.f_t0) / self.f_dur

    def uptime(self) -> int:
        return int(time.monotonic() - self.t0)

    def status_payload(self) -> bytes:
        with self.lock:
            now = time.monotonic()
            b = self.b_now()
            lvl_now = b_to_level(b)
            flags = LFLAG_CALIBRATED
            if self.f_dur > 0 and now - self.f_t0 < self.f_dur:
                flags |= LFLAG_FADING
            if self.lost:
                flags |= LFLAG_LINK_LOST
            if now < self.hold_until:
                flags |= LFLAG_HOLD
            if now < self.seq_until:
                flags |= LFLAG_SEQUENCE
            if self.fallback:
                flags |= LFLAG_FALLBACK
            i = 0.0 if b < 0 else 5e-6 * (1.4 / 5e-6) ** b
            state = LSTATE_FAULT if self.fault else (LSTATE_ON if b >= 0 else LSTATE_OFF)
            v_led = 29.9 + 1.48 * i if i > 0 else 0.0
            return struct.pack(STATUS_FMT, self.level_target, lvl_now, state, self.fault, flags, i, v_led,
                               v_led + 1.0 if i > 0 else 3.5, 48.1, 312, 355, 298, 301, 0x0100, self.uptime(),
                               self.level_link)

    # ------------------------------------------------------------------ wire
    def _send(self, type_: int, payload: bytes = b""):
        self.seq = (self.seq + 1) & 0xFF
        try:
            os.write(self.master, frame(type_, self.seq, payload))
        except (BlockingIOError, OSError):
            pass  # nobody reading the other end (Board B restarting)

    def _tx_loop(self):
        while self.running:
            time.sleep(0.1)
            with self.lock:
                self._check_link()
                if not self.silent:
                    self._send(MSG_STATUS, self.status_payload())

    def _check_link(self):
        now = time.monotonic()
        timeout = self.params[10]
        if self.ever and not self.lost and now - self.last_rx > timeout and now >= self.hold_until:
            self.lost = True
            self.fallback = True
            if self.state_on():
                fb = b_to_level(self.params[0])
                self.seq_until = now + 1.2  # two blinks, then the fallback level
                self._fade(min(self.level_target, fb) if self.level_target else fb, 2.0)

    def state_on(self) -> bool:
        return self.b_now() >= 0

    def _rx_loop(self):
        while self.running:
            try:
                data = os.read(self.master, 512)
            except BlockingIOError:
                time.sleep(0.005)
                continue
            except OSError:
                time.sleep(0.05)
                continue
            for byte in data:
                if byte != 0:
                    self.rx.append(byte)
                    continue
                raw = cobs_decode(bytes(self.rx))
                self.rx.clear()
                if raw is None or len(raw) < 4:
                    continue
                body, crc = raw[:-2], raw[-2] | (raw[-1] << 8)
                if crc16(body) != crc:
                    continue
                with self.lock:
                    self._handle(body[0], body[1], body[2:])

    def _handle(self, type_: int, seq: int, p: bytes):
        now = time.monotonic()
        self.last_rx, self.ever, self.lost = now, True, False
        if self.silent:
            return
        if type_ == MSG_SET_LEVEL:
            level, fade_ms, _ = struct.unpack("<HIB", p)
            self.log.append((now, type_, (level, fade_ms)))
            if self.drop_next_set_level:
                self.drop_next_set_level = False  # as if the frame had been corrupted on the wire
                return
            self.level_link = level
            self.fallback = False
            self.seq_until = 0.0
            if not self.fault:
                self._fade(level, fade_ms / 1000.0)
            else:
                self.level_target = level
            self._send(MSG_STATUS, self.status_payload())
        elif type_ == MSG_PING:
            self.log.append((now, type_, ()))
            self._send(MSG_STATUS, self.status_payload())
        elif type_ == MSG_HOLD:
            (s,) = struct.unpack("<H", p)
            self.log.append((now, type_, (s,)))
            self.hold_until = now + min(s, 120)
            self._send(MSG_ACK, bytes([seq, 0]))
        elif type_ == MSG_CLEAR_FAULT:
            self.log.append((now, type_, ()))
            self.fault = 0
            self._send(MSG_ACK, bytes([seq, 0]))
        elif type_ == MSG_IDENTIFY:
            (n,) = struct.unpack("<B", p)
            self.log.append((now, type_, (n,)))
            self.seq_until = now + 0.4 * n
            self._send(MSG_ACK, bytes([seq, 0]))
        elif type_ == MSG_SET_PARAM:
            pid, value, save = struct.unpack("<BfB", p)
            self.log.append((now, type_, (pid, value, save)))
            if pid not in self.params or pid in (11, 12):
                self._send(MSG_ACK, bytes([seq, 2]))
                return
            self.params[pid] = value
            self._send(MSG_PARAM, struct.pack("<Bf", pid, value))
        elif type_ == MSG_GET_PARAM:
            (pid,) = struct.unpack("<B", p)
            self.log.append((now, type_, (pid,)))
            if pid not in self.params:
                self._send(MSG_ACK, bytes([seq, 2]))
                return
            self._send(MSG_PARAM, struct.pack("<Bf", pid, self.params[pid]))

    # ------------------------------------------------------------------ test helpers
    def commands(self, type_: int, since: float = 0.0) -> list[tuple]:
        with self.lock:
            return [(t, p) for (t, ty, p) in self.log if ty == type_ and t >= since]

    def force_fallback(self):
        with self.lock:
            self.lost = False
            self.fallback = True
            self._fade(b_to_level(self.params[0]), 0.5)

    def close(self):
        self.running = False
        time.sleep(0.15)
        for fd in (self.master, self.slave):
            try:
                os.close(fd)
            except OSError:
                pass
        if os.path.lexists(self.link):
            os.unlink(self.link)
