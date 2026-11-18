# Playing the donor's clips on the figure (three.js)

The rigged figure has no clips of its own. Load the donor GLB once for its clips, then give the figure a filtered copy of each.

```js
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clone as cloneSkinned } from "three/addons/utils/SkeletonUtils.js";

const loader = new GLTFLoader();
const [donor, figure] = await Promise.all([loader.loadAsync("/models/donor.glb"), loader.loadAsync("/models/figure.glb")]);

/* the donor's clips on the figure: rotations as they are, the hips' travel scaled by its leg length */
const legs = figure.userData.legs ?? 1;            /* the file's top-level extras land on gltf.userData */
const borrow = (clip) => {
  const k = clip.clone();
  k.tracks = k.tracks.filter((t) => /\.quaternion$/.test(t.name) || /Hips\.position$/.test(t.name));
  for (const t of k.tracks) if (/Hips\.position$/.test(t.name)) for (let i = 0; i < t.values.length; i++) t.values[i] *= legs;
  return k;
};

const root = cloneSkinned(figure.scene);
const mixer = new THREE.AnimationMixer(root);
const actions = donor.animations.map((c) => mixer.clipAction(borrow(c)));
actions[0].play();
```

Drop scale and the other bones' position tracks: they carry the donor's bone lengths and would stretch the figure back to the donor's proportions.

## Size

Bring the figure to the donor's **stature** and let it keep its own build. Measure both standing in a clip's first frame (the file rests in the donor's rest pose, often a T-pose), head joint above foot joint, not the bounding box (a raised hammer, a crest or a topknot would shrink the figure):

```js
const stature = (obj, mixer, clip) => {
  const a = mixer.clipAction(clip); a.play(); mixer.setTime(0); obj.updateMatrixWorld(true);
  const y = (n) => obj.getObjectByName(n).getWorldPosition(new THREE.Vector3()).y;
  const s = y("mixamorigHead") - y("mixamorigLeftFoot"); a.stop(); return s;
};
/* donorRoot / donorMixer: a clone of the donor set up the same way; donorScale: the scale you give the donor */
root.scale.setScalar(donorScale * stature(donorRoot, donorMixer, clip) / stature(root, mixer, clip));
```

Then stand it on the ground by its bounding box's lowest point in that frame.

## Weight

The example figure: 14K triangles, a 1K WebP colour map, quantised attributes: about 0.7 MB. Fetch it with the donor's file only when it is first needed. Load it with a plain `GLTFLoader` (no Draco decoder needed); `KHR_mesh_quantization` and `EXT_texture_webp` are supported by three.js out of the box.

## Shading

The figure carries one PBR material (metal 0, rough 1, double-sided) with the sculpt's baked colour map. If the scene uses a toon or cel shader on the donor, apply the same one to the figure with its own uniforms so both sit in the same light.
