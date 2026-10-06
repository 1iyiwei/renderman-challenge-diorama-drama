"""Render a quick isometric 16:9 preview of a KitBash3D set with a character for scale.

Usage (headless, one set per run):
  Blender -b assets/KitBash3D/<Set>.blend --python tools/preview_set.py -- \
      <out.png> [--hide PREFIX ...] [--only PREFIX ...]

  --hide PREFIX  hide objects whose names start with PREFIX
  --only PREFIX  keep only objects whose names start with PREFIX (plus lights)
The character (31_OldWoman_Sit6_Reading) is appended from the BigMediumSmall
WaterVillage .blend and placed in front of the set on its lowest level.
"""

import os
import sys

import bpy
from mathutils import Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAR_BLEND = os.path.join(REPO, "assets", "BMS_Pixar-Collab_Assets",
                          "WaterVillage _6Crowd_Characters", "WaterVillage_POSED.blend")
CHAR_NAME = "31_OldWoman_Sit6_Reading"


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out, hide, only = None, [], []
    it = iter(argv)
    for a in it:
        if a == "--hide":
            hide.append(next(it))
        elif a == "--only":
            only.append(next(it))
        else:
            out = a
    return out, hide, only


def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def main():
    out, hide, only = parse_args()
    scene = bpy.context.scene
    for o in scene.objects:
        if o.type == "MESH" and (any(o.name.startswith(p) for p in hide) or
                                 (only and not any(o.name.startswith(p) for p in only))):
            o.hide_render = o.hide_viewport = True
    shown = [o for o in scene.objects if o.type == "MESH" and not o.hide_render]
    lo, hi = bounds(shown)

    with bpy.data.libraries.load(CHAR_BLEND) as (src, dst):
        dst.objects = [CHAR_NAME]
    char = dst.objects[0]
    scene.collection.objects.link(char)
    clo, chi = bounds([char])
    char.location += Vector(((lo.x + hi.x) / 2 - (clo.x + chi.x) / 2,
                             lo.y - 0.8 - chi.y,
                             lo.z - clo.z))
    bpy.context.view_layer.update()
    lo, hi = bounds(shown + [char])

    center, radius = (lo + hi) / 2, (hi - lo).length / 2
    direction = Vector((1, -1, 0.82)).normalized()  # ~35 degree elevation, 45 degree azimuth
    cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
    scene.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = radius * 2.1 * 16 / 9  # fit the bounding sphere vertically
    cam.location = center + direction * radius * 3
    cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_start, cam.data.clip_end = radius * 0.01, radius * 10
    scene.camera = cam

    # Neutral sky + key light so dark sets stay readable; this is a layout preview, not a lighting test.
    scene.world = bpy.data.worlds.new("PreviewWorld")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.6, 0.7, 1)
    sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", "SUN"))
    sun.data.energy = 3
    sun.rotation_euler = (0.7, 0.3, 0.9)
    scene.collection.objects.link(sun)
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.abspath(out)
    bpy.ops.render.render(write_still=True)
    print(f"[preview] {os.path.basename(out)}: set size {[round(v, 2) for v in (hi - lo)]} m")


main()
