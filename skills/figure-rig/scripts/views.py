# views.py: straight-on orthographic views of a sculpt with a millimetre grid, for marking fit.json's joints and props.
#
#   blender -b --factory-startup --python views.py -- <sculpt.glb> <out-prefix> [--fit fit.json] [--px 1400] [--grid 1]
#
# Writes <out-prefix>-front.png (looking at the figure's face: +X is the figure's left, on the right of the picture),
# -left.png (from the figure's left side: -Y, its front, on the right), -top.png, and <out-prefix>-views.json with
# each picture's millimetre range so a pixel can be read back as a coordinate. Grid lines every --grid mm (faint) and
# every 10 x --grid (strong). With --fit, every joint is drawn as a dot (left side green, right red, centre yellow),
# props' boxes as outlines in cyan, so a marking can be checked against the figure before rigging.
# Millimetres are the sculpt's units x 1000, Z up, as Blender imports a glTF: the same space fit.json uses.
import sys, os, json, argparse, math

ap = argparse.ArgumentParser(prog="views.py", description="Orthographic front/left/top views with a mm grid (run inside Blender, arguments after --).")
ap.add_argument("sculpt"); ap.add_argument("out")
ap.add_argument("--fit", default=None, help="overlay this fit.json's joints and prop boxes")
ap.add_argument("--px", type=int, default=1400, help="picture size in pixels (square)")
ap.add_argument("--grid", type=float, default=1.0, help="grid spacing in mm (strong lines every 10)")
a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])

import bpy
import numpy as np
from mathutils import Vector

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=a.sculpt)
obs = [o for o in bpy.data.objects if o.type == "MESH"]
pts = np.array([list(o.matrix_world @ v.co) for o in obs for v in o.data.vertices]) * 1000.0
lo, hi = pts.min(0), pts.max(0); cen = (lo + hi) / 2; span = float((hi - lo).max()) * 1.08
print(f"[views] bounds mm: x {lo[0]:.1f}..{hi[0]:.1f}  y {lo[1]:.1f}..{hi[1]:.1f}  z {lo[2]:.1f}..{hi[2]:.1f}")

sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"; sc.display.shading.light = "STUDIO"; sc.display.shading.color_type = "TEXTURE"
sc.render.resolution_x = sc.render.resolution_y = a.px; sc.render.film_transparent = False
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w"); sc.world = w; w.color = (0.92, 0.92, 0.92)
cam = bpy.data.cameras.new("c"); cam.type = "ORTHO"; cam.ortho_scale = span / 1000.0; cam.clip_end = 1000
co = bpy.data.objects.new("c", cam); sc.collection.objects.link(co); sc.camera = co
far = span / 1000.0 * 3

# view -> (camera offset, euler degrees, which mm axes run right and up in the picture, sign of each)
VIEWS = {
    "front": ((0, -1, 0), (90, 0, 0), (0, 1), (2, 1)),     # right = +X, up = +Z
    "left":  ((1, 0, 0), (90, 0, 90), (1, -1), (2, 1)),    # right = -Y (the figure's front), up = +Z
    "top":   ((0, 0, 1), (0, 0, 0), (0, 1), (1, 1)),       # right = +X, up = +Y (the figure's back)
}
fit = json.load(open(a.fit)) if a.fit else None
meta = {}
for nm, (off, rot, (ax_r, sg_r), (ax_u, sg_u)) in VIEWS.items():
    co.location = Vector(cen / 1000.0) + Vector(off) * far
    co.rotation_euler = tuple(math.radians(r) for r in rot)
    path = f"{a.out}-{nm}.png"; sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    # millimetre range of the picture
    c_r, c_u = cen[ax_r] * sg_r, cen[ax_u] * sg_u
    r0, r1, u0, u1 = c_r - span / 2, c_r + span / 2, c_u - span / 2, c_u + span / 2
    meta[nm] = {"right": ("+" if sg_r > 0 else "-") + "XYZ"[ax_r], "up": ("+" if sg_u > 0 else "-") + "XYZ"[ax_u],
                "right_mm": [r0 * sg_r, r1 * sg_r], "up_mm": [u0 * sg_u, u1 * sg_u], "px": a.px}
    im = bpy.data.images.load(path); W_ = H_ = a.px
    px = np.empty(W_ * H_ * 4, np.float32); im.pixels.foreach_get(px); px = px.reshape(H_, W_, 4)   # row 0 is the bottom
    def col(mm_r): return (mm_r - r0) / span * W_
    def row(mm_u): return (mm_u - u0) / span * H_
    g = a.grid
    for k in range(math.floor(r0 / g), math.ceil(r1 / g) + 1):
        x = int(round(col(k * g)))
        if 0 <= x < W_: px[:, x, :3] = px[:, x, :3] * (0.55 if k % 10 == 0 else 0.85)
    for k in range(math.floor(u0 / g), math.ceil(u1 / g) + 1):
        y = int(round(row(k * g)))
        if 0 <= y < H_: px[y, :, :3] = px[y, :, :3] * (0.55 if k % 10 == 0 else 0.85)
    x0 = int(round(col(0))); y0 = int(round(row(0)))                      # the axes through zero, in blue
    if 0 <= x0 < W_: px[:, max(x0 - 1, 0):x0 + 2, :3] = (0.1, 0.3, 1.0)
    if 0 <= y0 < H_: px[max(y0 - 1, 0):y0 + 2, :, :3] = (0.1, 0.3, 1.0)
    if fit:
        def pp(p):
            p = np.asarray(p, float); return col(p[ax_r] * sg_r), row(p[ax_u] * sg_u)
        rad = max(3, a.px // 250)
        for jn, p in fit["joints"].items():
            x, y = pp(p); c = (0.1, 0.8, 0.1) if jn.startswith("Left") else (0.9, 0.1, 0.1) if jn.startswith("Right") else (1.0, 0.85, 0.0)
            xi, yi = int(x), int(y)
            px[max(yi - rad, 0):yi + rad, max(xi - rad, 0):xi + rad, :3] = c
        for pr in fit.get("props", []):
            for bx in pr.get("boxes", []):
                (xa, ya), (xb, yb) = pp(bx[0]), pp(bx[1])
                xa, xb = sorted((int(xa), int(xb))); ya, yb = sorted((int(ya), int(yb)))
                xa, xb, ya, yb = max(xa, 0), min(xb, W_ - 1), max(ya, 0), min(yb, H_ - 1)
                px[ya:yb, [xa, xb], :3] = (0, 0.9, 0.9); px[[ya, yb], xa:xb, :3] = (0, 0.9, 0.9)
    im.pixels.foreach_set(px.reshape(-1)); im.filepath_raw = path; im.file_format = "PNG"; im.save()
    print(f"[views] {path}: right {meta[nm]['right']} {meta[nm]['right_mm'][0]:.1f}..{meta[nm]['right_mm'][1]:.1f} mm, up {meta[nm]['up']}")
json.dump(meta, open(f"{a.out}-views.json", "w"), indent=1)
print(f"[views] wrote {a.out}-views.json. Pixel (col, row from the top) -> mm: right_mm[0] + col / px * (right_mm[1] - right_mm[0]) along 'right', up_mm[1] - row / px * (up_mm[1] - up_mm[0]) along 'up'")
