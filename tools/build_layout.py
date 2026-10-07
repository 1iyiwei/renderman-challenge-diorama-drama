"""Build a first-draft layout .blend for the "Paper Soul" diorama.

Everything heavy is *linked* (not copied) from the RenderMan-ready copies in
assets/derived/, so the scene file stays small enough for git:
  - KitBash3D Wood Collector house (collection instance), WoodCollector_rman.blend
  - BigMediumSmall old woman reading (local object using the linked mesh), OldWoman_rman.blend
    (make both with tools/convert_to_rman.py; see README)
  - Oni props (collection instances), oni_assets.blend from tools/import_oni_assets.py
Placeholder story elements (paper trail, string) and lights/camera are
created locally. Positions are Wood Collector world coordinates (meters).

Usage (Blender 4.5, Intel build for RenderMan):
  Blender -b --factory-startup --addons RenderManForBlender \
      --python tools/build_layout.py -- scenes/paper_soul_v002.blend [--force] \
      [--framing diorama|closeup] [--elevation DEGREES]
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
WOOD_COLLECTOR = os.path.join(ASSETS, "derived", "WoodCollector_rman.blend")
WOOD_COLLECTOR_COLL = "KB3D_SHG_BldgSmWoodCollector_A"
CHAR_BLEND = os.path.join(ASSETS, "derived", "OldWoman_rman.blend")
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

# Paper trail: from the newspaper, out from under the eave, then rising in front of the
# dark thatched roof (seen from the west-south-west), the crane high against the roof.
TRAIL_START = Vector((-5.75, -2.4, 1.75))
TRAIL_CTRL = Vector((-7.6, -2.9, 2.4))
CRANE_POS = Vector((-7.9, -1.6, 4.6))
TRAIL_COUNT = 32
TRAIL_SEED = 809  # Aug 9
# Exaggerated for readability at full-diorama framing (dream logic, not newspaper scale).
SCRAP_SIZE = (0.16, 0.28)
TRAIL_SPREAD = 0.5

# String: tied to the stool leg, along the floor past the knife, over the edge, up to the crane.
STRING_POINTS = [(-4.85, -2.75, VERANDA_Z + 0.03), (-5.5, -2.95, VERANDA_Z + 0.004),
                 (-5.85, -2.9, VERANDA_Z + 0.004), (-7.4, -3.2, 2.2), tuple(CRANE_POS)]

# Floor lantern in front of her (west, toward the camera side): the warm pool she sits in.
LANTERN_POS = Vector((-5.5, -1.8, VERANDA_Z))
CRANE_SCALE = 3.0

# Looking from the west-south-west (Li-Yi's v002 camera azimuth), 22 degrees down:
# a compromise between her side view (12) and isometric (~30-35).
CAMERA_AZIMUTH = 21.0     # degrees, direction the camera looks, from +X toward +Y
CAMERA_ELEVATION = 22.0   # degrees below horizontal
# Framing: "diorama" fits the whole ground base (the challenge wants a tiny self-contained world);
# "closeup" uses CAMERA_TARGET / CAMERA_ORTHO_SCALE around the veranda corner.
CAMERA_TARGET = Vector((-5.4, -2.2, 1.7))
CAMERA_ORTHO_SCALE = 9.5
FRAME_MARGIN = 1.05


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = next((a for a in argv if a.endswith(".blend")), "scenes/paper_soul_v002.blend")
    framing = argv[argv.index("--framing") + 1] if "--framing" in argv else "diorama"
    elevation = float(argv[argv.index("--elevation") + 1]) if "--elevation" in argv else CAMERA_ELEVATION
    return os.path.abspath(out), "--force" in argv, framing, elevation


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


def rman_surface(mat, **params):
    """Add a RenderMan PxrSurface network to a material (alongside its Blender nodes)."""
    if bpy.context.scene.render.engine != "PRMAN_RENDER":
        return
    from RenderManForBlender.rman_bl_nodes import __BL_NODES_MAP__ as nodes
    nt = mat.node_tree
    output = nt.nodes.new("RendermanOutputNode")
    output.location = (400, -600)
    surf = nt.nodes.new(nodes["PxrSurface"])
    surf.location = (100, -600)
    for name, value in params.items():
        setattr(surf, name, value)
    nt.links.new(surf.outputs["bxdf_out"], output.inputs["bxdf_in"])


def paper_material():
    mat = bpy.data.materials.new("PaperScrap")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.82, 0.76, 0.62, 1)
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Subsurface Weight"].default_value = 0.3  # thin paper glows when backlit
    bsdf.inputs["Subsurface Radius"].default_value = (0.02, 0.015, 0.01)
    mat.use_backface_culling = False
    rman_surface(mat, diffuseColor=(0.82, 0.76, 0.62), diffuseDoubleSided=1,
                 diffuseTransmitGain=0.45, diffuseTransmitColor=(1.0, 0.85, 0.6),  # thin paper, backlit glow
                 enableGlow=True, glowColor=(0.75, 0.85, 1.0), glowGain=0.08)  # faint spirit glow
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
        spread = TRAIL_SPREAD * math.sin(math.pi * t)  # loose in the middle, gathered at both ends
        pos += Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.5, 0.5))) * spread
        mesh = scrap_mesh(f"PaperScrap_{i:02d}", rng.uniform(*SCRAP_SIZE), t, rng)
        mesh.materials.append(mat)
        obj = bpy.data.objects.new(mesh.name, mesh)
        obj.location = pos
        obj.rotation_euler = [rng.uniform(0, 2 * math.pi) for _ in range(3)]
        parent_coll.objects.link(obj)
    crane = instance(oni_crane, "Crane", parent_coll, CRANE_POS, (0, 0, -135), CRANE_SCALE)
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
    rman_surface(mat, diffuseColor=(0.5, 0.05, 0.04))
    curve.materials.append(mat)
    obj = bpy.data.objects.new("SoulString", curve)
    parent_coll.objects.link(obj)
    return obj


def add_lights(parent_coll):
    """RenderMan lights when RfB is loaded (Eevee also sees them as Blender lights)."""
    world = bpy.data.worlds.new("PreDawn")  # Eevee only; RenderMan uses the dome light
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.03, 0.045, 0.09, 1)
    bg.inputs["Strength"].default_value = 1.0
    bpy.context.scene.world = world
    rman = bpy.context.scene.render.engine == "PRMAN_RENDER"

    def light(name, rman_type, blender_type, location, color, energy, rman_params, size=None):
        if rman:
            from RenderManForBlender import rfb_api
            obj, shader = rfb_api.create_light(rman_type)
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            for k, v in rman_params.items():
                setattr(shader, k, v)
            if rman_type != "PxrDomeLight":  # the dome doubles as the sky backdrop
                obj.data.renderman.light_primary_visibility = False  # no glowing balls in frame
            setattr(shader, "lightColor", color)
        else:
            obj = bpy.data.objects.new(name, bpy.data.lights.new(name, blender_type))
        parent_coll.objects.link(obj)
        obj.name = obj.data.name = name
        obj.data.color, obj.data.energy = color, energy  # Eevee
        obj.location = location
        if size:
            obj.scale = (size, size, size)
        return obj

    # Pre-dawn sky: dim blue dome (also the background).
    light("SkyDome", "PxrDomeLight", "SUN", (0, 0, 0), (0.3, 0.45, 1.0), 0.0, {"intensity": 0.15})
    # Cold low moon/dawn light from the east: dimmer and bluer, so the warm lantern wins near her.
    dawn = light("DawnSky", "PxrDistantLight", "SUN", (0, 0, 10), (0.45, 0.6, 1.0), 0.4,
                 {"intensity": 0.35, "angleExtent": 10.0})
    dawn.rotation_euler = (math.radians(65), 0, math.radians(100))
    # Warm floor lantern in front of her (light inside the lantern model).
    light("LanternWarm", "PxrSphereLight", "POINT", LANTERN_POS + Vector((0, 0, 0.26)), (1.0, 0.55, 0.25), 60,
          {"intensity": 1.0, "exposure": 9.0}, size=0.07)
    # Faint warm glow from the paper lantern on the south-west post.
    light("PostLantern", "PxrSphereLight", "POINT", (-5.5, -5.5, 4.2), (1.0, 0.6, 0.3), 60,
          {"intensity": 1.0, "exposure": 5.0}, size=0.15)
    # The soul: a faint cool glow around the crane so the end of the trail reads.
    light("SoulGlow", "PxrSphereLight", "POINT", CRANE_POS + Vector((0.15, -0.1, 0.25)), (0.75, 0.85, 1.0), 15,
          {"intensity": 1.0, "exposure": 3.5}, size=0.05)


def add_lantern(parent_coll):
    """Placeholder floor lantern: a glowing paper cylinder around the LanternWarm light."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.11, depth=0.32,
                                        location=LANTERN_POS + Vector((0, 0, 0.16)))
    obj = bpy.context.object
    obj.name = "FloorLantern"
    for coll in list(obj.users_collection):
        coll.objects.unlink(obj)
    parent_coll.objects.link(obj)
    mat = bpy.data.materials.new("LanternPaper")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.9, 0.8, 0.6, 1)
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.6, 0.3, 1)
    bsdf.inputs["Emission Strength"].default_value = 3.0
    rman_surface(mat, diffuseColor=(0.9, 0.8, 0.6), enableGlow=True,
                 glowColor=(1.0, 0.6, 0.3), glowGain=2.0)
    obj.data.materials.append(mat)
    if hasattr(obj, "renderman"):
        obj.renderman.rman_visibilityTransmission = "0"  # let the light inside shine through


def add_camera(parent_coll, elevation, fit_points=None):
    """Orthographic camera; with fit_points, framed to contain them all."""
    cam = bpy.data.objects.new("DioramaCam", bpy.data.cameras.new("DioramaCam"))
    az, el = math.radians(CAMERA_AZIMUTH), math.radians(elevation)
    d = -Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), -math.sin(el)))  # toward camera
    cam.location = CAMERA_TARGET + d * 40
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = CAMERA_ORTHO_SCALE
    cam.data.clip_start, cam.data.clip_end = 1, 100
    if fit_points:
        rot = cam.rotation_euler.to_matrix()
        local = [rot.transposed() @ (p - cam.location) for p in fit_points]
        xs, ys = [p.x for p in local], [p.y for p in local]
        aspect = 16 / 9
        cam.data.ortho_scale = max(max(xs) - min(xs), (max(ys) - min(ys)) * aspect) * FRAME_MARGIN
        cam.location += rot @ Vector(((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, 0))
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
    out, force, framing, elevation = parse_args()
    if os.path.exists(out) and not force:
        raise SystemExit(f"{out} exists; bump the version number or pass --force")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)  # also unloads add-ons
    bpy.ops.wm.save_as_mainfile(filepath=out)  # save first so library paths are made relative
    if addon_utils.enable("RenderManForBlender", default_set=False):  # after the empty save: its save hook needs a world
        bpy.context.scene.render.engine = "PRMAN_RENDER"  # before adding RfB nodes and lights

    set_coll, char_coll = new_collection("Set"), new_collection("Character")
    props_coll, soul_coll = new_collection("Props"), new_collection("PaperSoul")
    light_coll, cam_coll = new_collection("Lights"), new_collection("Camera")

    wood_collector = link_collection(WOOD_COLLECTOR, WOOD_COLLECTOR_COLL)
    instance(wood_collector, "WoodCollector", set_coll)
    add_character(char_coll)
    for name, loc, rot, scale in PROPS:
        instance(link_collection(ONI_BLEND, name), name, props_coll, loc, rot, scale)
    add_paper_trail(soul_coll, link_collection(ONI_BLEND, "origami"))
    add_string(soul_coll)
    add_lights(light_coll)
    add_lantern(props_coll)
    fit = None
    if framing == "diorama":  # whole ground base, house and the crane at the end of the trail
        fit = [o.matrix_world @ Vector(c) for o in wood_collector.all_objects if o.type == "MESH"
               for c in o.bound_box] + [CRANE_POS]
    add_camera(cam_coll, elevation, fit)
    setup_render()

    bpy.ops.wm.save_as_mainfile(filepath=out)
    print(f"[layout] saved {os.path.relpath(out, REPO)} ({os.path.getsize(out) / 1e6:.1f} MB)")
    for lib in bpy.data.libraries:
        print(f"[layout] linked {lib.filepath}")


main()
