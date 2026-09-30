# XTM footprints

`ESP32-S3-Zero_Socket.kicad_mod`: Board B's U1, a Waveshare ESP32-S3-Zero plugged into two 1x9
2.54 mm female headers 15.24 mm apart (Waveshare's own figure for the row spacing). Drawn for this
project, as seen from the side the module is on; Board B puts it on the bottom.

- Pin order, top view with the USB-C end up: left column 1-9 from the USB end (5V, GND, 3V3,
  GP1-GP6), right column 10-18 from the antenna end (GP7-GP13, RX/GP44, TX/GP43). Checked against
  Waveshare's product photo and the community footprint at github.com/jtomka/kicad-esp32-s3-zero.
- Holes 1.0 mm, pads 1.7 mm, as KiCad's PinSocket_1x09_P2.54mm_Vertical.
- A copper keep-out (no tracks, vias or pours, both layers) under the ceramic antenna across the
  module's far end.

Print the board 1:1 and lay the module on it before ordering.
