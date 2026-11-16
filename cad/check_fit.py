"""Interference and sanity checks for the Nod case against catalog-size part blocks."""
import itertools
import cadquery as cq
import trimesh
import nod_case as n

box = n.box
shell, lid = n.make_shell(), n.make_lid()
cap_rest, cap_down = n.make_keycap(), n.make_keycap(pressed=True)
# the legs ride inside the switch stem, so test the cap body without them against the switch
_legs = box(-n.LEG_PITCH/2 - 1, n.LEG_PITCH/2 + 1, n.KEY_CY - n.LEG_D/2 - 0.01, n.KEY_CY + n.LEG_D/2 + 0.01, -20, n.CAP_PROUD - n.CAP_TOP_T - 0.001)
cap_rest_body, cap_down_body = cap_rest.cut(_legs), cap_down.cut(_legs.translate((0, 0, -n.TRAVEL)))

parts = {
    # Waveshare 1.47in module: 22.0 x 38.5; thickness unknown, 4 mm assumed for glass + PCB
    "screen module": box(-n.MOD_W / 2, n.MOD_W / 2, n.MOD_Y1 - n.MOD_L, n.MOD_Y1, -n.FRONT - 4.0, -n.FRONT),
    # Choc v1 above the plate: 15 x 15 flange up to 2.8 mm; below: 13.8 sq to 2.2 mm under plate top; centre post 3 mm more
    "switch top": box(-7.5, 7.5, n.KEY_CY - 7.5, n.KEY_CY + 7.5, n.PLATE_TOP_Z, n.PLATE_TOP_Z + 2.8),
    "switch bottom": box(-6.85, 6.85, n.KEY_CY - 6.85, n.KEY_CY + 6.85, n.PLATE_TOP_Z - 2.2, n.PLATE_TOP_Z),
    "switch post+pins": box(-6.0, 6.0, n.KEY_CY - 6.0, n.KEY_CY + 6.0, n.PLATE_TOP_Z - 5.2, n.PLATE_TOP_Z - 2.2),
    "battery": box(-n.BAT[0] / 2, n.BAT[0] / 2, n.BAT_Y0, n.BAT_Y0 + n.BAT[1], n.BAT_Z_FRONT - n.BAT[2], n.BAT_Z_FRONT),
    "xiao pcb": box(-n.XIAO_W / 2, n.XIAO_W / 2, n.XIAO_Y0, n.XIAO_Y0 + n.XIAO_L, n.xiao_bot_z, n.xiao_bot_z + n.XIAO_PCB),
    "xiao usb-c": box(-n.USB_W / 2, n.USB_W / 2, n.XIAO_Y0 - 0.8, n.XIAO_Y0 + 6.5,
                      n.usb_cz - n.USB_T / 2, n.usb_cz + n.USB_T / 2),
    "xiao parts (2 mm)": box(-n.XIAO_W / 2 + 1, n.XIAO_W / 2 - 1, n.XIAO_Y0 + 7, n.XIAO_Y0 + n.XIAO_L,
                             n.xiao_bot_z + n.XIAO_PCB, n.xiao_bot_z + n.XIAO_PCB + 2.0),
}
for side, sx in (("R", 1), ("L", -1)):
    x_out = sx * n.W / 2
    x_in = sx * (n.W / 2 - n.CONN_IN)
    parts[f"connector {side}"] = box(min(x_in, x_out), max(x_in, x_out),
                                     n.CONN_CY - n.CONN_L / 2, n.CONN_CY + n.CONN_L / 2,
                                     -n.SHELL_D, -n.SHELL_D + n.CONN_T)
    for y in n.MAG_YS:
        parts[f"magnet {side}{y}"] = (cq.Workplane("YZ").workplane(offset=(n.W / 2 - 1.59) if sx > 0 else -n.W / 2)
                                     .center(y, n.MAG_Z).circle(6.35 / 2).extrude(1.59))

def vol(a, b):
    try:
        v = a.intersect(b).val().Volume()
    except Exception:
        v = 0.0
    return v

fails = 0
print("== parts vs printed parts (mm^3, want ~0)")
for name, p in parts.items():
    for pn, printed in (("shell", shell), ("lid", lid), ("cap rest", cap_rest_body), ("cap pressed", cap_down_body)):
        v = vol(p, printed)
        if v > 0.01:
            fails += 1
            print(f"  CLASH {name} x {pn}: {v:.3f}")
print("== parts vs parts")
for (a, pa), (b, pb) in itertools.combinations(parts.items(), 2):
    v = vol(pa, pb)
    if v > 0.01:
        fails += 1
        print(f"  CLASH {a} x {b}: {v:.3f}")
print("== keycap vs case")
for pn, c in (("rest", cap_rest), ("pressed", cap_down)):
    for qn, q in (("shell", shell), ("lid", lid)):
        v = vol(c, q)
        print(f"  cap {pn} x {qn}: {v:.4f}")
        if v > 0.01:
            fails += 1

# mating check: shell + lid fill the envelope without overlapping
print("== shell x lid overlap:", round(vol(shell, lid), 4))
bb = shell.union(lid).val().BoundingBox()
print(f"== assembled envelope: {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm")
for f in ["nod_shell.stl", "nod_lid.stl", "nod_keycap_leg1.28.stl"]:
    m = trimesh.load(f"{f}")
    print(f"== {f}: watertight={m.is_watertight} volume={m.volume:.0f} mm^3 extents={[round(e,2) for e in m.extents]}")
print("FAILS", fails)
