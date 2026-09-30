# Board A firmware (STM32G431CBU6)

Bare-metal C on ST's LL drivers. Runs the four sinks, the tracking buck, fades, crossovers,
headroom, protection, the link to Board B and a calibration console.

## Layout

| Path | What |
| --- | --- |
| `src/main.c` | Start-up order and the main loop |
| `src/app/control.c` | The controller: 4 kHz tick (fades, crossovers, V_out lead, sink codes), fault handling, headroom learning, blink sequences |
| `src/app/link.c` | Board B protocol (COBS + CRC-16 frames, see `src/core/link_protocol.h`) and link-loss handling |
| `src/app/console.c` | Calibration and bring-up console on the STLINK virtual COM port |
| `src/app/settings.c` | Parameters settable from Board B or the console |
| `src/core/` | Portable logic with host tests: brightness curve and light matching, channel calibration and blend, fade engine, LED model, framing, parameter storage format |
| `src/hw/` | Everything that touches a register |
| `third_party/` | CMSIS core, the G4 device header and startup file, and the LL headers, with their licences (`VERSIONS.txt` records the upstream commits) |
| `tests/` | Host tests for `src/core` |
| `tools/calibrate.py` | Current and light calibration over the console |

## Build

Needs CMake 3.20 or later, Ninja or Make, and `arm-none-eabi-gcc` 12 or later. The Arm GNU
Toolchain or the xPack build both work; the firmware was compiled here with xPack GCC 14.2.1.

```sh
cmake -B build -G Ninja -DCMAKE_TOOLCHAIN_FILE=cmake/arm-none-eabi.cmake
cmake --build build
```

That gives `build/board_a.elf`, `.bin` and `.hex`, 50–58 KB of the 126 KB available depending on
the toolchain. The last
2 KB page of flash holds the calibration and settings.

If the toolchain isn't on your PATH, add `-DARM_TOOLCHAIN_DIR=/path/to/toolchain/bin` to the first command.

Host tests (any C compiler; they run under AddressSanitizer):

```sh
make -C tests
```

## Flash

Plug the STLINK-V3MINIE into J4 (STDC14; its cable is keyed) and power Board A from 48 V.
The STLINK senses the target's voltage but does not power it. Any one of these works:

```sh
# STM32CubeProgrammer
STM32_Programmer_CLI -c port=SWD mode=UR -w build/board_a.elf -v -rst
# OpenOCD
openocd -f interface/stlink.cfg -f target/stm32g4x.cfg -c "program build/board_a.elf verify reset exit"
# pyOCD
pyocd flash -t stm32g431cbux build/board_a.elf
```

The factory option bytes are what this design expects. Leave nSWBOOT0 = 1 so the PB8/BOOT0
pin decides boot mode: that is how Board B can put Board A in its ROM bootloader through the
ribbon later. Check them with `STM32_Programmer_CLI -c port=SWD -ob displ`.

## Console

The console runs on the same STLINK's virtual COM port at 115200 8N1. Every command answers
with `key=value` lines and ends with a line starting `ok` or `err`.

| Command | Does |
| --- | --- |
| `st` | One status line: state, level, current, V_out, cathode, 48 V, codes, gate monitors, temperatures, link |
| `lvl L [ms]`, `b pos [ms]`, `off` | Set a level (0-65535, or 0-1 on the curve) with an optional fade |
| `raw ch code`, `rawi ch amps`, `ka ch`, `dark`, `exit` | Calibration mode: one channel alone at a DAC code, at a current, at its keep-alive, or all off; `exit` leaves |
| `cal ch amps` | Record the measured current for the raw channel's present code. Two points replace the channel's model; a third low point is its keep-alive |
| `calreset ch`, `calshow`, `dark_a amps` | Calibration housekeeping |
| `set id value`, `get id`, `params` | Settings (ids in `src/core/link_protocol.h`, `enum link_param`) |
| `save` | Write calibration and settings to flash. The write waits until the light is off or below 10 mA, because erasing flash stalls the CPU for about 20 ms |
| `vf`, `clear`, `id [n]`, `defaults`, `reboot` | Learned V_f table, clear a latched fault, blink to identify, factory defaults (not saved), restart |

## Calibration

See [the build guide, "Calibrate"](../../docs/BUILD_GUIDE.md#12-calibrate), or section "Calibration" of
[the Phase 2 design](../../docs/design-record/phase2-detailed-design.md#calibration). In short:

```sh
pip install pyserial        # and pyvisa for a SCPI meter
python3 tools/calibrate.py current --port /dev/ttyACM0 [--dmm VISA-resource]
python3 tools/calibrate.py lux --port /dev/ttyACM0
python3 tools/calibrate.py fleet --port /dev/ttyACM0 --ref <lux>
```
