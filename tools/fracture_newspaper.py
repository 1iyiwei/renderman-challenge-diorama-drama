"""Make the old woman's newspaper fracture toward its top edge (RenderMan only).

Inserts shaders/PaperFracture.osl into the RenderMan network of her newspaper
material (M_Papers): the print color goes through the shader (crack lines) and
its presence output cuts away Voronoi pieces, more of them toward the top edge.
The fracture works in the mesh's object space, so it doesn't depend on the scene.

This edits the character asset (not the scene) because RfB takes materials
from the mesh, ignoring object-level material slot overrides.

Usage (Blender 4.5 Intel with RenderMan for Blender):
  Blender -b assets/derived/OldWoman_rman.blend --addons RenderManForBlender \
      --python tools/fracture_newspaper.py -- assets/derived/OldWoman_fractured_rman.blend \
      [--no-presence] [--param name=value ...]   (e.g. --param cellSize=0.03 crackDarkness=0.5)
"""

import os
import subprocess
import sys

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RMANTREE = os.environ.get("RMANTREE", "/Applications/Pixar/RenderManProServer-27.3")
FRACTURE_OSL = os.path.join(REPO, "shaders", "PaperFracture.osl")
CHAR_NAME = "31_OldWoman_Sit6_Reading"
NEWSPAPER_MATERIAL = "M_Papers"
FRACTURE_START = 0.45  # fraction of the sheet's height where fracturing begins
FRACTURE_PARAMS = {"cellSize": 0.045, "jitter": 0.9, "maxRemove": 0.97,
                   "crackWidth": 0.004, "crackDarkness": 0.65, "seed": 809}

from RenderManForBlender.rman_bl_nodes import __BL_NODES_MAP__ as NODES  # noqa: E402


def compile_shader():
    oso = os.path.splitext(FRACTURE_OSL)[0] + ".oso"
    if not os.path.exists(oso) or os.path.getmtime(oso) < os.path.getmtime(FRACTURE_OSL):
        subprocess.run([os.path.join(RMANTREE, "bin", "oslc"), "-o", oso, FRACTURE_OSL], check=True)
    return oso


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = os.path.abspath(argv[0])
    overrides = {}
    if "--param" in argv:
        for arg in argv[argv.index("--param") + 1:]:
            if "=" in arg:
                name, value = arg.split("=")
                overrides[name] = float(value)
    bpy.context.scene.render.engine = "PRMAN_RENDER"  # RfB nodes can only be added under its engine
    char = bpy.data.objects[CHAR_NAME]
    mesh = char.data
    slot = next(i for i, m in enumerate(mesh.materials) if m and m.name.startswith(NEWSPAPER_MATERIAL))
    zs = [mesh.vertices[v].co.z for p in mesh.polygons if p.material_index == slot for v in p.vertices]
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
    osl.shadercode = "<blend_dir>/../" + os.path.relpath(oso, REPO)
    params = dict(FRACTURE_PARAMS, startHeight=bottom + FRACTURE_START * (top - bottom), endHeight=top)
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
    if "--no-presence" not in argv:
        nt.links.new(osl.outputs["presence"], surf.inputs["presence"])

    bpy.ops.wm.save_as_mainfile(filepath=out)
    print(f"[fracture] newspaper z {bottom:.3f}..{top:.3f}, fracture from {params['startHeight']:.3f}; saved {out}")


main()
