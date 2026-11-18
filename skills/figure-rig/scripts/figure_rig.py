# figure_rig.py: a static sculpt (one fused mesh, no skeleton, standing in its own pose, often on a display base) ->
# a skinned GLB on a donor's Mixamo-named skeleton, so it plays the donor's animation clips by bone name.
#
#   blender -b --factory-startup --python figure_rig.py -- <sculpt.glb> <donor-rigged.glb> <fit.json> <out.glb> [--debug <dir/name>]
#
# How: the sculpt stands in its own pose, not a T-pose. The donor's skeleton is put into that pose (each bone turned
# the least it can to reach the joint marked in fit.json, its length set to the statue's), and that pose is written as
# the skin's bind pose. The file's skeleton itself rests as the donor's does, with the statue's bone lengths, so a
# clip's rotations mean the same thing on both. Weights: each vertex goes to the bone whose capsule it is nearest,
# measured in capsule radii, then smoothed over the mesh; props listed in fit.json are pinned whole to one bone.
# fit.json is in millimetres in the sculpt's own space as Blender imports it (Z up, the figure facing -Y, its left +X).
# See references/fit-format.md for every key.
import sys, os, json, struct, argparse

ap = argparse.ArgumentParser(prog="figure_rig.py", description="Rig a static sculpt onto a donor's Mixamo skeleton (run inside Blender, arguments after --).")
ap.add_argument("sculpt", help="the static figure, a GLB with one textured mesh (e.g. a Meshy export)")
ap.add_argument("donor", help="a rigged GLB with Mixamo bone names whose clips the figure should play")
ap.add_argument("fit", help="fit.json: joints, capsule radii, props (millimetres, sculpt space)")
ap.add_argument("out", help="the GLB to write")
ap.add_argument("--debug", default=os.environ.get("RIG_DEBUG"), help="path prefix for close renders of each 'debug' region and a .joints.json (also RIG_DEBUG)")
ap.add_argument("--hips-height", type=float, default=None, help="the donor's hips above the ground in its own units (default: read from its rest pose)")
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
if args.debug: os.environ["RIG_DEBUG"] = args.debug

import bpy, bmesh, re
import numpy as np

SRC, DONOR, FIT, OUT = args.sculpt, args.donor, args.fit, args.out
for _src in (SRC, DONOR, FIT):
    if os.path.exists(OUT) and os.path.samefile(OUT, _src): sys.exit(f"[rig] the output would overwrite an input ({_src}): give another path")
fit = json.load(open(FIT))
MM = 0.001

# ---------- the donor's skeleton, read straight from its file ----------
def read_glb(path):
    with open(path, "rb") as fh:
        fh.read(12); n, = struct.unpack("<I", fh.read(4)); fh.read(4); j = json.loads(fh.read(n))
        m, = struct.unpack("<I", fh.read(4)); fh.read(4); binary = fh.read(m)
    return j, binary
sj, _ = read_glb(DONOR)
nodes = sj["nodes"]; NN = len(nodes)
parent = [-1] * NN
for i, nd in enumerate(nodes):
    for c in nd.get("children", []): parent[c] = i
name = [nd.get("name", "") for nd in nodes]
short = [re.sub(r"^mixamorig:?", "", n) for n in name]       # "mixamorig:Hips" (FBX/Blender) or "mixamorigHips" (three.js)
idx = {s: i for i, s in enumerate(short)}
def qmat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
def mquat(m):
    """rotation matrix -> quaternion (x, y, z, w)"""
    t = np.trace(m)
    if t > 0:
        r = np.sqrt(1 + t) * 2; return [(m[2, 1] - m[1, 2]) / r, (m[0, 2] - m[2, 0]) / r, (m[1, 0] - m[0, 1]) / r, r / 4]
    i = int(np.argmax(np.diag(m))); j, k = (i + 1) % 3, (i + 2) % 3
    r = np.sqrt(1 + m[i, i] - m[j, j] - m[k, k]) * 2; q = [0.0] * 4
    q[i] = r / 4; q[j] = (m[j, i] + m[i, j]) / r; q[k] = (m[k, i] + m[i, k]) / r; q[3] = (m[k, j] - m[j, k]) / r
    return q
for nd in nodes:                                       # a node written as a matrix: the same thing as translation, rotation, scale
    if "matrix" in nd:
        M_ = np.array(nd.pop("matrix"), float).reshape(4, 4).T
        S_ = np.linalg.norm(M_[:3, :3], axis=0)
        nd["translation"] = M_[:3, 3].tolist(); nd["rotation"] = mquat(M_[:3, :3] / S_); nd["scale"] = S_.tolist()
T = [np.array(nd.get("translation", [0, 0, 0]), float) for nd in nodes]
R = [qmat(nd.get("rotation", [0, 0, 0, 1])) for nd in nodes]
_joints = set(sj["skins"][0]["joints"])
_scaled = [nd.get("name", i) for i, nd in enumerate(nodes) if i in _joints and not np.allclose(nd.get("scale", [1, 1, 1]), 1, atol=1e-4)]
if _scaled: print(f"[rig] warning: these donor bones carry a scale, which the fit ignores: {_scaled}")
# Nodes above the skeleton (an Armature at 0.01 from Blender's FBX import) keep their transform in the output, so the
# figure comes out at the donor's size. Everything below is fitted in the skeleton's own units.
order = []
def walk(i):
    order.append(i)
    for c in nodes[i].get("children", []): walk(c)
for r in sj["scenes"][0]["nodes"]: walk(r)

def minrot(a, b):
    """the least rotation taking direction a to direction b"""
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    v = np.cross(a, b); c = float(a @ b); s = np.linalg.norm(v)
    if s < 1e-9: return np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * ((1 - c) / (s * s))

# ---------- the statue's joints, into the donor's space (its units, Y up, facing +Z, feet on y = 0) ----------
NEED = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "HeadTop_End"] + [s_ + b for s_ in ("Left", "Right") for b in (
    "Shoulder", "Arm", "ForeArm", "Hand", "HandMiddle4", "UpLeg", "Leg", "Foot", "ToeBase", "Toe_End")]
lack = [b for b in NEED if b not in idx]
if lack: sys.exit(f"[rig] the donor lacks bones: {lack} (needs Mixamo names; see references/fit-format.md)")
lack = [b for b in NEED if b not in fit["joints"]]
if lack: sys.exit(f"[rig] fit.json lacks joints: {lack}")
unknown = [b for b in fit["joints"] if b not in idx]
if unknown: sys.exit(f"[rig] fit.json names joints the donor does not have: {unknown}")
for _pr in fit.get("props", []):
    _bad = [b for b in [_pr.get("bone")] + _pr.get("bones", []) + _pr.get("cut_from", []) if b is not None and b not in idx]
    if _bad or "bone" not in _pr: sys.exit(f"[rig] prop {_pr.get('name', '?')}: 'bone' is required and these bones are not in the donor: {_bad}")
J = fit["joints"]; hips_mm = np.array(J["Hips"], float); sole = fit["sole"]
HIPS_H = args.hips_height or fit.get("hips_height") or float(T[idx["Hips"]][1])
K = HIPS_H / (hips_mm[2] - sole)                       # the statue's hips go where the donor's rest
print(f"[rig] donor hips {HIPS_H:.3f} above the ground")
def to_s(p):                                           # millimetres, Blender axes -> donor space
    p = np.asarray(p, float)
    return np.stack([(p[..., 0] - hips_mm[0]) * K, (p[..., 2] - sole) * K, -(p[..., 1] - hips_mm[1]) * K], -1)
target = {idx[k]: to_s(v) for k, v in J.items()}
PRIMARY = {"Hips": "Spine", "Spine": "Spine1", "Spine1": "Spine2", "Spine2": "Neck", "Neck": "Head", "Head": "HeadTop_End"}
for s_ in ("Left", "Right"):
    PRIMARY.update({s_ + "Shoulder": s_ + "Arm", s_ + "Arm": s_ + "ForeArm", s_ + "ForeArm": s_ + "Hand", s_ + "Hand": s_ + "HandMiddle4",
                    s_ + "UpLeg": s_ + "Leg", s_ + "Leg": s_ + "Foot", s_ + "Foot": s_ + "ToeBase", s_ + "ToeBase": s_ + "Toe_End"})
primary = {idx[a]: idx[b] for a, b in PRIMARY.items()}

Rw = [np.eye(3)] * NN; P = [np.zeros(3)] * NN; scale = [1.0] * NN
for i in order:
    p = parent[i]
    Rp = Rw[p] if p >= 0 else np.eye(3); Pp = P[p] if p >= 0 else np.zeros(3)
    if short[i] == "Hips": P[i] = target[i]
    else: P[i] = Pp + Rp @ (T[i] * scale[i])
    carry = Rp @ R[i]
    c = primary.get(i)
    if c is not None and c in target:
        want = target[c] - P[i]
        Rw[i] = minrot(carry @ T[c], want) @ carry
        scale[c] = np.linalg.norm(want) / np.linalg.norm(T[c])
    else: Rw[i] = carry
    for k in nodes[i].get("children", []):             # the other children keep their direction and take the statue's length
        if k != c and k in target: scale[k] = np.linalg.norm(target[k] - P[i]) / np.linalg.norm(T[k])
miss = {short[i]: round(float(np.linalg.norm(P[i] - target[i]) / K), 2) for i in target}
print("[rig] joint misses, mm:", {k: v for k, v in miss.items() if v > 0.3})
def leg(side, tr, sc): return sum(np.linalg.norm(tr[idx[side + b]]) * sc[idx[side + b]] for b in ("Leg", "Foot"))
LEGK = (leg("Left", T, scale) + leg("Right", T, scale)) / (leg("Left", T, [1.0] * NN) + leg("Right", T, [1.0] * NN))
print(f"[rig] scale {K * 1000:.2f} per file unit, legs {LEGK:.3f} of the donor's")

# ---------- the mesh ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
ob = next(o for o in bpy.data.objects if o.type == "MESH")
bm = bmesh.new(); bm.from_mesh(ob.data)
bmesh.ops.transform(bm, matrix=ob.matrix_world, verts=bm.verts)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
# the display base goes: cut at the soles, cap the cut, drop the crumbs of ground left above it
cut = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-7, plane_co=(0, 0, fit["cut"] * MM), plane_no=(0, 0, 1), clear_inner=True)
bmesh.ops.holes_fill(bm, edges=[e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge)], sides=0)
bm.verts.ensure_lookup_table()
seen = set(); comps = []
for v in bm.verts:
    if v.index in seen: continue
    stack = [v]; seen.add(v.index); comp = []
    while stack:
        u = stack.pop(); comp.append(u)
        for e in u.link_edges:
            w = e.other_vert(u)
            if w.index not in seen: seen.add(w.index); stack.append(w)
    comps.append(comp)
comps.sort(key=len, reverse=True)
keep_above = fit.get("crumb", fit["cut"] + 4) * MM
drop = [v for c in comps[1:] if max(v.co.z for v in c) < keep_above for v in c]
print(f"[rig] {len(comps)} pieces, sizes {[len(c) for c in comps[:8]]}; dropping {len(drop)} vertices of ground")
bmesh.ops.delete(bm, geom=drop, context="VERTS")
bmesh.ops.triangulate(bm, faces=bm.faces)
me = bpy.data.meshes.new("fig"); bm.to_mesh(me); bm.free()
want = fit.get("triangles")                            # a light cut: a figure in the background needs few triangles
if want and len(me.polygons) > want:
    ob2 = bpy.data.objects.new("fig", me); bpy.context.scene.collection.objects.link(ob2)
    mod = ob2.modifiers.new("d", "DECIMATE"); mod.ratio = want / len(me.polygons); mod.use_collapse_triangulate = True
    me = bpy.data.meshes.new_from_object(ob2.evaluated_get(bpy.context.evaluated_depsgraph_get()))
for p in me.polygons: p.use_smooth = True
me.update()
nv, nl, nt = len(me.vertices), len(me.loops), len(me.polygons)
co = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3).astype(float)
vn = np.empty(nv * 3, np.float32); me.vertices.foreach_get("normal", vn); vn = vn.reshape(-1, 3).astype(float)
lv = np.empty(nl, np.int32); me.loops.foreach_get("vertex_index", lv)
uv = np.empty(nl * 2, np.float32); me.uv_layers[0].data.foreach_get("uv", uv); uv = uv.reshape(-1, 2)
mm = co / MM                                           # millimetres, Blender axes: what fit.json speaks
V = to_s(mm)                                           # donor space
Nn = np.stack([vn[:, 0], vn[:, 2], -vn[:, 1]], -1)
tri = lv.reshape(-1, 3)
print(f"[rig] mesh: {nv} vertices, {nt} triangles")

# ---------- weights ----------
RAD = fit["radius"]; caps = []                         # (joint, a, b, radius)
def J_(n): return P[idx[n]]
def cap(bone, a, b, r): caps.append((idx[bone], np.asarray(a, float), np.asarray(b, float), r * K))
up = np.array([0, 1.0, 0])
cap("Hips", J_("Hips") - up * RAD["pelvis_drop"] * K, J_("Spine"), RAD["Hips"])
for a, b in (("Spine", "Spine1"), ("Spine1", "Spine2"), ("Spine2", "Neck"), ("Neck", "Head")): cap(a, J_(a), J_(b), RAD[a])
cap("Head", J_("Head"), J_("HeadTop_End") + (J_("HeadTop_End") - J_("Head")) * 0.35, RAD["Head"])
for s_ in ("Left", "Right"):
    for a, b in (("Shoulder", "Arm"), ("Arm", "ForeArm"), ("ForeArm", "Hand"), ("UpLeg", "Leg"), ("Leg", "Foot"), ("Foot", "ToeBase"), ("ToeBase", "Toe_End")):
        cap(s_ + a, J_(s_ + a), J_(s_ + b), RAD[a])
    h, e = J_(s_ + "Hand"), J_(s_ + "HandMiddle4"); cap(s_ + "Hand", h, e + (e - h) * 0.3, RAD["Hand"])
def segdist(p, a, b):
    ab = b - a; t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)
score = np.stack([segdist(V, a, b) / r for _, a, b, r in caps], 1)
capj = np.array([c[0] for c in caps])
W = np.zeros((nv, NN))
soft = fit.get("soft", 0.22)
w0 = np.clip(1 - (score - score.min(1, keepdims=True)) / soft, 0, None) ** 2
np.add.at(W.T, capj, w0.T)
# each vertex's colour in the map, for telling a prop from the hand that holds it
fj, fbin = read_glb(SRC)
t = fj["textures"][fj["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]["index"]]
im = fj["images"][t.get("extensions", {}).get("EXT_texture_webp", {}).get("source", t.get("source"))]
bv = fj["bufferViews"][im["bufferView"]]; img = fbin[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
tmp = os.path.join(bpy.app.tempdir, "map.webp"); open(tmp, "wb").write(img)
bi = bpy.data.images.load(tmp); iw, ih = bi.size
px = np.empty(iw * ih * 4, np.float32); bi.pixels.foreach_get(px); px = px.reshape(ih, iw, 4)
vuv = np.zeros((nv, 2)); vuv[lv] = uv
rgb = px[np.clip((vuv[:, 1] * ih).astype(int), 0, ih - 1), np.clip((vuv[:, 0] * iw).astype(int), 0, iw - 1), :3]
luma = rgb @ np.array([0.299, 0.587, 0.114]); sat = (rgb.max(1) - rgb.min(1)) / np.maximum(rgb.max(1), 1e-6)
if os.environ.get("RIG_DEBUG"):
    for nm in ("LeftForeArm", "RightForeArm", "LeftHand"):
        ci = next((k for k, c_ in enumerate(caps) if short[c_[0]] == nm), None)
        if ci is None: continue
        m = score[:, ci] < 0.9
        if not m.any(): print(f"[rig] colour near {nm}: no vertices within its capsule"); continue
        print(f"[rig] colour near {nm}: n {int(m.sum())} luma {np.percentile(luma[m], [10, 50, 90]).round(2)} sat {np.percentile(sat[m], [10, 50, 90]).round(2)}")
# props: whole to one bone, and kept out of the smoothing
pinned = np.zeros(nv, bool); group = np.full(nv, -1)
ed0 = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]); ed0 = np.concatenate([ed0, ed0[:, ::-1]])
deg0 = np.bincount(ed0[:, 0], minlength=nv).astype(float)
for gi, pr in enumerate(fit.get("props", [])):
    sel = np.zeros(nv, bool)
    for bx in pr.get("boxes", []):
        lo, hi = np.array(bx[0], float), np.array(bx[1], float); sel |= ((mm >= lo) & (mm <= hi)).all(1)
    for bn in pr.get("bones", []): sel |= W.argmax(1) == idx[bn]     # everything a bone would have had: a hand locked to its forearm
    inbox = sel.copy()
    for sg in pr.get("rods", []):
        sel |= segdist(mm, np.array(sg[0], float), np.array(sg[1], float)) < sg[2]
    for bx in pr.get("not", []):
        lo, hi = np.array(bx[0], float), np.array(bx[1], float); sel &= ~((mm >= lo) & (mm <= hi)).all(1)
    sp = pr.get("spare")                                # what is inside the prop's space but is not the prop: a hand by its colour and its bone, a white ribbon by its colour
    if sp:
        out_ = np.ones(nv, bool)
        if "luma" in sp: out_ &= (luma >= sp["luma"][0]) & (luma <= sp["luma"][1])
        if "sat" in sp: out_ &= (sat >= sp["sat"][0]) & (sat <= sp["sat"][1])
        if "caps" in sp:
            near = np.zeros(nv, bool)
            for ci, c_ in enumerate(caps):
                if short[c_[0]] in sp["caps"]: near |= score[:, ci] < sp.get("within", 1.0)
            out_ &= near
        sel &= ~out_
    asis = np.zeros(nv, bool)
    for bn in pr.get("bones", []): asis |= W.argmax(1) == idx[bn]
    if "luma" in pr: sel &= ((luma >= pr["luma"][0]) & (luma <= pr["luma"][1])) | asis
    if "sat" in pr: sel &= ((sat >= pr["sat"][0]) & (sat <= pr["sat"][1])) | asis
    for _ in range(pr.get("grow", 0)):                 # take in the few vertices the colour test missed inside the prop
        n_in = np.zeros(nv); np.add.at(n_in, ed0[:, 0], sel[ed0[:, 1]].astype(float)); sel |= (n_in / np.maximum(deg0, 1) >= pr.get("grow_at", 0.5)) & inbox
    W[sel] = 0; W[sel, idx[pr["bone"]]] = 1; pinned |= sel; group[sel] = gi
    print(f"[rig] prop {pr['name']}: {int(sel.sum())} vertices -> {pr['bone']}")
W /= W.sum(1, keepdims=True)
# a prop torn from what it was sculpted against: the triangles that bridge it to a part that moves otherwise are left
# out, and before the smoothing, so that no weight seeps across the cut
dom = W.argmax(1); keep = np.ones(len(tri), bool)
for gi, pr in enumerate(fit.get("props", [])):
    free = {idx[b] for b in pr.get("cut_from", [])}
    if not free: continue
    g = group[tri] == gi; other = np.isin(dom[tri], list(free)) & ~g
    keep &= ~(g.any(1) & other.any(1))
for gi, pr in enumerate(fit.get("props", [])):
    if pr.get("delete"): keep &= ~(group[tri] == gi).any(1)
print(f"[rig] {int((~keep).sum())} bridging or deleted triangles left out")
if os.environ.get("RIG_DEBUG"):
    # pictures of who owns what round a prop: true colour beside the classes (props tinted blue, each bone its own colour)
    import math
    from mathutils import Vector
    dbg = os.path.splitext(os.environ["RIG_DEBUG"])[0]
    PAL = {"Hips": (1, 0, 0), "LeftUpLeg": (1, .55, 0), "LeftForeArm": (0, .85, 0), "LeftHand": (0, 1, 1), "LeftArm": (0, .35, 1), "Spine": (1, 0, 1), "Spine1": (.6, 0, .6), "Spine2": (.4, 0, .8), "RightHand": (1, 1, 0), "RightForeArm": (.6, .8, 0), "Head": (.3, .3, 1), "Neck": (0, .6, .6)}
    cls = np.full((nv, 3), 0.35)
    for k_, c_ in PAL.items(): cls[dom == idx[k_]] = c_
    cls = 0.65 * cls + 0.35 * rgb; cls[group >= 0] = 0.25 + 0.75 * rgb[group >= 0]; cls[group >= 0, 2] = 1.0
    for o_ in bpy.data.objects: o_.hide_render = True
    obd = bpy.data.objects.new("dbg", me); bpy.context.scene.collection.objects.link(obd)
    for nm, colr in (("true", rgb), ("cls", cls)):
        ca = me.color_attributes.new(nm, "FLOAT_COLOR", "POINT"); ca.data.foreach_set("color", np.concatenate([colr, np.ones((nv, 1))], 1).astype(np.float32).reshape(-1))
    sc = bpy.context.scene; sc.render.engine = "BLENDER_WORKBENCH"; sc.display.shading.light = "FLAT"; sc.display.shading.color_type = "VERTEX"
    sc.render.resolution_x = sc.render.resolution_y = 700; sc.view_settings.view_transform = "Standard"
    wd = bpy.data.worlds.new("w"); sc.world = wd; wd.color = (0.1, 0.1, 0.1)
    cam = bpy.data.cameras.new("c"); cam.type = "ORTHO"; co_ = bpy.data.objects.new("c", cam); sc.collection.objects.link(co_); sc.camera = co_
    for rg in fit.get("debug", []):
        cen = Vector(rg["at"]) * MM; cam.ortho_scale = rg["size"] * MM
        for vn_, (off, rot) in {"front": ((0, -1, 0), (90, 0, 0)), "left": ((1, 0, 0), (90, 0, 90)), "back": ((0, 1, 0), (90, 0, 180)), "top": ((0, 0, 1), (0, 0, 0)), "under": ((0, 0, -1), (180, 0, 0)), "fl": ((.7, -.7, .3), (72, 0, 45))}.items():
            co_.location = cen + Vector(off) * max(0.2, rg["size"] * MM * 2); co_.rotation_euler = tuple(math.radians(r_) for r_ in rot)
            for nm in ("true", "cls"):
                me.color_attributes.active_color = me.color_attributes[nm]; me.color_attributes.render_color_index = me.color_attributes.find(nm)
                sc.render.filepath = f"{dbg}-{re.sub(r'[^A-Za-z0-9._-]', '_', str(rg['name']))}-{vn_}-{nm}.png"; bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(obd)
gone = tri[~keep]
luv = uv.reshape(-1, 3, 2)[keep].reshape(-1, 2); tri = tri[keep]
ed = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]); ed = np.concatenate([ed, ed[:, ::-1]])
deg = np.bincount(ed[:, 0], minlength=nv).astype(float)[:, None]
for _ in range(fit.get("smooth", 8)):
    acc = np.zeros_like(W); np.add.at(acc, ed[:, 0], W[ed[:, 1]])
    Wn = np.where(deg > 0, 0.5 * W + 0.5 * acc / np.maximum(deg, 1), W); Wn[pinned] = W[pinned]; W = Wn
# the cuts leave holes: an arm sculpted against a prop has no inner side there. Each hole's rim is closed with a fan of
# one flat colour taken from the rim.
torn = {frozenset(e) for t_ in gone for e in ((t_[0], t_[1]), (t_[1], t_[2]), (t_[2], t_[0]))}
have = {(int(a_), int(b_)) for t_ in tri for a_, b_ in ((t_[0], t_[1]), (t_[1], t_[2]), (t_[2], t_[0]))}
nxt = {}
for a_, b_ in have:
    if (b_, a_) not in have and frozenset((a_, b_)) in torn: nxt.setdefault(a_, b_)
caps_t, caps_uv, add_v, add_n, add_w = [], [], [], [], []
used = set(); nloops = 0
for start in list(nxt):
    if start in used: continue
    loop = [start]; used.add(start); cur = nxt[start]
    while cur != start and cur in nxt and cur not in used and len(loop) < 600:
        loop.append(cur); used.add(cur); cur = nxt[cur]
    if cur != start or len(loop) < 3: continue
    L = np.array(loop); c = len(V) + len(add_v)
    add_v.append(V[L].mean(0)); n_ = Nn[L].mean(0); add_n.append(n_ / max(np.linalg.norm(n_), 1e-9)); add_w.append(W[L].mean(0))
    u0 = vuv[L[np.argsort(luma[L])[len(L) // 2]]]
    for k in range(len(L)):
        caps_t.append((L[(k + 1) % len(L)], L[k], c)); caps_uv += [u0, u0, u0]
    nloops += 1
if add_v:
    V = np.vstack([V, add_v]); Nn = np.vstack([Nn, add_n]); W = np.vstack([W, add_w])
    tri = np.vstack([tri, np.array(caps_t)]); luv = np.vstack([luv, np.array(caps_uv, np.float32)])
print(f"[rig] {nloops} holes capped with {len(caps_t)} triangles")
lvk = tri.reshape(-1)
_skin = sj["skins"][0]["joints"]; _off = np.setdiff1d(np.arange(NN), _skin)
W[:, _off] = 0; W /= np.maximum(W.sum(1, keepdims=True), 1e-12)   # only the skin's joints may carry weight
top = np.argsort(-W, 1)[:, :4]; tw = np.take_along_axis(W, top, 1); tw /= tw.sum(1, keepdims=True)

# ---------- the file ----------
skin_joints = sj["skins"][0]["joints"]; slot = {n: k for k, n in enumerate(skin_joints)}
key = np.concatenate([lvk[:, None].astype(np.float64), np.round(luv, 5)], 1)
uniq, inv = np.unique(key, axis=0, return_inverse=True)
vi = uniq[:, 0].astype(int); inv = inv.reshape(-1)
pos = V[vi].astype(np.float32); nor = Nn[vi].astype(np.float32); tex = np.stack([uniq[:, 1], 1 - uniq[:, 2]], 1).astype(np.float32)
jn = np.vectorize(lambda n: slot.get(n, 0))(top[vi]).astype(np.uint8); wt = tw[vi].astype(np.float32)
jn[wt == 0] = 0
ind = inv.astype(np.uint32)
ibm = np.zeros((len(skin_joints), 16), np.float32)
for k, n in enumerate(skin_joints):
    M = np.eye(4); M[:3, :3] = Rw[n]; M[:3, 3] = P[n]
    ibm[k] = np.linalg.inv(M).T.reshape(-1)             # column-major
MIME = im.get("mimeType") or ("image/webp" if img[8:12] == b"WEBP" else "image/png")
side = fit.get("map")                                  # resize the colour map (cwebp): 1024 is plenty for a figure seen at a distance
if side:
    import subprocess
    small = os.path.join(bpy.app.tempdir, "small.webp")
    subprocess.run(["cwebp", "-quiet", "-q", str(fit.get("map_q", 78)), "-resize", str(side), str(side), tmp, "-o", small], check=True)
    img = open(small, "rb").read(); MIME = "image/webp"
chunks = []; views = []; accs = []
def view(data, target=None, stride=None):
    off = sum(len(c) for c in chunks); pad = (-len(data)) % 4; chunks.append(data + b"\0" * pad)
    v = {"buffer": 0, "byteOffset": off, "byteLength": len(data)}
    if target: v["target"] = target
    if stride: v["byteStride"] = stride
    views.append(v); return len(views) - 1
def acc(arr, typ, comp, target=None, mm_=False, norm=False, stride=None):
    a = {"bufferView": view(arr.tobytes(), target, stride), "componentType": comp, "count": len(arr), "type": typ}
    if mm_: a["min"] = arr.min(0).tolist(); a["max"] = arr.max(0).tolist()
    if norm: a["normalized"] = True
    accs.append(a); return len(accs) - 1
# packed: normals as bytes (padded to four), texture coordinates as 16-bit, weights as bytes that sum to 255
nor /= np.maximum(np.linalg.norm(nor, axis=1, keepdims=True), 1e-9)
nor8 = np.zeros((len(nor), 4), np.int8); nor8[:, :3] = np.round(nor * 127)
tex16 = np.round(np.clip(tex, 0, 1) * 65535).astype(np.uint16)
w8 = np.floor(wt * 255).astype(np.int32); w8[np.arange(len(w8)), wt.argmax(1)] += 255 - w8.sum(1); w8 = w8.astype(np.uint8)
jn[w8 == 0] = 0
small_ix = len(pos) < 65536
a_ind = acc(ind.astype(np.uint16) if small_ix else ind, "SCALAR", 5123 if small_ix else 5125, 34963); a_pos = acc(pos, "VEC3", 5126, 34962, True)
a_nor = acc(nor8, "VEC3", 5120, 34962, norm=True, stride=4)
a_tex = acc(tex16, "VEC2", 5123, 34962, norm=True); a_j = acc(jn, "VEC4", 5121, 34962); a_w = acc(w8, "VEC4", 5121, 34962, norm=True); a_ibm = acc(ibm, "MAT4", 5126)
v_img = view(img)
EXT = (["EXT_texture_webp"] if MIME == "image/webp" else []) + ["KHR_mesh_quantization"]
out_nodes = []; placed = False
for i, nd in enumerate(nodes):
    o = {"name": nd.get("name", "")}
    if "children" in nd: o["children"] = nd["children"]
    if "rotation" in nd: o["rotation"] = nd["rotation"]
    if "translation" in nd: o["translation"] = (T[i] * scale[i]).tolist()
    if "scale" in nd and i not in _joints: o["scale"] = nd["scale"]
    if "mesh" in nd and not placed: o["mesh"] = 0; o["skin"] = 0; placed = True   # the figure once, on the donor's first mesh node
    out_nodes.append(o)
if not placed: sys.exit("[rig] the donor has no mesh node to hang the figure on")
g = {
    "asset": {"version": "2.0", "generator": "figure-rig"},
    "extensionsUsed": EXT, "extensionsRequired": EXT,
    "scene": 0, "scenes": [{"nodes": sj["scenes"][0]["nodes"]}], "nodes": out_nodes,
    "meshes": [{"name": "figure", "primitives": [{"attributes": {"POSITION": a_pos, "NORMAL": a_nor, "TEXCOORD_0": a_tex, "JOINTS_0": a_j, "WEIGHTS_0": a_w}, "indices": a_ind, "material": 0}]}],
    "skins": [{"joints": skin_joints, "inverseBindMatrices": a_ibm}],
    "materials": [{"name": "figure", "doubleSided": True, "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0, "roughnessFactor": 1}}],
    "textures": [({"extensions": {"EXT_texture_webp": {"source": 0}}} if MIME == "image/webp" else {"source": 0}) | {"sampler": 0}], "samplers": [{"magFilter": 9729, "minFilter": 9987}],
    "images": [{"bufferView": v_img, "mimeType": MIME}],
    "accessors": accs, "bufferViews": views, "buffers": [{"byteLength": sum(len(c) for c in chunks)}],
    "extras": {"legs": round(float(LEGK), 4)},        # the figure's legs over the donor's: scale the hips' travel in a clip by it
}
js = json.dumps(g, separators=(",", ":")).encode(); js += b" " * ((-len(js)) % 4); body = b"".join(chunks)
with open(OUT, "wb") as fh:
    fh.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(body)))
    fh.write(struct.pack("<I4s", len(js), b"JSON")); fh.write(js); fh.write(struct.pack("<I4s", len(body), b"BIN\0")); fh.write(body)
print(f"[rig] wrote {OUT}: {len(pos)} vertices, {len(ind) // 3} triangles, {os.path.getsize(OUT) / 1e6:.2f} MB")
# the fitted joints back in millimetres, for laying over the views (written beside the debug dump only)
if not os.environ.get("RIG_DEBUG"): sys.exit(0)
back = {short[i]: [float(P[i][0] / K + hips_mm[0]), float(-P[i][2] / K + hips_mm[1]), float(P[i][1] / K + sole)] for i in range(NN) if short[i] in idx and parent[i] >= 0}
json.dump({"joints": back, "parent": {short[i]: short[parent[i]] for i in range(NN) if parent[i] >= 0}}, open(os.path.splitext(os.environ["RIG_DEBUG"])[0] + ".joints.json", "w"))
