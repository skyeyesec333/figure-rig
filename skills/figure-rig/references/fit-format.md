# fit.json

All lengths are **millimetres in the sculpt's own space as Blender imports the GLB**: the file's units x 1000, Z up, the figure facing -Y, its left at +X. (A 7.5 cm Meshy figurine is about 75 mm tall; a life-size model is about 1800. Both work; only the numbers are larger.) `views.py` renders the space with a grid in exactly these units.

## Reading coordinates off the views

- **front** (looking at its face): right of the picture = +X (the figure's left), up = +Z. Gives x and z.
- **left** (from the figure's left side): right of the picture = -Y (its front), up = +Z. Gives y and z.
- **top**: right = +X, up = +Y (its back). A check for y.
- `<name>-views.json` holds each picture's millimetre range: for a pixel at column `c`, row `r` from the top, `mm_right = right_mm[0] + c / px * (right_mm[1] - right_mm[0])` and `mm_up = up_mm[1] - r / px * (up_mm[1] - up_mm[0])`.
- Mark joints **at the pivot inside the body**: a shoulder ball, not the top of the pauldron; a knee at the middle of the leg's depth; the hip joints a little below and outside the crotch; HeadTop_End at the crown (not a topknot or helmet crest); HandMiddle4 at the middle fingertip; Toe_End at the tip of the toe.
- Re-render with `--fit` and look. A dot outside the body is wrong.

## Keys

| key | what it is |
|---|---|
| `joints` | `{bone: [x, y, z]}` for every required bone (Mixamo names without the `mixamorig:` prefix): Hips, Spine, Spine1, Spine2, Neck, Head, HeadTop_End, and per side Shoulder, Arm, ForeArm, Hand, HandMiddle4, UpLeg, Leg, Foot, ToeBase, Toe_End |
| `sole` | the soles' height. The statue's hips-above-sole is mapped onto the donor's hips height |
| `cut` | the base is cut off at this height and the cut capped (just above `sole`) |
| `crumb` | loose pieces lower than this are dropped (bits of base left above the cut). Default `cut + 4` |
| `radius` | capsule radius per bone kind: `Hips`, `Spine`, `Spine1`, `Spine2`, `Neck`, `Head`, `Shoulder`, `Arm`, `ForeArm`, `Hand`, `UpLeg`, `Leg`, `Foot`, `ToeBase`, plus `pelvis_drop` (how far below the hip joint the pelvis capsule reaches) |
| `soft` | how gently weight falls off between neighbouring capsules (default 0.22; larger blends more) |
| `smooth` | rounds of weight smoothing over the mesh (default 8) |
| `triangles` | decimate to this many triangles (omit to keep all) |
| `map`, `map_q` | resize the colour map to this square size with `cwebp` at this quality (omit `map` to keep it as it is) |
| `hips_height` | override the donor's hips height (default: read from the donor's rest pose; also `--hips-height`) |
| `props` | list of props, below |
| `debug` | list of `{name, at: [x,y,z], size}` regions rendered close with `--debug` |

### A prop

| key | what it is |
|---|---|
| `name` | for the log |
| `bone` | the one bone it goes to, whole |
| `boxes` | `[[min xyz], [max xyz]]` boxes; a vertex inside any is the prop |
| `rods` | `[[a xyz], [b xyz], radius]`: a handle, a shaft, a staff |
| `bones` | bones whose whole share goes with the prop: `["LeftHand"]` locks the holding hand to the forearm the prop is on |
| `not` | boxes to take back out |
| `luma`, `sat` | `[lo, hi]` colour ranges (0..1, from the colour map): only vertices in range are the prop (the `bones` share is kept regardless) |
| `spare` | what is inside the prop's space but is not the prop: `{luma, sat, caps, within}` (e.g. the hand by its skin colour and nearness to the hand capsules) |
| `grow`, `grow_at` | rounds of taking in neighbours the colour test missed inside the boxes, when at least `grow_at` of a vertex's neighbours are in |
| `cut_from` | bones the prop was sculpted against: triangles bridging the prop to them are removed before smoothing, and the holes capped |
| `delete` | `true` removes the prop altogether |

## Misses, and what to change

| you see | change |
|---|---|
| a joint miss over 1 mm in the log | that joint's parent chain is inconsistent: re-mark the parent and child |
| skin stretched into sheets between a prop and the body | add those bones to `cut_from` |
| part of a prop left behind when the arm moves | widen its boxes or rods, or lower `luma`/`sat` limits, or add `grow` |
| the holding hand peeled off the prop | add the hand to the prop's `bones` |
| a half shell or hole where a prop was | the body behind it was never sculpted; tie the prop to the limb that covers it instead |
| the torso pulling the upper arm | lower `radius.Spine2` or raise `radius.Arm` |
| clothing torn at the hips in a high kick | raise `pelvis_drop` and `soft`, or more `smooth` |
| feet sliding or the figure floating | check `sole`; on the web, scale the hips' travel by `extras.legs` |
