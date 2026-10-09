"""Prepare the old woman for the dream: she dozes off, and her newspaper fractures.

Her head droops (rolled to her right and nodded forward, blended into the neck), so she
reads as asleep rather than reading.

Inserts shaders/PaperFracture.osl into the RenderMan network of her newspaper
material (M_Papers): the print color goes through the shader (crack lines) and
its presence output cuts away Voronoi pieces, more of them toward the top edge.
The fracture works in the mesh's object space, so it doesn't depend on the scene.

Newspaper (RenderMan only):
This edits the character asset (not the scene) because RfB takes materials
from the mesh, ignoring object-level material slot overrides.

Usage (Blender 4.5 Intel with RenderMan for Blender):
  Blender -b assets/derived/OldWoman_rman.blend --addons RenderManForBlender \
      --python tools/fracture_newspaper.py -- assets/derived/OldWoman_fractured_rman.blend \
      [--no-presence] [--param name=value ...]   (e.g. --param cellSize=0.03 crackDarkness=0.5 glowGain=0.5 newspaperScale=1.2 newspaperSag=40 headRoll=-20)
"""

import math
import os
import subprocess
import sys

import bpy
from mathutils import Quaternion, Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RMANTREE = os.environ.get("RMANTREE", "/Applications/Pixar/RenderManProServer-27.3")
FRACTURE_OSL = os.path.join(REPO, "shaders", "PaperFracture.osl")
CHAR_NAME = "31_OldWoman_Sit6_Reading"
NEWSPAPER_MATERIAL = "M_Papers"
# Exaggerated (dream logic) so the fracture reads at full-diorama framing.
NEWSPAPER_SCALE = 1.4
# Dozing head (mesh object space: she faces -Y, up is +Z, her right is -X).
HEAD_ROLL = -25.0   # degrees about +Y: negative tips the head to her right (screen left, toward the trail)
HEAD_PITCH = 12.0   # degrees about +X: positive nods the head forward
# Optional: the newspaper sags toward her lap, rotated forward about where her hands hold it.
# Off by default: held up, the newspaper reads more clearly (tried 35 degrees on Oct 9: too flat).
NEWSPAPER_SAG = 0.0  # degrees; keep < 90 so the top edge stays highest (the fracture works by height)
NEWSPAPER_GRIP_Z = 1.0  # object-space height where her hands hold the sides: the sag hinge
NECK_PIVOT = Vector((-0.015, -0.17, 1.22))  # below the chin (eyes at z ~1.33)
HEAD_BLEND = (1.17, 1.27)  # z range over which the rotation fades in (shoulders -> chin)
HEAD_RADIUS = (0.16, 0.30)  # horizontal distance from the neck over which it fades out (keeps the shoulders)
HAT_MATERIAL = "Hat"  # moves rigidly with the head
FRACTURE_START = 0.25  # fraction of the sheet's height where fracturing begins
# Glow matching the first paper scraps (GLOW_WARM / GLOW_GAIN[0] in build_layout.py).
GLOW_COLOR = (1.0, 0.75, 0.45)
GLOW_GAIN = 0.35
FRACTURE_PARAMS = {"cellSize": 0.07, "jitter": 0.9, "maxRemove": 0.97,
                   "crackWidth": 0.004, "crackDarkness": 0.65, "seed": 809}

from RenderManForBlender.rman_bl_nodes import __BL_NODES_MAP__ as NODES  # noqa: E402


def detach_rfb_handlers():
    """RfB's scene-update/save handlers scan textures and expand <blend_dir> against this file's
    folder, creating stray directories (e.g. assets/source/assets/derived/...). Not needed here."""
    for handlers in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.save_pre,
                     bpy.app.handlers.save_post, bpy.app.handlers.load_post):
        for handler in list(handlers):
            if getattr(handler, "__module__", "").startswith("RenderManForBlender"):
                handlers.remove(handler)


def compile_shader():
    oso = os.path.splitext(FRACTURE_OSL)[0] + ".oso"
    if not os.path.exists(oso) or os.path.getmtime(oso) < os.path.getmtime(FRACTURE_OSL):
        subprocess.run([os.path.join(RMANTREE, "bin", "oslc"), "-o", oso, FRACTURE_OSL], check=True)
    return oso


def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def droop_head(mesh, roll, pitch, exclude):
    """Rotate the head about the neck, blended by height and distance so the shoulders stay put."""
    full = Quaternion((0, 1, 0), math.radians(roll)) @ Quaternion((1, 0, 0), math.radians(pitch))
    hat_slots = {i for i, m in enumerate(mesh.materials) if m and m.name.startswith(HAT_MATERIAL)}
    hat = {v for p in mesh.polygons if p.material_index in hat_slots for v in p.vertices}
    moved = 0
    for v in mesh.vertices:
        if v.index in exclude:
            continue
        co = v.co
        if v.index in hat:
            w = 1.0
        else:
            radial = (Vector((co.x, co.y)) - NECK_PIVOT.xy).length
            w = smoothstep(*HEAD_BLEND, co.z) * (1.0 - smoothstep(*HEAD_RADIUS, radial))
        if w > 0.0:
            rot = Quaternion().slerp(full, w)
            v.co = NECK_PIVOT + rot @ (co - NECK_PIVOT)
            moved += 1
    return moved


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = os.path.abspath(argv[0])
    overrides = {}
    if "--param" in argv:
        for arg in argv[argv.index("--param") + 1:]:
            if "=" in arg:
                name, value = arg.split("=")
                overrides[name] = float(value)
    detach_rfb_handlers()
    bpy.context.scene.render.engine = "PRMAN_RENDER"  # RfB nodes can only be added under its engine
    char = bpy.data.objects[CHAR_NAME]
    mesh = char.data
    slot = next(i for i, m in enumerate(mesh.materials) if m and m.name.startswith(NEWSPAPER_MATERIAL))
    paper = sorted({v for p in mesh.polygons if p.material_index == slot for v in p.vertices})
    # Enlarge the newspaper about its bottom center and let it sag forward about the line where her hands hold it
    # (it shares no vertices with her hands/body).
    scale = overrides.pop("newspaperScale", NEWSPAPER_SCALE)
    cos = [mesh.vertices[v].co.copy() for v in paper]
    pivot = Vector((sum(c.x for c in cos) / len(cos), sum(c.y for c in cos) / len(cos), min(c.z for c in cos)))
    sag = Quaternion((1, 0, 0), math.radians(overrides.pop("newspaperSag", NEWSPAPER_SAG)))
    scaled = [pivot + (co - pivot) * scale for co in cos]
    grip = [c for c in scaled if abs(c.z - NEWSPAPER_GRIP_Z) < 0.06] or scaled
    hinge = Vector((pivot.x, sum(c.y for c in grip) / len(grip), NEWSPAPER_GRIP_Z))  # where her hands hold it
    for v, co in zip(paper, scaled):
        mesh.vertices[v].co = hinge + sag @ (co - hinge)
    roll = overrides.pop("headRoll", HEAD_ROLL)
    pitch = overrides.pop("headPitch", HEAD_PITCH)
    moved = droop_head(mesh, roll, pitch, exclude=set(paper))
    print(f"[fracture] head drooped (roll {roll}, pitch {pitch}): {moved} vertices")
    zs = [mesh.vertices[v].co.z for v in paper]
    bottom, top = min(zs), max(zs)

    nt = mesh.materials[slot].node_tree
    if any(n.bl_label == "PxrOSL" for n in nt.nodes):
        raise SystemExit("newspaper already fractured; run on the unfractured OldWoman_rman.blend")
    surf = next(n for n in nt.nodes if n.bl_label == "PxrSurface")
    metal = next(n for n in nt.nodes if n.bl_label == "PxrMetallicWorkflow")
    print_color = metal.inputs["baseColor"].links[0].from_socket

    oso = compile_shader()
    osl = nt.nodes.new(NODES["PxrOSL"])
    osl.location = (metal.location.x - 300, metal.location.y + 300)
    osl.codetypeswitch = "EXT"
    osl.shadercode = oso
    osl.RefreshNodes(bpy.context, nodeOR=osl)  # creates the shader's sockets
    # At render time <blend_dir> is the scene's folder (scenes/), even for linked libraries.
    osl["shadercode"] = "<blend_dir>/../" + os.path.relpath(oso, REPO)  # stored directly (see detach_rfb_handlers)
    params = dict(FRACTURE_PARAMS, startHeight=bottom + FRACTURE_START * (top - bottom), endHeight=top)
    glow_gain = overrides.pop("glowGain", GLOW_GAIN)  # not a shader parameter
    params.update(overrides)
    for name, value in params.items():
        osl.inputs[name].default_value = value
    # print x shade with a standard PxrBlend (routing the print color through the OSL node
    # turned it grey in RfB)
    blend = nt.nodes.new(NODES["PxrBlend"])
    blend.location = (metal.location.x - 150, metal.location.y + 150)
    blend.operation = "18"  # Multiply
    nt.links.new(print_color, blend.inputs["topRGB"])
    nt.links.new(osl.outputs["shade"], blend.inputs["bottomRGB"])
    nt.links.new(blend.outputs["resultRGB"], metal.inputs["baseColor"])

    # Self-illuminated like the paper scraps at the start of the trail (warm, dim): print x tint.
    glow = nt.nodes.new(NODES["PxrBlend"])
    glow.location = (blend.location.x, blend.location.y + 200)
    glow.operation = "18"  # Multiply
    glow.bottomRGB = GLOW_COLOR
    nt.links.new(blend.outputs["resultRGB"], glow.inputs["topRGB"])
    surf.enableGlow = True
    surf.glowGain = glow_gain
    nt.links.new(glow.outputs["resultRGB"], surf.inputs["glowColor"])
    if "--no-presence" not in argv:
        nt.links.new(osl.outputs["presence"], surf.inputs["presence"])

    bpy.context.preferences.filepaths.save_version = 0  # no .blend1 backup of the derived file
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print(f"[fracture] newspaper z {bottom:.3f}..{top:.3f}, fracture from {params['startHeight']:.3f}; saved {out}")


main()
