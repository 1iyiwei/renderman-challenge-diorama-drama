"""Make a RenderMan-ready copy of a Blender asset file.

RenderMan for Blender ignores image textures in plain Blender materials, and
its own "Convert Cycles to RenderMan" only knows Blender 3.x Principled BSDF
inputs. This adds a RenderMan network next to each material's Blender nodes
(which stay for Eevee previews):

  Principled BSDF            ->  PxrSurface
    Base Color, Metallic     ->    PxrMetallicWorkflow -> diffuse + specular colors
    Roughness                ->    specularRoughness
    Normal (Normal Map)      ->    PxrNormalMap -> bumpNormal
    Alpha                    ->    presence
    Emission Color/Strength  ->    glow
  Image Texture              ->  PxrTexture reading a .tex made by txmake
                                 (saved in <out dir>/tex/<out name>/)

Textures are found through reroutes and simple pass-through nodes (Mix, Color
Ramp, Normal Map); mix factors and ramps are not reproduced. Materials whose
Principled BSDF sits inside node groups use the first group's ("clean" over
"dirty"). Displacement is not converted.

Usage (Blender 4.5 Intel with RenderMan for Blender):
  Blender -b <source.blend> --addons RenderManForBlender \
      --python tools/convert_to_rman.py -- <out.blend> [--keep OBJECT ...]

  --keep OBJECT  keep only these objects (others are deleted before converting,
                 so their textures aren't converted needlessly)
"""

import concurrent.futures
import os
import subprocess
import sys

import bpy

RMANTREE = os.environ.get("RMANTREE", "/Applications/Pixar/RenderManProServer-27.3")
TXMAKE = os.path.join(RMANTREE, "bin", "txmake")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0])
KEEP = [argv[i + 1] for i, a in enumerate(argv) if a == "--keep"]
OUT_DIR = os.path.dirname(OUT)
TEX_DIR = os.path.join(OUT_DIR, "tex", os.path.splitext(os.path.basename(OUT))[0])

from RenderManForBlender.rman_bl_nodes import __BL_NODES_MAP__ as NODES  # noqa: E402

tx_jobs = {}  # source image path -> .tex path


def follow(socket):
    """(node, from_socket) feeding a socket, skipping reroutes; None if unlinked."""
    while socket.is_linked:
        link = socket.links[0]
        if link.from_node.bl_idname == "NodeReroute":
            socket = link.from_node.inputs[0]
            continue
        return link.from_node, link.from_socket
    return None


def find_image(socket, depth=0):
    """(image, "RGB" or "A") of the image texture driving a socket, or None."""
    hit = follow(socket)
    if hit is None or depth > 4:
        return None
    node, from_socket = hit
    if node.bl_idname == "ShaderNodeTexImage":
        return (node.image, "A" if from_socket.name == "Alpha" else "RGB") if node.image else None
    # Pass-through nodes: prefer color inputs over mix factors.
    for inp in sorted(node.inputs, key=lambda i: i.name in ("Factor", "Fac", "Strength")):
        found = find_image(inp, depth + 1)
        if found:
            return found
    return None


def find_principled(node_tree, depth=0):
    for node in node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            return node
    groups = [n for n in node_tree.nodes if n.bl_idname == "ShaderNodeGroup" and n.node_tree]
    groups.sort(key=lambda n: "dirty" in n.node_tree.name.lower())  # clean layer first
    for group in groups if depth < 3 else []:
        found = find_principled(group.node_tree, depth + 1)
        if found:
            return found
    return None


def set_param(node, param, value):
    if not hasattr(node, param):
        print(f"[rman]   {node.name}: no parameter {param}")
        return
    if isinstance(getattr(node, param), str) and not isinstance(value, str):
        value = str(value)  # RfB stores int menus as string enums
    setattr(node, param, value)


def tex_file(image):
    src = bpy.path.abspath(image.filepath, library=image.library)
    if image.packed_file:  # e.g. BigMediumSmall: packed, with paths from the vendor's machine
        src = os.path.join(TEX_DIR, "src", os.path.basename(image.filepath) or image.name)
        os.makedirs(os.path.dirname(src), exist_ok=True)
        if not os.path.exists(src):
            with open(src, "wb") as f:
                f.write(image.packed_file.data)
    elif not os.path.exists(src):
        print(f"[rman]   skipping missing image {image.name}")
        return None
    dst = os.path.join(TEX_DIR, os.path.basename(src) + ".tex")
    tx_jobs[src] = dst
    # Absolute: RfB resolves <blend_dir> against the scene file, not the linked library.
    # TODO: remap for cloud rendering.
    return dst


def add_rman_network(mat):
    nt = mat.node_tree
    principled = find_principled(nt)
    if principled is None:
        print(f"[rman]   {mat.name}: no Principled BSDF, left as is")
        return False
    x = 0

    def new(kind):
        nonlocal x
        node = nt.nodes.new(NODES[kind])
        node.location = (x, -1200)
        x -= 280
        return node

    output = nt.nodes.new("RendermanOutputNode")
    output.location = (400, -1200)
    surf = new("PxrSurface")
    surf.enablePrimarySpecular = True
    set_param(surf, "specularModelType", 1)  # GGX, as in the Oni materials
    textures = {}

    def texture(image):
        if image.name not in textures:
            path = tex_file(image)
            if path is None:
                return None
            node = new("PxrTexture")
            node.label = image.name
            set_param(node, "filename", path)
            set_param(node, "linearize", 1 if image.colorspace_settings.name == "sRGB" else 0)
            textures[image.name] = node
        return textures[image.name]

    def drive(input_name, dst, param, color):
        """Connect a Principled input to a RenderMan parameter (texture or constant)."""
        sock = principled.inputs[input_name]
        found = find_image(sock)
        tex = texture(found[0]) if found else None
        if tex is not None:
            out_name = "resultA" if found[1] == "A" else ("resultRGB" if color else "resultR")
            nt.links.new(tex.outputs[out_name], dst.inputs[param])
        elif not sock.is_linked or not found:
            value = sock.default_value
            set_param(dst, param, tuple(value)[:3] if color else value)

    metal = new("PxrMetallicWorkflow")
    drive("Base Color", metal, "baseColor", True)
    drive("Metallic", metal, "metallic", False)
    nt.links.new(metal.outputs["resultDiffuseRGB"], surf.inputs["diffuseColor"])
    nt.links.new(metal.outputs["resultSpecularFaceRGB"], surf.inputs["specularFaceColor"])
    nt.links.new(metal.outputs["resultSpecularEdgeRGB"], surf.inputs["specularEdgeColor"])
    drive("Roughness", surf, "specularRoughness", False)

    found = find_image(principled.inputs["Normal"])
    if found and texture(found[0]) is not None:
        nmap = new("PxrNormalMap")
        nt.links.new(texture(found[0]).outputs["resultRGB"], nmap.inputs["inputRGB"])
        hit = follow(principled.inputs["Normal"])
        if hit and hit[0].bl_idname == "ShaderNodeNormalMap":
            set_param(nmap, "bumpScale", hit[0].inputs["Strength"].default_value)
        nt.links.new(nmap.outputs["resultN"], surf.inputs["bumpNormal"])

    if principled.inputs["Alpha"].is_linked:
        drive("Alpha", surf, "presence", False)

    strength = principled.inputs["Emission Strength"].default_value
    if principled.inputs["Emission Color"].is_linked and strength > 0:
        surf.enableGlow = True
        drive("Emission Color", surf, "glowColor", True)
        set_param(surf, "glowGain", strength)

    nt.links.new(surf.outputs["bxdf_out"], output.inputs["bxdf_in"])
    return True


def txmake(src, dst):
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return None
    cmd = [TXMAKE, "-resize", "round-", "-mode", "periodic", "-compression", "zip", src, dst]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return None if result.returncode == 0 else f"{os.path.basename(src)}: {result.stderr.strip()[:200]}"


def main():
    if KEEP:
        for obj in list(bpy.data.objects):
            if obj.name not in KEEP:
                bpy.data.objects.remove(obj)
        bpy.data.orphans_purge(do_recursive=True)
    scene = bpy.context.scene
    scene.render.engine = "PRMAN_RENDER"  # RfB nodes can only be added under its engine
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")  # RfB's save hook expects one

    materials = {s.material for o in scene.objects for s in getattr(o, "material_slots", []) if s.material}
    converted = sum(add_rman_network(m) for m in sorted(materials, key=lambda m: m.name)
                    if m.use_nodes and not any(n.bl_idname == "RendermanOutputNode" for n in m.node_tree.nodes))

    os.makedirs(TEX_DIR, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        errors = [e for e in pool.map(lambda job: txmake(*job), tx_jobs.items()) if e]
    for e in errors:
        print(f"[rman]   txmake failed: {e}")

    bpy.ops.wm.save_as_mainfile(filepath=OUT)
    print(f"[rman] {converted}/{len(materials)} materials converted, {len(tx_jobs)} textures, saved {OUT}")


main()
