"""Quick preview of a scene .blend through its own camera.

Usage:
  Blender -b scenes/<scene>.blend [--addons RenderManForBlender] \
      --python tools/preview_scene.py -- <out.png> [--engine eevee|prman] [--percent N] [--report] \
      [--focus x,y,z --ortho SIZE]

eevee (default) is a fast layout check; prman renders with RenderMan
(RIS on macOS) to check that materials and lights translate.
--report prints where key objects land in the frame instead of rendering.
"""

import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out = os.path.abspath(argv[0])
engine = argv[argv.index("--engine") + 1] if "--engine" in argv else "eevee"
percent = int(argv[argv.index("--percent") + 1]) if "--percent" in argv else 33

scene = bpy.context.scene
if engine == "prman":
    scene.render.engine = "PRMAN_RENDER"
else:
    engines = {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
scene.render.resolution_percentage = percent
if "--focus" in argv:  # zoom the scene camera onto a point: --focus x,y,z --ortho size
    from mathutils import Vector
    target = Vector([float(v) for v in argv[argv.index("--focus") + 1].split(",")])
    cam = scene.camera
    forward = cam.matrix_world.to_3x3() @ Vector((0, 0, -1))
    cam.location = target - forward * 40
    cam.data.ortho_scale = float(argv[argv.index("--ortho") + 1]) if "--ortho" in argv else 2.0
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = out
if "--report" in argv:
    # Where key objects land in frame: (x, y) in 0..1 from bottom-left, plus depth.
    from bpy_extras.object_utils import world_to_camera_view
    for obj in scene.objects:
        if obj.type in {"EMPTY", "MESH", "CURVE"} and obj.parent is None and not obj.name.startswith("PaperScrap_"):
            x, y, z = world_to_camera_view(scene, scene.camera, obj.matrix_world.translation)
            flag = "" if 0 <= x <= 1 and 0 <= y <= 1 else "  OUT OF FRAME"
            print(f"[frame] {obj.name:20s} x={x:.2f} y={y:.2f}{flag}")
else:
    bpy.ops.render.render(write_still=True)
    print(f"[preview] {out}")
