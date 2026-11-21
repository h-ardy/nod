"""
Nod module case, parametric CadQuery model.

Axes (mm):  X = width (left/right), Y = height (0 = bottom end, USB-C side),
            Z = depth (0 = front face, negative toward the back).

Parts: shell (front + walls), lid (back plate), keycap (Choc v1 legs).
Run:   python3 nod_case.py      -> writes STL + STEP files into ./out
"""
import os
import cadquery as cq

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

# ---------------------------------------------------------------- envelope
W, H, D = 25.4, 76.2, 25.4          # 1 x 3 x 1 in
EDGE_R = 1.5                         # outer edge round
WALL_SIDE = 1.4                      # left/right walls
WALL_END = 2.0                       # top/bottom walls
FRONT = 2.0                          # front wall
LID_T = 1.6                          # back lid
SHELL_D = D - LID_T                  # 23.8
IN_X = W / 2 - WALL_SIDE             # 11.3 (inner half width)
Y_IN0, Y_IN1 = WALL_END, H - WALL_END

# ---------------------------------------------------------------- screen (Waveshare 1.47in LCD Module, 22.0 x 38.5 mm)
MOD_W, MOD_L, FIT = 22.0, 38.5, 0.3
MOD_Y1 = Y_IN1                       # module top end touches the top wall
MOD_Y0 = MOD_Y1 - (MOD_L + FIT)      # stop tabs sit here
MOD_CY = (MOD_Y0 + MOD_Y1) / 2
WIN_W, WIN_H = 18.4, 33.4            # visible area of the 1.47in panel
WIN_DY = 0.0                         # shift the window if your module's glass is off-centre
BEZEL = 0.5                          # stepped bevel around the window

# ---------------------------------------------------------------- key (Kailh Choc v1, PG1350)
KEY_CY = 18.2
CAP_W, CAP_H, CAP_R = 21.0, 24.0, 2.0
CAP_CLR = 0.3
OPEN_W, OPEN_H = CAP_W + 2 * CAP_CLR, CAP_H + 2 * CAP_CLR
WELL_WALL = 1.2
PLATE_T = 1.2                        # Choc plate thickness
SW_CUT = 13.8 + 0.1                  # Choc plate cut-out + print allowance
SACRIFICIAL_T = float(os.environ.get("NOD_SAC", "0.2"))                  # one 0.2 mm layer bridged over the switch hole (cut it out after printing)
STEM_TOP_ABOVE_PLATE = 5.8           # PG1350 drawing
CAP_PROUD = 0.3                      # cap top sits this far above the front face at rest
CAP_TOP_T = 1.4
CAP_SKIRT, CAP_SKIRT_DEPTH = 1.2, 1.5
LEG_D, LEG_PITCH, LEG_LEN = 3.0, 5.7, 3.0
FDM_LEGS = (1.20, 1.28, 1.35)        # the drawing's leg sizes, which fit the switch when printed in PLA
TRAVEL = 3.0
cap_under_z = CAP_PROUD - CAP_TOP_T                     # -1.1
PLATE_TOP_Z = cap_under_z - STEM_TOP_ABOVE_PLATE        # -6.9
PLATE_BOT_Z = PLATE_TOP_Z - PLATE_T                     # -8.1
WELL_Y0 = KEY_CY - OPEN_H / 2 - WELL_WALL
WELL_Y1 = KEY_CY + OPEN_H / 2 + WELL_WALL

# ---------------------------------------------------------------- battery (Adafruit 2750, 36 x 19.6 x 5.2)
BAT = (19.6, 36.0, 5.2)
BAT_Y0 = 36.2
BAT_Z_FRONT = -10.4

# ---------------------------------------------------------------- XIAO nRF52840 (21 x 17.8)
XIAO_W, XIAO_L, XIAO_PCB = 17.8, 21.0, 1.2
XIAO_STANDOFF = 2.0
XIAO_Y0 = 3.1
xiao_bot_z = -SHELL_D + XIAO_STANDOFF                   # -21.8
USB_W, USB_T = 8.94, 3.26
usb_cz = xiao_bot_z + XIAO_PCB + USB_T / 2              # about -19.0
USB_OPEN = (9.6, 4.4)
USB_RECESS = (12.8, 7.2, 1.2)            # pocket for the cable plug, so the plug reaches the board

# ---------------------------------------------------------------- side connectors (Adafruit 5358, 21 x 7 x 7) and magnets (K&J D41-N52)
CONN_L, CONN_T, CONN_IN, CONN_CLR = 21.0, 7.0, 7.0, 0.3
CONN_CY = 45.7
MAG_D, MAG_T = 6.35 + 0.2, 1.59 + 0.16
MAG_YS = (30.2, 66.0)
MAG_Z = -19.8
MAG_BOSS_R, MAG_BOSS_IN = 3.9, 1.0

# ---------------------------------------------------------------- lid fixing: one M2 screw at the top, two hooks at the bottom
SCREW_Y, BOSS_R, PILOT_R = 72.7, 2.5, 0.85
BOSS_FRONT_Z = -18.0                  # leaves room for batteries up to 20 x 36 x 7.5 mm
HOOK_X = (6.8, 10.2)
HOOK_Z = (-22.6, -21.8)


def box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY")
            .box(x1 - x0, y1 - y0, z1 - z0, centered=False)
            .translate((x0, y0, z0)))


def rrect_z(w, h, r, cx, cy, z0, z1):
    """Rounded rectangle prism along Z."""
    return (cq.Workplane("XY").workplane(offset=z0).center(cx, cy)
            .rect(w, h).extrude(z1 - z0).edges("|Z").fillet(r))


def mirror_x(solid):
    return solid.union(solid.mirror("YZ"))


def body():
    b = box(-W / 2, W / 2, 0, H, -D, 0)
    return b.edges().fillet(EDGE_R)


def make_shell():
    outer = body().intersect(box(-W, W, -1, H + 1, -SHELL_D, 1))
    s = outer.cut(box(-IN_X, IN_X, Y_IN0, Y_IN1, -SHELL_D - 1, -FRONT))

    # key well + integral Choc plate
    well = box(-IN_X, IN_X, WELL_Y0, WELL_Y1, PLATE_BOT_Z, -FRONT)
    s = s.union(well)
    # screen stop tabs at the bottom end of the module (middle left open for its cable)
    tab = box(IN_X - 3.0, IN_X, MOD_Y0 - 1.0, MOD_Y0, -5.0, -FRONT)
    s = s.union(mirror_x(tab))
    # magnet bosses
    for y in MAG_YS:
        boss = (cq.Workplane("YZ").workplane(offset=IN_X - MAG_BOSS_IN)
                .center(y, MAG_Z).circle(MAG_BOSS_R).extrude(MAG_BOSS_IN + 0.01))
        s = s.union(mirror_x(boss))
    # lid screw boss, merged into the top wall
    boss = (cq.Workplane("XY").workplane(offset=-SHELL_D).center(0, SCREW_Y)
            .circle(BOSS_R).extrude(SHELL_D + BOSS_FRONT_Z))
    s = s.union(boss)
    # (no gusset: the battery end sits right under this boss; its 4 mm overhang prints fine as a short bridge)

    # ---- cuts
    s = s.cut(rrect_z(OPEN_W, OPEN_H, CAP_R + CAP_CLR, 0, KEY_CY, PLATE_TOP_Z, 1))
    s = s.cut(box(-SW_CUT / 2, SW_CUT / 2, KEY_CY - SW_CUT / 2, KEY_CY + SW_CUT / 2,
                  PLATE_BOT_Z - 1, PLATE_TOP_Z + 0.01))
    if SACRIFICIAL_T > 0:
        # One thin layer across the switch hole, on the plate's front side. Printed face down, the plate
        # ring would otherwise start in mid air and sag into strings. This layer prints as one bridge
        # between the well walls, the ring stacks on top of it, and you cut it out with a hobby knife.
        s = s.union(box(-SW_CUT / 2 - 0.01, SW_CUT / 2 + 0.01, KEY_CY - SW_CUT / 2 - 0.01, KEY_CY + SW_CUT / 2 + 0.01,
                        PLATE_TOP_Z - SACRIFICIAL_T, PLATE_TOP_Z))
    wy = MOD_CY + WIN_DY
    s = s.cut(rrect_z(WIN_W, WIN_H, 1.0, 0, wy, -FRONT - 1, 1))
    s = s.cut(rrect_z(WIN_W + 2 * BEZEL, WIN_H + 2 * BEZEL, 1.4, 0, wy, -BEZEL, 1))
    for y in MAG_YS:
        pocket = (cq.Workplane("YZ").workplane(offset=W / 2 - MAG_T)
                  .center(y, MAG_Z).circle(MAG_D / 2).extrude(MAG_T + 1))
        s = s.cut(mirror_x(pocket))
    slot = box(IN_X - 1, W / 2 + 1,
               CONN_CY - (CONN_L + CONN_CLR) / 2, CONN_CY + (CONN_L + CONN_CLR) / 2,
               -SHELL_D - 1, -SHELL_D + CONN_T + CONN_CLR)
    s = s.cut(mirror_x(slot))
    # XZ workplane normal is -Y: start 1 mm outside the bottom wall (y = -1) and cut through it toward +Y
    usb = (cq.Workplane("XZ").workplane(offset=1)
           .center(0, usb_cz).rect(*USB_OPEN).extrude(-(WALL_END + 2))
           .edges("|Y").fillet(1.6))
    s = s.cut(usb)
    rec = (cq.Workplane("XZ").workplane(offset=1)
           .center(0, usb_cz).rect(USB_RECESS[0], USB_RECESS[1]).extrude(-(1 + USB_RECESS[2]))
           .edges("|Y").fillet(2.5))
    s = s.cut(rec)
    groove = box(HOOK_X[0] - 0.2, HOOK_X[1] + 0.2, Y_IN0 - 0.9, Y_IN0 + 0.1,
                 HOOK_Z[0] - 0.1, HOOK_Z[1] + 0.1)
    s = s.cut(mirror_x(groove))
    s = s.cut(cq.Workplane("XY").workplane(offset=-SHELL_D - 1).center(0, SCREW_Y)
              .circle(PILOT_R).extrude(8.5))
    return s


def make_lid():
    lid = body().intersect(box(-W, W, -1, H + 1, -D - 1, -SHELL_D))
    top = -SHELL_D
    # XIAO standoffs under the board edges + side rails
    st = box(XIAO_W / 2 - 1.5, XIAO_W / 2 - 0.5, XIAO_Y0 + 1, XIAO_Y0 + XIAO_L - 1, top, top + XIAO_STANDOFF)
    rail = box(XIAO_W / 2 + 0.2, XIAO_W / 2 + 1.2, XIAO_Y0, XIAO_Y0 + XIAO_L,
               top, top + XIAO_STANDOFF + XIAO_PCB)
    lid = lid.union(mirror_x(st)).union(mirror_x(rail))
    # bottom hooks (vertical leg + nose that enters the groove in the bottom wall)
    leg = box(HOOK_X[0], HOOK_X[1], Y_IN0 + 0.1, Y_IN0 + 0.9, top - 0.01, HOOK_Z[1])
    nose = box(HOOK_X[0], HOOK_X[1], Y_IN0 - 0.7, Y_IN0 + 0.1, HOOK_Z[0], HOOK_Z[1])
    lid = lid.union(mirror_x(leg)).union(mirror_x(nose))
    # screw clearance + counterbore
    lid = lid.cut(cq.Workplane("XY").workplane(offset=-D - 1).center(0, SCREW_Y).circle(1.15).extrude(4))
    lid = lid.cut(cq.Workplane("XY").workplane(offset=-D - 1).center(0, SCREW_Y).circle(2.1).extrude(2.0))
    return lid


def make_keycap(leg_t=1.28, pressed=False, leg_d=None, tip=0.0, dish=True):
    """Keycap in its installed position (at rest, or pressed by TRAVEL)."""
    top = CAP_PROUD
    under = top - CAP_TOP_T
    cap = rrect_z(CAP_W, CAP_H, CAP_R, 0, KEY_CY, under, top)
    cap = cap.faces(">Z").edges().chamfer(0.5)
    skirt = rrect_z(CAP_W, CAP_H, CAP_R, 0, KEY_CY, under - CAP_SKIRT_DEPTH, under + 0.01)
    skirt = skirt.cut(rrect_z(CAP_W - 2 * CAP_SKIRT, CAP_H - 2 * CAP_SKIRT,
                              max(CAP_R - CAP_SKIRT, 0.3), 0, KEY_CY, under - 5, under + 1))
    cap = cap.union(skirt)
    # shallow finger dish, 0.35 mm deep
    dish_r = 60.0
    dish_cut = (cq.Workplane("YZ").workplane(offset=-W).center(KEY_CY, top + dish_r - 0.35)
            .circle(dish_r).extrude(2 * W))
    if dish:
        # Face down on a filament printer the dish would leave the middle of the face in mid air, so
        # the FDM caps skip it and stay flat on the bed.
        cap = cap.cut(dish_cut)
    for sx in (-1, 1):
        x = sx * LEG_PITCH / 2
        ld = leg_d or LEG_D
        leg = box(x - leg_t / 2, x + leg_t / 2, KEY_CY - ld / 2, KEY_CY + ld / 2, under - LEG_LEN, under + 0.01)
        if tip > 0:
            leg = leg.faces("<Z").edges("|Y").chamfer(min(tip, leg_t / 2 - 0.05))
        cap = cap.union(leg)
    if pressed:
        cap = cap.translate((0, 0, -TRAVEL))
    return cap


def export_stl(shape, path, tol=0.02):
    """Export, then drop the sliver triangles OCC leaves at fillet corners so the mesh is watertight."""
    cq.exporters.export(shape, path, tolerance=tol, angularTolerance=0.1)
    try:
        import trimesh
        m = trimesh.load(path)
        m.merge_vertices(digits_vertex=4)
        parts = m.split(only_watertight=False)
        m = max(parts, key=lambda p: len(p.faces))
        trimesh.repair.fill_holes(m)
        trimesh.repair.fix_normals(m)
        m.export(path)
        return m.is_watertight
    except ImportError:
        return None


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    shell, lid = make_shell(), make_lid()
    # print orientation: front face (screen side) flat on the bed, open back facing up
    shell_print = shell.rotate((0, 0, 0), (0, 1, 0), 180)
    print("shell watertight:", export_stl(shell_print, os.path.join(OUT, "nod_shell.stl")))
    print("lid watertight:", export_stl(lid.translate((0, 0, D)), os.path.join(OUT, "nod_lid.stl")))
    # Filament (FDM): flat top, so the whole face sits on the bed when printed face down.
    # Printed in PLA, all three of these leg sizes fit the switch.
    for t in FDM_LEGS:
        cap = make_keycap(t, dish=False)
        flat = cap.translate((0, -KEY_CY, -CAP_PROUD)).rotate((0, 0, 0), (1, 0, 0), 180)
        print(f"keycap fdm {t} watertight:", export_stl(flat, os.path.join(OUT, f"nod_keycap_fdm_leg{t:.2f}.stl"), 0.01))
    # Resin prints true to size: the drawing's own leg sizes
    for t in (1.20, 1.28):
        cap = make_keycap(t)
        flat = cap.translate((0, -KEY_CY, -CAP_PROUD)).rotate((0, 0, 0), (1, 0, 0), 180)
        print(f"keycap resin {t} watertight:", export_stl(flat, os.path.join(OUT, f"nod_keycap_resin_leg{t:.2f}.stl"), 0.01))
    asm = (cq.Assembly(name="nod_module")
           .add(shell, name="shell", color=cq.Color(0.12, 0.12, 0.13))
           .add(lid, name="lid", color=cq.Color(0.2, 0.2, 0.22))
           .add(make_keycap(), name="keycap", color=cq.Color(0.85, 0.47, 0.34)))
    asm.save(os.path.join(OUT, "nod_module_assembly.step"))
    cq.exporters.export(shell, os.path.join(OUT, "nod_shell.step"))
    cq.exporters.export(lid, os.path.join(OUT, "nod_lid.step"))
    cq.exporters.export(make_keycap(), os.path.join(OUT, "nod_keycap.step"))
    print("done", OUT)
