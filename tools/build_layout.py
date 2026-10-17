"""Build a first-draft layout .blend for the "Paper Soul" diorama.

Everything heavy is *linked* (not copied) from the RenderMan-ready copies in
assets/derived/, so the scene file stays small enough for git:
  - KitBash3D Wood Collector house (collection instance), WoodCollector_rman.blend
  - BigMediumSmall old woman reading (local object using the linked mesh), OldWoman_rman.blend
    (make both with tools/convert_to_rman.py; see README)
  - Oni props (collection instances), oni_assets.blend from tools/import_oni_assets.py
Placeholder story elements (paper trail) and lights/camera are
created locally. Positions are Wood Collector world coordinates (meters).

Usage (Blender 4.5, Intel build for RenderMan):
  Blender -b --factory-startup --addons RenderManForBlender \
      --python tools/build_layout.py -- scenes/paper_soul_v003.blend [--force] \
      [--framing diorama|closeup] [--elevation DEGREES] [--final] [--local]

  --local  append assets instead of linking: a self-contained scene for the cloud farm's packer
           (RANCHecker -> RenderMan scene_package), e.g. scenes/paper_soul_v003_render.blend
           (large, not in git); Blender preview images are dropped (RenderMan uses .tex)
  --final  full 3840x2160 (100%), production sampling, output to build/final/<scene>.0001.png;
           render with: Blender -b scenes/<scene>.blend --addons RenderManForBlender -f 1
           (on macOS this is RIS, not XPU: use the cloud farm for the submission render)
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
# With the fracturing newspaper (tools/fracture_newspaper.py); OldWoman_rman.blend is the intact one.
CHAR_BLEND = os.path.join(ASSETS, "derived", "OldWoman_fractured_rman.blend")
CHAR_NAME = "31_OldWoman_Sit6_Reading"
ONI_BLEND = os.path.join(ASSETS, "derived", "oni_assets.blend")

VERANDA_Z = 0.59  # floor height of the L-shaped veranda (south + west sides)

# Character: west veranda near the south-west corner, facing west (-X).
CHAR_POS = Vector((-5.1, -2.4, VERANDA_Z))
CHAR_ROT_Z = math.radians(-90)

# Oni props: (collection, location of bottom-center pivot, rotation XYZ degrees, scale)
# Spread along the west veranda (the lit "stage" facing the camera), slightly enlarged.
PROPS = [
    ("clock",              (-4.42, -2.6, 1.45),        (0, 0, -90), 1.3),  # west wall, behind her
    ("kakuremino",         (-4.75, 0.7, 1.15),         (0, 0, -90), 1.0),  # north of the doors, empty, above the basket
    ("setsubun_bagClosed", (-5.45, -1.75, VERANDA_Z),  (0, 0, 20),  3.0),  # by her feet, still tied shut
    # An abandoned meal on the lit corner of the veranda ("false clues" that reward looking):
    ("bentoKappa",         (-5.4, -3.1, VERANDA_Z),    (0, 0, 30),  1.3),  # cucumber bento
    ("bentoNaridon",       (-5.1, -3.3, VERANDA_Z),    (0, 0, -20), 0.3),  # rice ball in its bamboo-leaf wrap
    ("cutleryKnife",       (-5.68, -2.95, VERANDA_Z + 0.035), (90, 0, 40), 1.3),  # the cleaver, set down
]

# Paper trail: from the newspaper out from under the eave, then a wide S-curve rising in front
# of the dark thatched roof to the crane above the ridge (screen: right, far left, right, left).
TRAIL_POINTS = [Vector(p) for p in [(-5.75, -2.4, 1.75), (-7.6, -2.7, 2.5), (-7.4, 0.2, 4.0),
                                    (-5.6, -1.8, 5.8), (-3.4, 0.3, 8.4)]]
CRANE_POS = TRAIL_POINTS[-1]
TRAIL_COUNT = 44
TRAIL_SEED = 809  # Aug 9
# Exaggerated for readability at full-diorama framing (dream logic, not newspaper scale).
SCRAP_SIZE = (0.07, 0.26)  # at the newspaper (fracture-cell size) -> near the crane
TRAIL_SPREAD = 0.5
# Glow: warm (lantern-lit newspaper) near her, cool spirit-blue toward the crane.
GLOW_WARM, GLOW_COOL = (1.0, 0.75, 0.45), (0.7, 0.85, 1.0)
GLOW_GAIN = (0.35, 0.8)
GLOW_BINS = 6
# The scraps and crane are cut from her newspaper: same texture (from the converted character).
NEWSPAPER_IMAGE = os.path.join(ASSETS, "derived", "tex", "OldWoman_rman", "src", "Papers_color.jpg")
NEWSPAPER_TEX = os.path.join(ASSETS, "derived", "tex", "OldWoman_rman", "Papers_color.jpg.tex")
# Printed panels of the newspaper texture atlas, in UV space (u0, v0, u1, v1).
PRINT_REGIONS = [(0.53, 0.52, 0.87, 0.99), (0.15, 0.03, 0.49, 0.48), (0.51, 0.03, 0.87, 0.48)]
UV_PER_METER = 0.9  # newspaper print density: ~0.37 UV across the 0.42 m sheet
SCRAP_UV_MAX = 0.16

NEWSPAPER_MATERIAL = "M_Papers"

# Reading lantern hanging from the eave, above her and just in front (center of the lantern),
# high enough to clear her hat from the camera.
LANTERN_POS = Vector((-5.45, -2.6, 2.85))
LANTERN_CORD_TOP = 4.3  # just under the roof
LANTERN_RADIUS, LANTERN_HEIGHT = 0.12, 0.34  # same size as the earlier placeholder cylinder
LANTERN_RIBS = 7  # bamboo ribs showing as dark lines across the glowing paper
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
# RenderMan sampling (min samples, max samples, pixel variance).
PREVIEW_SAMPLING = (0, 128, 0.05)
FINAL_SAMPLING = (64, 512, 0.02)


LINK = True  # link assets (working scenes); False with --local (self-contained render package)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = next((a for a in argv if a.endswith(".blend")), "scenes/paper_soul_v003.blend")
    framing = argv[argv.index("--framing") + 1] if "--framing" in argv else "diorama"
    elevation = float(argv[argv.index("--elevation") + 1]) if "--elevation" in argv else CAMERA_ELEVATION
    global LINK
    LINK = "--local" not in argv
    return os.path.abspath(out), "--force" in argv, framing, elevation, "--final" in argv


def new_collection(name):
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def link_collection(blend, name):
    with bpy.data.libraries.load(blend, link=LINK, relative=True) as (src, dst):
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
    with bpy.data.libraries.load(CHAR_BLEND, link=LINK, relative=True) as (src, dst):
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


def newspaper_top_edge(char):
    """World-space center of the top edge of her newspaper, where the paper trail starts.
    (The fracture itself lives in the character asset: tools/fracture_newspaper.py.)"""
    mesh = char.data
    slot = next(i for i, m in enumerate(mesh.materials) if m and m.name.startswith(NEWSPAPER_MATERIAL))
    verts = [mesh.vertices[v].co for p in mesh.polygons if p.material_index == slot for v in p.vertices]
    top = max(v.z for v in verts)
    edge = [v for v in verts if v.z > top - 0.04]
    return char.matrix_world @ (sum(edge, Vector()) / len(edge))


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


def paper_material(name, glow_color, glow_gain):
    """Newspaper-printed thin paper that glows: glow = print x tint, so the print stays readable."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    image = nt.nodes.new("ShaderNodeTexImage")  # Eevee preview
    image.image = bpy.data.images.load(NEWSPAPER_IMAGE, check_existing=True)
    image.image.filepath = bpy.path.relpath(NEWSPAPER_IMAGE)  # relative to the scene file
    tint = nt.nodes.new("ShaderNodeMix")
    tint.data_type, tint.blend_type = "RGBA", "MULTIPLY"
    tint.inputs["Factor"].default_value = 1.0
    tint.inputs["B"].default_value = (*glow_color, 1)
    nt.links.new(image.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(image.outputs["Color"], tint.inputs["A"])
    nt.links.new(tint.outputs["Result"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Emission Strength"].default_value = glow_gain
    mat.use_backface_culling = False

    if bpy.context.scene.render.engine == "PRMAN_RENDER":
        from RenderManForBlender.rman_bl_nodes import __BL_NODES_MAP__ as nodes
        output = nt.nodes.new("RendermanOutputNode")
        surf = nt.nodes.new(nodes["PxrSurface"])
        tex = nt.nodes.new(nodes["PxrTexture"])
        tex["filename"] = "<blend_dir>/../" + os.path.relpath(NEWSPAPER_TEX, REPO)  # direct: no RfB callback
        tex.linearize = 1
        blend = nt.nodes.new(nodes["PxrBlend"])
        blend.operation = "18"  # Multiply
        blend.bottomRGB = glow_color
        surf.diffuseDoubleSided = 1
        surf.diffuseTransmitGain = 0.45  # thin paper, backlit glow
        surf.diffuseTransmitColor = (1.0, 0.85, 0.6)
        surf.enableGlow = True
        surf.glowGain = glow_gain
        nt.links.new(tex.outputs["resultRGB"], surf.inputs["diffuseColor"])
        nt.links.new(tex.outputs["resultRGB"], blend.inputs["topRGB"])
        nt.links.new(blend.outputs["resultRGB"], surf.inputs["glowColor"])
        nt.links.new(surf.outputs["bxdf_out"], output.inputs["bxdf_in"])
    return mat


def glow_materials():
    """GLOW_BINS paper materials from warm/dim (t=0, near her) to cool/bright (t=1, crane)."""
    mats = []
    for b in range(GLOW_BINS):
        t = b / (GLOW_BINS - 1)
        color = tuple(w + (c - w) * t for w, c in zip(GLOW_WARM, GLOW_COOL))
        gain = GLOW_GAIN[0] + (GLOW_GAIN[1] - GLOW_GAIN[0]) * t
        mats.append(paper_material(f"PaperSoul_{b}", color, gain))
    return mats


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
    # UVs: a random patch of one printed panel, so each scrap shows a different bit of the newspaper.
    u0, v0, u1, v1 = rng.choice(PRINT_REGIONS)
    uv_size = min(size * UV_PER_METER, SCRAP_UV_MAX)  # print at (roughly) true scale
    u, v = rng.uniform(u0, u1 - uv_size), rng.uniform(v0, v1 - uv_size)
    flat = [(0, 0), (1, 0), (1, 1), (0, 1)]  # corner order of the quad before folding
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        fu, fv = flat[loop.vertex_index]
        uv_layer.data[loop.index].uv = (u + fu * uv_size, v + fv * uv_size)
    return mesh


def catmull_rom(points, samples=400):
    """Dense samples of a Catmull-Rom spline through points, with cumulative arc length."""
    pts = [points[0]] + list(points) + [points[-1]]
    dense = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for k in range(samples // (len(points) - 1)):
            u = k / (samples // (len(points) - 1))
            dense.append(0.5 * (2 * p1 + (p2 - p0) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                                + (3 * p1 - p0 - 3 * p2 + p3) * u ** 3))
    dense.append(points[-1])
    lengths = [0.0]
    for a, b in zip(dense, dense[1:]):
        lengths.append(lengths[-1] + (b - a).length)
    return dense, lengths


def path_at(dense, lengths, t):
    """Point at fraction t of the arc length."""
    target = t * lengths[-1]
    i = next((k for k, L in enumerate(lengths) if L >= target), len(lengths) - 1)
    if i == 0:
        return dense[0]
    f = (target - lengths[i - 1]) / max(lengths[i] - lengths[i - 1], 1e-9)
    return dense[i - 1].lerp(dense[i], f)


def add_paper_trail(parent_coll, oni_crane, start=None):
    """Scraps along the trail from start (the newspaper's top edge) to the crane."""
    rng = random.Random(TRAIL_SEED)
    mats = glow_materials()
    dense, lengths = catmull_rom([start or TRAIL_POINTS[0]] + TRAIL_POINTS[1:])
    for i in range(TRAIL_COUNT):
        # Stratified jitter along the path: one scrap per stratum, so spacing is even but not regular.
        t = (i + rng.uniform(0.15, 0.85)) / TRAIL_COUNT * 0.95
        pos = path_at(dense, lengths, t)
        spread = TRAIL_SPREAD * math.sin(math.pi * t)  # loose in the middle, gathered at both ends
        pos += Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.5, 0.5))) * spread
        size = (SCRAP_SIZE[0] + (SCRAP_SIZE[1] - SCRAP_SIZE[0]) * t ** 0.6) * rng.uniform(0.8, 1.2)
        mesh = scrap_mesh(f"PaperScrap_{i:02d}", size, t, rng)
        mesh.materials.append(mats[min(int(t * GLOW_BINS), GLOW_BINS - 1)])
        obj = bpy.data.objects.new(mesh.name, mesh)
        obj.location = pos
        obj.rotation_euler = [rng.uniform(0, 2 * math.pi) for _ in range(3)]
        parent_coll.objects.link(obj)
    crane = instance(oni_crane, "Crane", parent_coll, CRANE_POS, (0, 0, -135), CRANE_SCALE)
    if hasattr(crane, "renderman"):  # the soul: override the linked crane's paper with a glowing one
        crane.renderman.rman_material_override = paper_material("SoulCrane", GLOW_COOL, 1.2)
    return crane


def add_lights(parent_coll):
    """RenderMan lights when RfB is loaded (Eevee also sees them as Blender lights)."""
    world = bpy.data.worlds.new("World")  # Eevee only (RenderMan uses the dome light); RANCHecker expects this name
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
    # Warm reading lantern hanging in front of and above her (light inside the lantern model).
    light("LanternWarm", "PxrSphereLight", "POINT", LANTERN_POS, (1.0, 0.55, 0.25), 60,
          {"intensity": 1.0, "exposure": 9.0}, size=0.07)
    # Faint warm glow from the paper lantern on the south-west post.
    light("PostLantern", "PxrSphereLight", "POINT", (-5.5, -5.5, 4.2), (1.0, 0.6, 0.3), 60,
          {"intensity": 1.0, "exposure": 5.0}, size=0.15)
    # The soul: a faint cool glow around the crane so the end of the trail reads.
    light("SoulGlow", "PxrSphereLight", "POINT", CRANE_POS + Vector((0.15, -0.1, 0.25)), (0.75, 0.85, 1.0), 15,
          {"intensity": 1.0, "exposure": 3.5}, size=0.05)


def lantern_meshes():
    """Chochin paper lantern around the origin: a barrel-shaped paper body, wooden rims, bamboo ribs."""
    radius, height, sides = LANTERN_RADIUS, LANTERN_HEIGHT, 32

    def ring(r, z):
        return [(r * math.cos(2 * math.pi * k / sides), r * math.sin(2 * math.pi * k / sides), z)
                for k in range(sides)]

    def lathe(name, profile, cap_top=False, cap_bottom=False):
        """Surface of revolution through (r, z) profile points (bottom to top)."""
        verts, faces = [], []
        for r, z in profile:
            verts += ring(r, z)
        for i in range(len(profile) - 1):
            for k in range(sides):
                a, b = i * sides + k, i * sides + (k + 1) % sides
                faces.append((a, b, b + sides, a + sides))
        if cap_bottom:
            faces.append(tuple(reversed(range(sides))))
        if cap_top:
            faces.append(tuple(range((len(profile) - 1) * sides, len(profile) * sides)))
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        return mesh

    # Paper body: barrel profile, narrower at the rims.
    rows = 14
    body = [(radius * (0.80 + 0.20 * math.sin(math.pi * i / rows)), -height / 2 + height * i / rows)
            for i in range(rows + 1)]
    paper = lathe("LanternPaper", body)
    # Wooden rims: short closed rings at the top and bottom.
    rim_r, rim_h = radius * 0.86, 0.022
    rims = []
    for name, z in (("LanternRimTop", height / 2), ("LanternRimBottom", -height / 2)):
        rims.append(lathe(name, [(rim_r, z - rim_h / 2), (rim_r, z + rim_h / 2)], cap_top=True, cap_bottom=True))
    # Bamboo ribs: thin rings just outside the paper, following the barrel.
    ribs = []
    for i in range(1, LANTERN_RIBS + 1):
        t = i / (LANTERN_RIBS + 1)
        r = radius * (0.80 + 0.20 * math.sin(math.pi * t)) + 0.002
        z = -height / 2 + height * t
        w = 0.004
        ribs.append(lathe(f"LanternRib{i}", [(r, z - w / 2), (r + 0.003, z), (r, z + w / 2)]))
    return paper, rims, ribs


def add_lantern(parent_coll):
    """Hanging paper lantern (chochin) around the LanternWarm light, on a cord from the eave."""
    paper_mesh, rim_meshes, rib_meshes = lantern_meshes()

    paper = bpy.data.materials.new("LanternPaper")
    paper.use_nodes = True
    bsdf = paper.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.9, 0.8, 0.6, 1)
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.6, 0.3, 1)
    bsdf.inputs["Emission Strength"].default_value = 3.0
    paper.use_backface_culling = False
    rman_surface(paper, diffuseColor=(0.9, 0.8, 0.6), diffuseDoubleSided=1, enableGlow=True,
                 glowColor=(1.0, 0.6, 0.3), glowGain=2.0)
    wood = bpy.data.materials.new("LanternWood")
    wood.use_nodes = True
    wood.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.10, 0.06, 0.035, 1)
    wood.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.6
    rman_surface(wood, diffuseColor=(0.10, 0.06, 0.035))

    for mesh, mat in [(paper_mesh, paper)] + [(m, wood) for m in rim_meshes + rib_meshes]:
        mesh.materials.append(mat)
        obj = bpy.data.objects.new(mesh.name, mesh)
        obj.location = LANTERN_POS
        parent_coll.objects.link(obj)
        if hasattr(obj, "renderman"):
            # Let the light inside shine out (no shadows from the paper, rims or ribs).
            obj.renderman.rman_visibilityTransmission = "0"

    cord = bpy.data.curves.new("LanternCord", "CURVE")
    cord.dimensions, cord.bevel_depth = "3D", 0.004
    spline = cord.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (*(LANTERN_POS + Vector((0, 0, LANTERN_HEIGHT / 2))), 1)
    spline.points[1].co = (LANTERN_POS.x, LANTERN_POS.y, LANTERN_CORD_TOP, 1)
    cord_obj = bpy.data.objects.new("LanternCord", cord)
    cord_obj.data.materials.append(wood)
    parent_coll.objects.link(cord_obj)


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


def setup_render(final):
    """Preview settings by default; with final, the full-resolution production frame."""
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = 3840, 2160  # challenge max, 16:9
    scene.render.resolution_percentage = 100 if final else 25
    scene.frame_start = scene.frame_end = scene.frame_current = 1  # a still, not Blender's 250 frames
    scene.render.filepath = "//../build/final/"  # Blender's own output (RfB uses the paths below)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_depth = "16"
    if hasattr(scene, "renderman"):
        scene.render.engine = "PRMAN_RENDER"
        scene.renderman.renderVariant = "xpu"  # falls back to RIS on macOS; XPU on the cloud farm
        rm = scene.renderman
        # RfB writes its own output, by default under /tmp: keep it in the repo's (ignored) build/.
        rm.root_path_output = "<blend_dir>/../build/renderman/<blend>"
        rm.path_beauty_image_output = "<blend_dir>/../build/final/<blend>.<F4>.<ext>"
        if final:
            rm.hider_minSamples, rm.hider_maxSamples, rm.ri_pixelVariance = FINAL_SAMPLING
        else:
            rm.hider_minSamples, rm.hider_maxSamples, rm.ri_pixelVariance = PREVIEW_SAMPLING
    else:
        print("[layout] RenderMan add-on not loaded; leaving default engine")


def detach_rfb_handlers():
    """RfB's link/scene-update/save handlers scan textures and expand <blend_dir> against each
    linked file's folder, creating stray directories (e.g. assets/assets/derived/...)."""
    for handlers in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.save_pre,
                     bpy.app.handlers.save_post, bpy.app.handlers.load_post):
        for handler in list(handlers):
            if getattr(handler, "__module__", "").startswith("RenderManForBlender"):
                handlers.remove(handler)


def main():
    out, force, framing, elevation, final = parse_args()
    if os.path.exists(out) and not force:
        raise SystemExit(f"{out} exists; bump the version number or pass --force")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)  # also unloads add-ons
    bpy.context.preferences.filepaths.save_version = 0  # no .blend1 backups (the script is the source)
    bpy.ops.wm.save_as_mainfile(filepath=out)  # save first so library paths are made relative
    if addon_utils.enable("RenderManForBlender", default_set=False):  # after the empty save: its save hook needs a world
        bpy.context.scene.render.engine = "PRMAN_RENDER"  # before adding RfB nodes and lights
        detach_rfb_handlers()

    set_coll, char_coll = new_collection("Set"), new_collection("Character")
    props_coll, soul_coll = new_collection("Props"), new_collection("PaperSoul")
    light_coll, cam_coll = new_collection("Lights"), new_collection("Camera")

    wood_collector = link_collection(WOOD_COLLECTOR, WOOD_COLLECTOR_COLL)
    instance(wood_collector, "WoodCollector", set_coll)
    newspaper_top = newspaper_top_edge(add_character(char_coll))
    for name, loc, rot, scale in PROPS:
        instance(link_collection(ONI_BLEND, name), name, props_coll, loc, rot, scale)
    add_paper_trail(soul_coll, link_collection(ONI_BLEND, "origami"), newspaper_top)
    add_lights(light_coll)
    add_lantern(props_coll)
    fit = None
    if framing == "diorama":  # whole ground base, house and the crane at the end of the trail
        fit = [o.matrix_world @ Vector(c) for o in wood_collector.all_objects if o.type == "MESH"
               for c in o.bound_box] + [CRANE_POS]
    add_camera(cam_coll, elevation, fit)
    setup_render(final)

    if not LINK:
        # Render package: RenderMan reads .tex files, so drop Blender's preview images (Eevee only),
        # including the character's packed textures and the KitBash ones in ~/.kitbash3d.
        for image in list(bpy.data.images):
            bpy.data.images.remove(image)
        # Absolute RenderMan paths: RfB's packer resolves <blend_dir> against each material's
        # original file; it copies the files and rewrites the paths into the package anyway.
        scenes_dir = os.path.dirname(out)
        for mat in bpy.data.materials:
            for node in mat.node_tree.nodes if mat.node_tree else []:
                for attr in ("filename", "shadercode"):
                    value = getattr(node, attr, None)
                    if isinstance(value, str) and value.startswith("<blend_dir>/"):
                        node[attr] = os.path.normpath(os.path.join(scenes_dir, value[len("<blend_dir>/"):]))
        if hasattr(bpy.context.scene, "rman_txmgr_list"):
            bpy.context.scene.rman_txmgr_list.clear()  # stale texture registrations from the build
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print(f"[layout] saved {os.path.relpath(out, REPO)} ({os.path.getsize(out) / 1e6:.1f} MB)")
    for lib in bpy.data.libraries:
        print(f"[layout] linked {lib.filepath}")


main()
