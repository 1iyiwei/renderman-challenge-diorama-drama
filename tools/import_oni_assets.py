"""Import the Netflix/Tonko House Oni assets into Blender.

The supplied .usda files are material "look" layers whose geometry is an
Alembic reference. Blender's USD importer can't resolve .abc references, so a
plain File > Import > USD yields an empty placeholder. This script imports the
.abc geometry directly and rebuilds each material from the textures named in
the .usda (Principled BSDF with UDIM PNGs).

Usage:
  Inside Blender: open in the Scripting tab and Run Script.
  Headless:
    Blender -b --python tools/import_oni_assets.py -- assets/derived/oni_assets.blend [asset ...]
"""

import os
import re
import sys

import bpy
from mathutils import Vector
from pxr import Sdf

ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "Diorama_Drama_Netflix_Megalis")
USD_DIR = os.path.join(ROOT, "usd")
SPACING = 0.6  # gap between assets laid out along X, in meters


def udim_tiles(png):
    """Sorted [(tile number, file)] for a path with a <UDIM> token, or [(None, png)]."""
    if "<UDIM>" not in png:
        return [(None, png)] if os.path.exists(png) else []
    tile_dir, pattern = os.path.split(png)
    if not os.path.isdir(tile_dir):
        return []
    regex = re.compile(re.escape(pattern).replace(re.escape("<UDIM>"), r"(\d{4})") + "$")
    return sorted((int(m.group(1)), os.path.join(tile_dir, f))
                  for f in os.listdir(tile_dir) if (m := regex.match(f)))


def tex_path(usd_file, asset_path):
    """Resolve a PxrTexture filename to an on-disk PNG with Blender's <UDIM> token."""
    path = asset_path[:-4] if asset_path.endswith(".tex") else asset_path
    tex_dir = os.path.join(ROOT, "tex")
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(os.path.dirname(usd_file), path))
    if not udim_tiles(path):
        # Some paths are absolute paths from the authors' machines; fall back
        # to <tex dir>/<asset folder>/<file>.
        folder = os.path.basename(os.path.dirname(path))
        path = os.path.join(tex_dir, folder, os.path.basename(path))
    return path if udim_tiles(path) else None


def binding_target(spec):
    """Material name of a prim spec's material:binding, or None."""
    rel = spec.relationships.get("material:binding")
    if rel is None:
        return None
    targets = list(rel.targetPathList.explicitItems) or list(rel.targetPathList.prependedItems)
    return targets[0].name if targets else None


def read_usd(usd_file):
    """Return (abc_path, {material: {slot: png}}, {prim name: material}, root material)."""
    layer = Sdf.Layer.FindOrOpen(usd_file)
    root = layer.rootPrims[0]
    abc = root.referenceList.prependedItems[0].assetPath
    if not os.path.isabs(abc) or not os.path.exists(abc):
        # e.g. setsubun_bagClosed points at /depts/tools/...; remap into geo/.
        rel = abc.split("/geo/")[-1]
        abc = os.path.join(ROOT, "geo", rel)

    materials = {}
    mat_root = layer.GetPrimAtPath("/materials")
    for mat in mat_root.nameChildren if mat_root else []:
        slots = {}
        for shader in mat.nameChildren:
            attr = shader.attributes.get("inputs:filename")
            if attr is not None and attr.default is not None:
                png = tex_path(usd_file, attr.default.path)
                if png:
                    slots[shader.name] = png
        materials[mat.name] = slots

    bindings = {}

    def walk(spec):
        target = binding_target(spec)
        if target:
            bindings[spec.name] = target
        for child in spec.nameChildren:
            walk(child)

    for child in root.nameChildren:
        walk(child)
    root_mat = binding_target(root)
    return abc, materials, bindings, root_mat


def load_image(png, non_color):
    tiles = udim_tiles(png)
    img = bpy.data.images.load(tiles[0][1], check_existing=True)
    if tiles[0][0] is not None:
        img.source = "TILED"  # Blender scans the folder for all sibling tiles
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    elif "_LIN" in os.path.basename(png):
        img.colorspace_settings.name = "Linear Rec.709"
    return img


def build_material(name, slots):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    out = nt.nodes["Material Output"]

    def tex(slot, non_color, y):
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = load_image(slots[slot], non_color)
        node.location = (-700, y)
        node.label = slot
        return node

    if "DIFFCOL" in slots:
        nt.links.new(tex("DIFFCOL", False, 300).outputs["Color"], bsdf.inputs["Base Color"])
    if "METAL" in slots:
        nt.links.new(tex("METAL", True, 0).outputs["Color"], bsdf.inputs["Metallic"])
    if "ROUGH" in slots:
        nt.links.new(tex("ROUGH", True, -300).outputs["Color"], bsdf.inputs["Roughness"])
    if "NOR" in slots:
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.location = (-300, -600)
        nt.links.new(tex("NOR", True, -600).outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    if "HEIGHT" in slots:
        disp = nt.nodes.new("ShaderNodeDisplacement")
        disp.location = (-300, -900)
        disp.inputs["Scale"].default_value = 0.01  # dispAmount in the .usda
        disp.inputs["Midlevel"].default_value = 0.0
        nt.links.new(tex("HEIGHT", True, -900).outputs["Color"], disp.inputs["Height"])
        nt.links.new(disp.outputs["Displacement"], out.inputs["Displacement"])
    return mat


def import_asset(usd_file, x_offset):
    name = os.path.splitext(os.path.basename(usd_file))[0]
    abc, materials, bindings, root_mat = read_usd(usd_file)

    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    layer_coll = bpy.context.view_layer.layer_collection.children[coll.name]
    bpy.context.view_layer.active_layer_collection = layer_coll

    before = set(bpy.data.objects)
    bpy.ops.wm.alembic_import(filepath=abc)
    new_objs = [o for o in bpy.data.objects if o not in before]

    for obj in new_objs:
        if obj.type != "MESH":
            continue
        mat_name = None
        o = obj
        while o is not None and mat_name is None:  # nearest bound ancestor wins
            mat_name = bindings.get(o.name) or bindings.get(o.data.name if o is obj else "")
            o = o.parent
        mat_name = mat_name or root_mat
        if mat_name in materials:
            obj.data.materials.clear()
            obj.data.materials.append(build_material(mat_name, materials[mat_name]))
        obj.data.shade_smooth()

    roots = [o for o in new_objs if o.parent is None]
    meshes = [o for o in new_objs if o.type == "MESH"]
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box] or [Vector()]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    width = hi.x - lo.x
    for r in roots:
        r.location.x += x_offset - lo.x
    # Pivot for collection instances: bottom center of the asset.
    coll.instance_offset = (x_offset + width / 2, (lo.y + hi.y) / 2, lo.z)
    dims = ", ".join(f"{v:.3f}" for v in hi - lo)
    print(f"[oni] {name}: {len(meshes)} meshes, size ({dims}) m, abc={os.path.relpath(abc, ROOT)}")
    return width


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv and argv[0].endswith(".blend") else None
    wanted = [a for a in argv if not a.endswith(".blend")]
    files = sorted(f for f in os.listdir(USD_DIR) if f.endswith(".usda"))
    if out:  # headless batch: start from an empty scene, not the default cube
        bpy.ops.wm.read_factory_settings(use_empty=True)
    if wanted:
        files = [f for f in files if os.path.splitext(f)[0] in wanted]
    x = 0.0
    for f in files:
        x += import_asset(os.path.join(USD_DIR, f), x) + SPACING
    if out:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))


main()
