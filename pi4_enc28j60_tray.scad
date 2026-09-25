// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

// Mounting tray for a Raspberry Pi 4: sits on four standoffs over the Pi's
// M2.5 holes and carries a generic blue ENC28J60 Ethernet module (HanRun
// HR911105A jack, 2x5 header, four ~3 mm corner holes).
//
// Coordinates match the Pi 4 mechanical drawing: origin at the board corner
// at the microSD end on the side away from the GPIO header, X along the 85 mm
// edge toward the USB/Ethernet end, Y along the 56 mm edge toward the GPIO
// header.

/* [Tray] */
tray_thickness = 3;
corner_radius  = 3;

/* [Raspberry Pi 4] */
pi_len         = 85;
pi_wid         = 56;
pi_hole_inset  = 3.5;  // hole centers 3.5 mm from the SD-card end and long edge
pi_hole_dx     = 58;   // official hole spacing
pi_hole_dy     = 49;
pi_screw_clear = 2.9;  // M2.5 clearance

/* [ENC28J60 module] */
// Measure your module with calipers and correct these -- the generic
// boards vary, and the hole spacing is not published anywhere reliable.
enc_len      = 56;     // along X (RJ45 end to header end)
enc_wid      = 34;
enc_hole_dx  = 48;     // center-to-center, along X
enc_hole_dy  = 27;     // center-to-center, along Y
enc_pilot    = 2.6;    // pilot for an M3 screw tapping into plastic
boss_dia     = 6.5;
boss_height  = 4;      // lifts the PCB so through-hole solder joints clear
enc_edge_gap = 1;      // RJ45 end of module to the tray's USB/Ethernet edge

/* [GPIO wire notch] */
gpio_notch    = true;
gpio_notch_x0 = 8;     // GPIO header spans roughly x = 7..58
gpio_notch_x1 = 57;
gpio_notch_y0 = 47;

$fn = 48;

// Module placed with its RJ45 toward the Pi's USB/Ethernet end, centered in Y.
enc_origin = [pi_len - enc_edge_gap - enc_len, (pi_wid - enc_wid) / 2];
enc_hole_c = enc_origin + [enc_len / 2, enc_wid / 2];

function pi_holes() = [
  for (i = [0, 1], j = [0, 1])
    [pi_hole_inset + i * pi_hole_dx, pi_hole_inset + j * pi_hole_dy]
];

function enc_holes() = [
  for (i = [-1, 1], j = [-1, 1])
    enc_hole_c + [i * enc_hole_dx / 2, j * enc_hole_dy / 2]
];

module rounded_plate(size, r, h) {
  linear_extrude(h)
    offset(r) offset(-r) square(size);
}

module tray() {
  difference() {
    union() {
      rounded_plate([pi_len, pi_wid], corner_radius, tray_thickness);
      for (p = enc_holes())
        translate(p) cylinder(d = boss_dia, h = tray_thickness + boss_height);
    }
    for (p = pi_holes())
      translate([p.x, p.y, -1])
        cylinder(d = pi_screw_clear, h = tray_thickness + 2);
    for (p = enc_holes())
      translate([p.x, p.y, -1])
        cylinder(d = enc_pilot, h = tray_thickness + boss_height + 2);
    if (gpio_notch)
      translate([gpio_notch_x0, gpio_notch_y0, -1])
        cube([gpio_notch_x1 - gpio_notch_x0, pi_wid, tray_thickness + 2]);
  }
}

// Fail the render if a parameter change makes parts collide.
assert(enc_origin.x >= 0, "ENC28J60 module overhangs the SD-card end");
for (e = enc_holes())
  assert(e.x + boss_dia / 2 <= pi_len && e.x - boss_dia / 2 >= 0 &&
         e.y + boss_dia / 2 <= pi_wid && e.y - boss_dia / 2 >= 0,
         str("ENC boss at ", e, " hangs off the tray; raise enc_edge_gap"));
for (e = enc_holes(), p = pi_holes())
  assert(norm(e - p) > boss_dia / 2 + 3,
         str("ENC boss at ", e, " collides with Pi standoff at ", p));

tray();
