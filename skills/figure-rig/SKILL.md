---
name: figure-rig
description: Rig a static, unrigged 3D sculpt (a Meshy or other image-to-3D figure standing on a display base, one fused mesh, no skeleton) onto an existing Mixamo-named skeleton so it plays that skeleton's animation clips in three.js or any glTF player. Use when the user wants a statue, figurine or Meshy model to dance, walk or move, mentions rigging a static GLB, borrowing another character's animations, or skinning a sculpt to a Mixamo skeleton without Mixamo's auto-rigger.
---

# Figure rig: a static sculpt that plays another character's dances

Image-to-3D tools give you a sculpt: one fused shell, posed however the picture was, often on a base, with props (a hammer, scrolls, a sword) sculpted against the body. Auto-riggers want a clean T-pose and separate props, so they fail on it. This skill rigs the sculpt **in its own pose** onto a **donor**: any rigged GLB with Mixamo bone names whose clips you want it to play. The output file shares the donor's bone names, so the donor's clips play on it unchanged; nothing is animated in the figure's own file.

```
1. views.py       straight-on front / left / top renders with a millimetre grid
2. fit.json       joints, capsule radii, props marked by hand from those renders (about an hour per figure)
3. figure_rig.py  cut the base, bind the donor's skeleton in the statue's pose, weight, pin props, write a light GLB
4. check          --debug renders of each prop region; held frames, one per clip; then a full watch in motion
5. web            borrow the donor's clips (rotations as they are, hips' travel scaled by leg length), match its stature
```

Show the user the views, the debug renders and the held frames as you go. Fix a miss in fit.json and run again; a run takes seconds.

`scripts/` below means the `scripts/` folder in **this skill's base directory**, not the user's project: `${CLAUDE_SKILL_DIR}/scripts` (Claude Code fills in the skill's directory for a plugin or a copied skill alike). The commands below use `S` for it:

```sh
S="${CLAUDE_SKILL_DIR}/scripts"
```

## 1. Views

```sh
blender -b --factory-startup --python "$S/views.py" -- <sculpt.glb> <build>/<name> [--fit <name>.fit.json] [--grid 1]
```

Writes `<name>-front.png`, `-left.png`, `-top.png` and `-views.json` (each picture's millimetre range, so a pixel reads back as a coordinate). Millimetres are the file's units x 1000, Z up, the figure facing -Y, its left at +X: the space `fit.json` uses. With `--fit` every marked joint is drawn as a dot (left green, right red, centre yellow) and each prop box as a cyan outline. Re-render with `--fit` after every marking pass and look before rigging.

## 2. Mark the fit file

Start from [references/example.fit.json](references/example.fit.json) (an example figure holding a hammer over one shoulder and a bundle of scrolls in the other hand). Read [references/fit-format.md](references/fit-format.md) for every key. In short:

- **Joints** for every bone in the list (Hips, the three spines, Neck, Head, HeadTop_End; per side Shoulder, Arm, ForeArm, Hand, HandMiddle4, UpLeg, Leg, Foot, ToeBase, Toe_End), each `[x, y, z]` in mm. Read x and z off the front view, y off the left view. Put joints **inside** the body at the pivot, not on its surface.
- **`sole`**: the height of the soles; **`cut`**: just above it, where the base is cut off (the cut is capped); **`crumb`**: loose bits of ground lower than this are dropped.
- **`radius`**: one capsule radius per bone kind, about the limb's half-thickness. Too small and the next bone steals the surface; too large and the torso drags the arms.
- **`props`**: each one goes whole to one bone. Mark it with boxes and rods; trim with `not`, a colour range, or `spare` (what is inside its space but is not the prop, such as the hand that holds it).
- **`cut_from`**: the bones a prop was sculpted against. The triangles that bridge them are cut before the weights are smoothed.
- **`triangles`**, **`map`**, **`map_q`**: the budget. A figure seen at a distance needs about 14K triangles and a 1K map.

## 3. Rig

```sh
blender -b --factory-startup --python "$S/figure_rig.py" -- <sculpt.glb> <donor.glb> <name>.fit.json <out.glb> [--debug <build>/<name>]
```

It prints the joint misses (should be under a millimetre), the figure's leg length against the donor's, the pieces it found and dropped, each prop's vertex count, the bridging triangles cut, the holes it capped and the file size. A typical result is 14K triangles at about 0.7 MB.

What it does, and the lessons it encodes:

- **Cut the base off at the soles** and cap the cut. Drop crumbs of ground left above it.
- **Bind in the statue's pose.** The donor's skeleton is turned bone by bone into the statue's pose (the least rotation reaching each marked joint, lengths set to the statue's) and that pose becomes the bind pose. The file's rest pose stays the donor's with the statue's lengths, so a clip's rotations mean the same thing on both.
- **Weights:** each vertex goes to the bone whose capsule it is nearest, measured in radii (soft falloff `soft`), then smoothed over the mesh `smooth` times.
- **Props go whole to one bone and are cut free before the smoothing.** After it, weight seeps across the join and drags skin and cloth into sheets.
- **A hand that holds a prop is locked to the forearm with it** (`"bones": ["LeftHand"]` in the prop), so a turning wrist cannot pull the hand off what it holds. Tying a prop to the hip instead usually fails: the arm behind it has no inner side and shows as a half shell.
- **Holes left by cutting a prop free are closed** with small flat patches coloured from the rim.
- **It stays light:** decimated to `triangles`, the map resized with `cwebp`, positions as floats, normals as bytes, UVs as 16-bit, weights as bytes (`KHR_mesh_quantization`). No Draco: few tools write Draco for a hand-built skin, and it would save perhaps a third more.
- `extras.legs` in the file is the figure's leg length over the donor's: the hips' travel in a clip is scaled by it on the web.

## 4. Check

- **Find misses with pictures, not guesses.** Add a `debug` region round each prop (`{"name", "at": [x,y,z], "size": mm}`) and run with `--debug <prefix>`: it renders close orthographic views from six sides, true colour beside who owns what (props tinted blue, each bone its own colour), and writes `<prefix>.joints.json` with the fitted joints.
- **Held frames, one per clip,** in the target app: hold every clip at a busy moment and look for tearing at the shoulders, hips and around each prop, from the front and from behind.
- **Then a full watch in motion.** Props passing through the body in some moves is likely and is a choice of clip, not a rig fault.

## 5. Web (three.js)

Read [references/web.md](references/web.md). The essentials: load the donor's clips once; for the figure, keep only quaternion tracks and the Hips position track, and scale the Hips position by `userData.legs`; size it to the donor's **stature** (the head joint above the foot joint, measured in a clip's first frame, not the bounding box, which a raised hammer or topknot distorts), so it keeps its own build.

## Files

- `scripts/figure_rig.py`: the rig (Blender 4.x/5.x, numpy as bundled). `-- --help` lists the arguments.
- `scripts/views.py`: the marking views and overlay.
- `references/fit-format.md`: every key of fit.json, how to read coordinates off the views, and what to change for each kind of miss.
- `references/example.fit.json`: a complete, working fit file for a figure with two props.
- `references/web.md`: playing the donor's clips on the figure in three.js.
