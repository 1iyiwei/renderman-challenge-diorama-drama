"""Build a first-draft layout .blend for the "Paper Soul" diorama.

Everything heavy is *linked* (not copied) from assets/, so the scene file
stays small enough for git:
  - KitBash3D Wood Collector house (collection instance)
  - BigMediumSmall old woman reading (local object using the linked mesh)
  - Oni props from assets/derived/oni_assets.blend (collection instances;
    build that first with tools/import_oni_assets.py)
Placeholder story elements (paper trail, string) and lights/camera are
created locally. Positions are Wood Collector world coordinates (meters).

Usage (Blender 4.5, Intel build for RenderMan):
  Blender -b --factory-startup --addons RenderManForBlender \
      --python tools/build_layout.py -- scenes/paper_soul_v001.blend [--force]
"""

import math
import os
import random
import sys

import addon_utils
import bpy
from mathutils import Matrix, Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(REPO, "assets")
WOOD_COLLECTOR = os.path.join(ASSETS, "KitBash3D", "WoodCollector.blend")
WOOD_COLLECTOR_COLL = "KB3D_SHG_BldgSmWoodCollector_A"
CHAR_BLEND = os.path.join(ASSETS, "BMS_Pixar-Collab_Assets",
                          "WaterVillage _6Crowd_Characters", "WaterVillage_POSED.blend")
CHAR_NAME = "31_OldWoman_Sit6_Reading"
ONI_BLEND = os.path.join(ASSETS, "derived", "oni_assets.blend")

VERANDA_Z = 0.59  # floor height of the L-shaped veranda (south + west sides)

# Character: west veranda near the south-west corner, facing west (-X).
CHAR_POS = Vector((-5.1, -2.4, VERANDA_Z))
CHAR_ROT_Z = math.radians(-90)

# Oni props: (collection, location of bottom-center pivot, rotation XYZ degrees, scale)
PROPS = [
    ("clock",              (-3.9, -3.00, 1.45),        (0, 0, 0),   1.0),  # on the south wall
    ("kakuremino",         (-3.0, -3.34, 0.75),        (0, 0, 0),   1.0),  # hanging, empty
    ("setsubun_bagClosed", (-4.75, -1.75, VERANDA_Z),  (0, 0, 20),  2.5),  # still tied shut
    ("cutleryKnife",       (-5.6, -3.2, VERANDA_Z + 0.027), (90, 0, 75), 1.0),  # beside the string
]

# Paper trail: from the newspaper, west past the roof eave and the edge of the ground,
# so the crane is silhouetted against the empty background on the left of the frame.
TRAIL_START = Vector((-5.75, -2.4, 1.75))
TRAIL_CTRL = Vector((-7.0, -2.2, 2.7))
CRANE_POS = Vector((-8.6, -2.6, 2.2))
TRAIL_COUNT = 26
TRAIL_SEED = 809  # Aug 9

# String: tied to the stool leg, along the floor past the knife, over the edge, up to the crane.
STRING_POINTS = [(-4.85, -2.75, VERANDA_Z + 0.03), (-5.5, -2.95, VERANDA_Z + 0.004),
                 (-5.85, -2.9, VERANDA_Z + 0.004), (-7.2, -2.9, 1.5), tuple(CRANE_POS)]

CAMERA_TARGET = Vector((-5.4, -2.2, 1.7))
CAMERA_DIR = Vector((-1, -1, 0.9))  # looking from the south-west, ~32 degrees down
CAMERA_ORTHO_SCALE = 9.5


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = next((a for a in argv if a.endswith(".blend")), "scenes/paper_soul_v001.blend")
    return os.path.abspath(out), "--force" in argv


def new_collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def link_collection(blend, name):
    with bpy.data.libraries.load(blend, link=True, relative=True) as (src, dst):
        if name not in src.collections:
            raise RuntimeError(f"{name} not found in {blend}")
        dst.collections = [name]
    return dst.collections[0]


def instance(coll_src, name, parent_coll, location=(0, 0, 0), rotation=(0, 0, 0), scale=1.0):
    empty = bpy.data.objects.new(name, None)
    empty.instance_type = "COLLECTION"
    empty.instance_collection = coll_src
    empty.location = location
    empty.rotation_euler = [math.radians(a) for a in rotation]
    empty.scale = (scale, scale, scale)
    parent_coll.objects.link(empty)
    return empty


def add_character(parent_coll):
    with bpy.data.libraries.load(CHAR_BLEND, link=True, relative=True) as (src, dst):
        dst.objects = [CHAR_NAME]
    linked = dst.objects[0]
    obj = bpy.data.objects.new("OldWoman", linked.data)  # local transform, linked mesh + materials
    for mod in linked.modifiers:
        print(f"[layout] note: character modifier {mod.type} not copied")
    parent_coll.objects.link(obj)
    # Put the bottom-center of her bounding box at CHAR_POS.
    lo = Vector([min(c[i] for c in obj.bound_box) for i in range(3)])
    hi = Vector([max(c[i] for c in obj.bound_box) for i in range(3)])
    pivot = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    rot = Matrix.Rotation(CHAR_ROT_Z, 4, "Z")
    obj.matrix_world = Matrix.Translation(CHAR_POS) @ rot @ Matrix.Translation(-pivot)
    return obj


def paper_material():
    mat = bpy.data.materials.new("PaperScrap")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.82, 0.76, 0.62, 1)
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Subsurface Weight"].default_value = 0.3  # thin paper glows when backlit
    bsdf.inputs["Subsurface Radius"].default_value = (0.02, 0.015, 0.01)
    mat.use_backface_culling = False
    return mat


def scrap_mesh(name, size, fold, rng):
    """A torn quad creased along its diagonal; fold=0 is flat, fold=1 is folded ~150 degrees."""
    j = lambda: rng.uniform(-0.12, 0.12) * size
    corners = [Vector((0 + j(), 0 + j(), 0)), Vector((size + j(), 0 + j(), 0)),
               Vector((size + j(), size + j(), 0)), Vector((0 + j(), size + j(), 0))]
    axis = (corners[2] - corners[0]).normalized()
    hinge = Matrix.Translation(corners[0]) @ Matrix.Rotation(math.radians(150) * fold, 4, axis) \
        @ Matrix.Translation(-corners[0])
    corners[1] = hinge @ corners[1]
    center = sum(corners, Vector()) / 4
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([c - center for c in corners], [], [(0, 1, 2), (0, 2, 3)])
    return mesh


def bezier(p0, p1, p2, t):
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def add_paper_trail(parent_coll, oni_crane):
    rng = random.Random(TRAIL_SEED)
    mat = paper_material()
    for i in range(TRAIL_COUNT):
        # Stratified jitter along the path: one scrap per stratum, so spacing is even but not regular.
        t = (i + rng.uniform(0.15, 0.85)) / TRAIL_COUNT * 0.92
        pos = bezier(TRAIL_START, TRAIL_CTRL, CRANE_POS, t)
        spread = 0.35 * math.sin(math.pi * t)  # loose in the middle, gathered at both ends
        pos += Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.5, 0.5))) * spread
        mesh = scrap_mesh(f"PaperScrap_{i:02d}", rng.uniform(0.08, 0.14), t, rng)
        mesh.materials.append(mat)
        obj = bpy.data.objects.new(mesh.name, mesh)
        obj.location = pos
        obj.rotation_euler = [rng.uniform(0, 2 * math.pi) for _ in range(3)]
        parent_coll.objects.link(obj)
    crane = instance(oni_crane, "Crane", parent_coll, CRANE_POS, (0, 0, -135), 0.6)
    return crane


def add_string(parent_coll):
    curve = bpy.data.curves.new("SoulString", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.003
    spline = curve.splines.new("NURBS")
    spline.points.add(len(STRING_POINTS) - 1)
    for p, co in zip(spline.points, STRING_POINTS):
        p.co = (*co, 1)
    spline.use_endpoint_u = True
    spline.order_u = 3
    mat = bpy.data.materials.new("String")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.5, 0.05, 0.04, 1)
    curve.materials.append(mat)
    obj = bpy.data.objects.new("SoulString", curve)
    parent_coll.objects.link(obj)
    return obj


def add_lights(parent_coll):
    world = bpy.data.worlds.new("PreDawn")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.03, 0.045, 0.09, 1)
    bg.inputs["Strength"].default_value = 1.0
    bpy.context.scene.world = world

    def light(name, kind, location, color, energy, **kw):
        data = bpy.data.lights.new(name, kind)
        data.color = color
        data.energy = energy
        for k, v in kw.items():
            setattr(data, k, v)
        obj = bpy.data.objects.new(name, data)
        obj.location = location
        parent_coll.objects.link(obj)
        return obj

    # Cold pre-dawn sky from the east, low.
    sky = light("DawnSky", "SUN", (0, 0, 10), (0.55, 0.68, 1.0), 0.6, angle=math.radians(10))
    sky.rotation_euler = (math.radians(65), 0, math.radians(100))
    # Warm practical lantern by her stool (placeholder: no lantern model yet).
    light("LanternWarm", "POINT", (-4.75, -1.45, 1.35), (1.0, 0.55, 0.25), 40, shadow_soft_size=0.06)
    # Faint warm glow from the paper lantern on the south-west post.
    light("PostLantern", "POINT", (-5.5, -5.5, 4.2), (1.0, 0.6, 0.3), 60, shadow_soft_size=0.15)


def add_camera(parent_coll):
    cam = bpy.data.objects.new("DioramaCam", bpy.data.cameras.new("DioramaCam"))
    d = CAMERA_DIR.normalized()
    cam.location = CAMERA_TARGET + d * 30
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = CAMERA_ORTHO_SCALE
    cam.data.clip_start, cam.data.clip_end = 1, 80
    parent_coll.objects.link(cam)
    bpy.context.scene.camera = cam


def setup_render():
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = 3840, 2160  # challenge max, 16:9
    scene.render.resolution_percentage = 25
    if hasattr(scene, "renderman"):
        scene.render.engine = "PRMAN_RENDER"
        scene.renderman.renderVariant = "xpu"  # falls back to RIS on macOS; XPU on the cloud farm
    else:
        print("[layout] RenderMan add-on not loaded; leaving default engine")


def main():
    out, force = parse_args()
    if os.path.exists(out) and not force:
        raise SystemExit(f"{out} exists; bump the version number or pass --force")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)  # also unloads add-ons
    bpy.ops.wm.save_as_mainfile(filepath=out)  # save first so library paths are made relative
    addon_utils.enable("RenderManForBlender", default_set=False)  # after the empty save: its save hook needs a world

    set_coll, char_coll = new_collection("Set"), new_collection("Character")
    props_coll, soul_coll = new_collection("Props"), new_collection("PaperSoul")
    light_coll, cam_coll = new_collection("Lights"), new_collection("Camera")

    instance(link_collection(WOOD_COLLECTOR, WOOD_COLLECTOR_COLL), "WoodCollector", set_coll)
    add_character(char_coll)
    for name, loc, rot, scale in PROPS:
        instance(link_collection(ONI_BLEND, name), name, props_coll, loc, rot, scale)
    add_paper_trail(soul_coll, link_collection(ONI_BLEND, "origami"))
    add_string(soul_coll)
    add_lights(light_coll)
    add_camera(cam_coll)
    setup_render()

    bpy.ops.wm.save_as_mainfile(filepath=out)
    print(f"[layout] saved {os.path.relpath(out, REPO)} ({os.path.getsize(out) / 1e6:.1f} MB)")
    for lib in bpy.data.libraries:
        print(f"[layout] linked {lib.filepath}")


main()
