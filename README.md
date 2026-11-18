# figure-rig

Makes a static 3D statue move, by giving it the skeleton and animations of a character that already moves.

It was built to turn a figurine holding a hammer and scrolls into a backup dancer that plays another character's seven dances: 14K triangles, 0.7 MB.

## Good for

- Making a Meshy (or other image-to-3D) statue dance, walk or idle on a website
- Reusing animations you already have, with no new motion capture
- Figures that hold props, like a hammer or a staff, that must stay in the hand
- Keeping the result small enough for the web (under 1 MB)

## Install

In Claude Code, run:

```
/plugin marketplace add skyeyesec333/figure-rig
/plugin install figure-rig@figure-rig
```

Or copy the skill into your own skills folder:

```sh
git clone https://github.com/skyeyesec333/figure-rig
cp -r figure-rig/skills/figure-rig ~/.claude/skills/
```

You can also copy it into one project's `.claude/skills/` folder instead.

## Try asking Claude

- "Make this Meshy statue dance with the soldier's animations"
- "Rig figure.glb onto dancer.glb"
- "The scrolls come off his hand when he spins; fix the rig"

Or call it directly: `/figure-rig figure.glb donor.glb`. As a plugin, it is `/figure-rig:figure-rig figure.glb donor.glb`.

## You'll need

- [Claude Code](https://claude.com/claude-code)
- [Blender](https://www.blender.org) 4.x or 5.x. It runs in the background and uses its own Python and numpy.
- A **donor**: a rigged GLB with Mixamo bone names (`mixamorig:Hips` or `mixamorigHips`), including the hand and toe end bones
- The statue as a GLB with one textured mesh
- `cwebp` (libwebp) to shrink the colour map
- About an hour per figure to mark the joints and props

## How it works

```
static sculpt + donor skeleton → marking views → fit.json → Blender → skinned GLB (~0.7 MB) → donor's clips in three.js
```

Image-to-3D tools give you a statue. It is one fused mesh, in whatever pose the picture had, often on a display base. Props are sculpted against the body.

Auto-riggers (tools that add a skeleton for you) want a clean T-pose, and they fail on a statue like this. This skill rigs the statue **in its own pose** onto the donor. The result shares the donor's bone names, so the donor's dances, walks and idles play on it unchanged.

1. **Marking views** (`scripts/views.py`): front, side and top renders with a millimetre grid. With a fit file, the marked joints and prop boxes are drawn over the figure.
2. **The fit file**: Claude helps you mark joint positions, limb thickness and props, starting from a complete example.
3. **Rigging in Blender** (`scripts/figure_rig.py`):
   - cuts the base off at the soles;
   - poses the donor's skeleton to match the statue and binds it there;
   - weights each vertex to the nearest bone (decides which bone moves it);
   - pins each prop whole to one bone and cuts it free from the body;
   - caps the holes, and writes a compact, skinned GLB.
4. **Checks**: close-up renders of which bone owns which part around each prop, then held frames of each clip in your app.
5. **three.js**: borrow the donor's clips and match the donor's height. The hips' travel is scaled by leg length.

The scripts also run without Claude. The paths are relative to the cloned repo:

```sh
blender -b --factory-startup --python skills/figure-rig/scripts/views.py -- figure.glb build/figure --fit figure.fit.json
blender -b --factory-startup --python skills/figure-rig/scripts/figure_rig.py -- figure.glb donor.glb figure.fit.json figure-rigged.glb
```

## Licence

MIT. See [LICENSE](LICENSE).
