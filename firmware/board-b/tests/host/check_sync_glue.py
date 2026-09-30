#!/usr/bin/env python3
"""Type-check the ESP-NOW glue (xtm_sync.cpp) and the hub's sync paths against ESPHome's real
espnow, switch and hmac_sha256 headers, on a PC.

ESP-NOW only builds for the ESP32, so the host test leaves it out. Here the ESPHome espnow
headers are used as they are, minus their USE_ESP32 guard, over a handful of stub ESP-IDF
declarations; the component's own sources are compiled with -fsyntax-only.
Run after `esphome compile --only-generate xtm-host.yaml`.
"""
import pathlib
import subprocess
import sys
import tempfile

import esphome

HERE = pathlib.Path(__file__).resolve().parent
GEN = HERE / ".esphome/build/xtm-host/src"
PKG = pathlib.Path(esphome.__file__).resolve().parent.parent  # site-packages
COMP = HERE.parent.parent / "components/xtm_driver"

IDF_STUBS = {
    "esp_err.h": """#pragma once
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_WIFI_BASE 0x3000
""",
    "esp_idf_version.h": """#pragma once
#define ESP_IDF_VERSION_VAL(major, minor, patch) (((major) << 16) | ((minor) << 8) | (patch))
#define ESP_IDF_VERSION ESP_IDF_VERSION_VAL(5, 5, 1)
""",
    "esp_mac.h": "#pragma once\n",
    "esp_now.h": """#pragma once
#include <stdint.h>
#include "esp_err.h"
#define ESP_NOW_ETH_ALEN 6
#define ESP_NOW_MAX_DATA_LEN 250
#define ESP_NOW_MAX_DATA_LEN_V2 1470
#define ESP_ERR_ESPNOW_BASE (ESP_ERR_WIFI_BASE + 100)
#define ESP_ERR_ESPNOW_NOT_INIT (ESP_ERR_ESPNOW_BASE + 1)
#define ESP_ERR_ESPNOW_ARG (ESP_ERR_ESPNOW_BASE + 2)
#define ESP_ERR_ESPNOW_NO_MEM (ESP_ERR_ESPNOW_BASE + 3)
#define ESP_ERR_ESPNOW_FULL (ESP_ERR_ESPNOW_BASE + 4)
#define ESP_ERR_ESPNOW_NOT_FOUND (ESP_ERR_ESPNOW_BASE + 5)
#define ESP_ERR_ESPNOW_INTERNAL (ESP_ERR_ESPNOW_BASE + 6)
#define ESP_ERR_ESPNOW_EXIST (ESP_ERR_ESPNOW_BASE + 7)
#define ESP_ERR_ESPNOW_IF (ESP_ERR_ESPNOW_BASE + 8)
typedef struct { signed rssi : 8; unsigned rate : 5; unsigned timestamp : 32; } wifi_pkt_rx_ctrl_t;
typedef struct { uint8_t *src_addr; uint8_t *des_addr; wifi_pkt_rx_ctrl_t *rx_ctrl; } esp_now_recv_info_t;
typedef struct { const uint8_t *src_addr; const uint8_t *des_addr; } esp_now_send_info_t;
typedef enum { ESP_NOW_SEND_SUCCESS = 0, ESP_NOW_SEND_FAIL } esp_now_send_status_t;
""",
}


def main():
    if not GEN.exists():
        sys.exit("run: esphome compile --only-generate xtm-host.yaml")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        for name, text in IDF_STUBS.items():
            (tmp / name).write_text(text)
        dst = tmp / "esphome/components/espnow"
        dst.mkdir(parents=True)
        for name in ("espnow_component.h", "espnow_packet.h", "espnow_err.h"):
            src = (PKG / "esphome/components/espnow" / name).read_text()
            # the real declarations, without the ESP32-only guard
            src = src.replace("#ifdef USE_ESP32", "#if 1", 1)
            (dst / name).write_text(src)
        flags = ["-std=gnu++20", "-fsyntax-only", "-Wall", "-Wextra", "-Wno-unused-parameter",
                 "-DUSE_HOST", "-DESPHOME_LOG_LEVEL=ESPHOME_LOG_LEVEL_DEBUG", "-DUSE_ESPNOW", "-DUSE_SWITCH", "-DUSE_ESPNOW_MAX_PAYLOAD_SIZE=250",
                 f"-I{tmp}", f"-I{GEN}", f"-I{PKG}", f"-I{COMP}"]
        ok = True
        for src in ("xtm_sync.cpp", "xtm_driver.cpp"):
            r = subprocess.run(["g++", *flags, str(COMP / src)], capture_output=True, text=True)
            status = "ok" if r.returncode == 0 else "FAILED"
            print(f"{status:6} {src} with ESP-NOW sync and the sync switch")
            if r.stderr.strip():
                print(r.stderr)
            ok &= r.returncode == 0
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
