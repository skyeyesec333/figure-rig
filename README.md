# figure-rig

A Claude Code skill that makes a static 3D sculpt move.

Image-to-3D tools such as Meshy give you a statue: one fused mesh, standing in whatever pose the picture had, often on a display base, with props sculpted against the body. Auto-riggers want a clean T-pose and fail on it. This skill rigs the statue **in its own pose** onto a **donor**: any rigged GLB with Mixamo bone names. The result shares the donor's bone names, so the donor's dances, walks and idles play on it unchanged.

```
static sculpt + donor skeleton → marking views → fit.json → Blender → skinned GLB (~0.7 MB) → donor's clips in three.js
```

It was built to turn a Meshy figurine holding a hammer and a bundle of scrolls into a backup dancer playing a rigged character's seven dances: 14K triangles, a 1K map, 0.7 MB.

## What the skill does

1. **Renders marking views** (`scripts/views.py`): front, side and top, orthographic, with a millimetre grid; with a fit file, the marked joints and prop boxes are drawn over the figure.
2. **Helps you mark the fit file:** joint positions, limb thickness and the props, starting from a complete example.
3. **Rigs it in Blender** (`scripts/figure_rig.py`): cuts the base off at the soles, turns the donor's skeleton into the statue's pose and binds it there, weights each vertex to the nearest bone, pins each prop whole to one bone and cuts it free from the body before smoothing, caps the holes, and writes a quantised, skinned GLB.
4. **Checks it:** close-up renders of who owns what around each prop, then held frames of each clip in your app.
5. **Shows how to play it in three.js:** borrow the donor's clips (rotations as they are, the hips' travel scaled by leg length) and match the donor's height.

## Install

**As a Claude Code plugin** (from inside Claude Code):

```
/plugin marketplace add skyeyesec333/figure-rig
/plugin install figure-rig@figure-rig
```

**Or as a plain skill:** copy `skills/figure-rig` into `~/.claude/skills/` (all your projects) or into a project's `.claude/skills/`:

```sh
git clone https://github.com/skyeyesec333/figure-rig
cp -r figure-rig/skills/figure-rig ~/.claude/skills/
```

## Use

Ask in any project:

- "Make this Meshy statue dance with the soldier's animations"
- "Rig figure.glb onto dancer.glb"
- "The scrolls come off his hand when he spins; fix the rig"

or call it directly: `/figure-rig figure.glb donor.glb`.

The scripts also run without Claude:

```sh
blender -b --factory-startup --python skills/figure-rig/scripts/views.py -- figure.glb build/figure --fit figure.fit.json
blender -b --factory-startup --python skills/figure-rig/scripts/figure_rig.py -- figure.glb donor.glb figure.fit.json figure-rigged.glb
```

## Requirements

- [Claude Code](https://claude.com/claude-code)
- [Blender](https://www.blender.org) 4.x or 5.x (run headless; uses its bundled Python and numpy)
- A donor: a rigged GLB with Mixamo bone names (`mixamorig:Hips` or `mixamorigHips`), including the hand and toe end bones
- A sculpt as a GLB with one textured mesh
- `cwebp` (libwebp) to shrink the colour map
- About an hour per figure to mark the joints and props

## Licence

MIT. See [LICENSE](LICENSE).
