from __future__ import annotations

import math
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
ART_DIR = ROOT / "art" / "blender" / "2d-upgrade"
RENDER_DIR = ART_DIR / "renders"
ASSET_DIR = ROOT / "art" / "source-assets" / "kenney-rpg-pack" / "extracted" / "PNG"
CHARACTER_DIR = ROOT / "art" / "source-assets" / "kenney-character-pack" / "extracted" / "PNG"

ART_DIR.mkdir(parents=True, exist_ok=True)
RENDER_DIR.mkdir(parents=True, exist_ok=True)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)
    for image in list(bpy.data.images):
        if image.users == 0:
            bpy.data.images.remove(image)


def collection(name: str) -> bpy.types.Collection:
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def link_to(obj: bpy.types.Object, coll: bpy.types.Collection) -> bpy.types.Object:
    for source in list(obj.users_collection):
        source.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def material_from_png(tile: int) -> bpy.types.Material:
    name = f"kenney_rpgTile{tile:03d}"
    existing = bpy.data.materials.get(name)
    if existing:
        return existing

    image_path = ASSET_DIR / f"rpgTile{tile:03d}.png"
    image = bpy.data.images.load(str(image_path))
    image.alpha_mode = "STRAIGHT"
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    mat.show_transparent_back = True
    nodes = mat.node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new(type="ShaderNodeOutputMaterial")
    emission = nodes.new(type="ShaderNodeEmission")
    transparent = nodes.new(type="ShaderNodeBsdfTransparent")
    mixer = nodes.new(type="ShaderNodeMixShader")
    tex = nodes.new(type="ShaderNodeTexImage")
    tex.image = image
    mat.node_tree.links.new(tex.outputs["Color"], emission.inputs["Color"])
    mat.node_tree.links.new(tex.outputs["Alpha"], mixer.inputs["Fac"])
    mat.node_tree.links.new(transparent.outputs["BSDF"], mixer.inputs[1])
    mat.node_tree.links.new(emission.outputs["Emission"], mixer.inputs[2])
    mat.node_tree.links.new(mixer.outputs["Shader"], output.inputs["Surface"])
    return mat


def material_from_image(path: Path, name_prefix: str = "image") -> bpy.types.Material:
    safe_name = f"{name_prefix}_{path.stem}".replace(" ", "_")
    existing = bpy.data.materials.get(safe_name)
    if existing:
        return existing
    image = bpy.data.images.load(str(path))
    image.alpha_mode = "STRAIGHT"
    material = bpy.data.materials.new(safe_name)
    material.use_nodes = True
    material.blend_method = "BLEND"
    material.show_transparent_back = True
    nodes = material.node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new(type="ShaderNodeOutputMaterial")
    emission = nodes.new(type="ShaderNodeEmission")
    transparent = nodes.new(type="ShaderNodeBsdfTransparent")
    mixer = nodes.new(type="ShaderNodeMixShader")
    tex = nodes.new(type="ShaderNodeTexImage")
    tex.image = image
    material.node_tree.links.new(tex.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(tex.outputs["Alpha"], mixer.inputs["Fac"])
    material.node_tree.links.new(transparent.outputs["BSDF"], mixer.inputs[1])
    material.node_tree.links.new(emission.outputs["Emission"], mixer.inputs[2])
    material.node_tree.links.new(mixer.outputs["Shader"], output.inputs["Surface"])
    return material


def flat_material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    output = nodes.new(type="ShaderNodeOutputMaterial")
    emission = nodes.new(type="ShaderNodeEmission")
    transparent = nodes.new(type="ShaderNodeBsdfTransparent")
    mixer = nodes.new(type="ShaderNodeMixShader")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = 1.0
    mixer.inputs["Fac"].default_value = color[3]
    mat.node_tree.links.new(transparent.outputs["BSDF"], mixer.inputs[1])
    mat.node_tree.links.new(emission.outputs["Emission"], mixer.inputs[2])
    mat.node_tree.links.new(mixer.outputs["Shader"], output.inputs["Surface"])
    if color[3] < 1:
        mat.blend_method = "BLEND"
    return mat


def plane(name: str, x: float, y: float, w: float, h: float, z: float, mat: bpy.types.Material, coll: bpy.types.Collection) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [
            (-w / 2, -h / 2, 0),
            (w / 2, -h / 2, 0),
            (w / 2, h / 2, 0),
            (-w / 2, h / 2, 0),
        ],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for loop, uv in zip(uv_layer.data, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop.uv = uv
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (x, y, z)
    obj.data.materials.append(mat)
    return link_to(obj, coll)


def tile(tile_id: int, x: float, y: float, z: float, coll: bpy.types.Collection, scale: float = 1.0, name: str | None = None) -> bpy.types.Object:
    return plane(name or f"tile_{tile_id:03d}_{x:.1f}_{y:.1f}", x, y, scale, scale, z, material_from_png(tile_id), coll)


def label(text: str, x: float, y: float, z: float, coll: bpy.types.Collection, size: float = 0.18) -> None:
    if any(marker in text for marker in ["€", "濮", "鏈", "鎴", "璁", "浜", "姘", "鍖", "鐮", "婀"]):
        return
    bpy.ops.object.text_add(location=(x, y, z), rotation=(0, 0, 0))
    obj = bpy.context.object
    obj.name = f"label_{text}"
    obj.data.body = text
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.data.materials.append(flat_material("label ink", (0.13, 0.22, 0.18, 1)))
    link_to(obj, coll)


def area_wash(name: str, x: float, y: float, w: float, h: float, color: tuple[float, float, float, float], coll: bpy.types.Collection) -> None:
    plane(name, x, y, w, h, 0.055, flat_material(f"{name}_wash", color), coll)


def ellipse(name: str, x: float, y: float, w: float, h: float, z: float, color: tuple[float, float, float, float], coll: bpy.types.Collection, segments: int = 48, angle: float = 0.0) -> bpy.types.Object:
    verts = [(0, 0, 0)]
    for index in range(segments):
        theta = math.tau * index / segments
        verts.append((math.cos(theta) * w / 2, math.sin(theta) * h / 2, 0))
    faces = []
    for index in range(1, segments + 1):
        faces.append((0, index, 1 if index == segments else index + 1))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (x, y, z)
    obj.rotation_euler[2] = math.radians(angle)
    obj.data.materials.append(flat_material(f"{name}_mat", color))
    return link_to(obj, coll)


def organic_blob(name: str, x: float, y: float, w: float, h: float, z: float, color: tuple[float, float, float, float], coll: bpy.types.Collection, points: int = 18, angle: float = 0.0, wobble: float = 0.18) -> bpy.types.Object:
    verts = [(0, 0, 0)]
    for index in range(points):
        theta = math.tau * index / points
        pulse = 1 + math.sin(index * 1.7) * wobble + math.cos(index * 2.3) * wobble * 0.55
        verts.append((math.cos(theta) * w * 0.5 * pulse, math.sin(theta) * h * 0.5 * pulse, 0))
    faces = [(0, index, 1 if index == points else index + 1) for index in range(1, points + 1)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = (x, y, z)
    obj.rotation_euler[2] = math.radians(angle)
    obj.data.materials.append(flat_material(f"{name}_mat", color))
    return link_to(obj, coll)


def build_ground(coll: bpy.types.Collection) -> None:
    for gx in range(-13, 14):
        for gy in range(-8, 8):
            base = 3 if (gx + gy) % 4 else 4
            tile(base, gx, gy, 0.0, coll)

    plaza_tiles = [(-3, 1), (-2, 1), (-1, 1), (0, 1), (1, 1), (2, 1), (-3, 0), (-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0), (-2, -1), (-1, -1), (0, -1), (1, -1)]
    for gx, gy in plaza_tiles:
        tile(8 if (gx + gy) % 2 else 9, gx, gy, 0.07, coll)

    road_tiles = [
        (-11, 0), (-10, 0), (-9, 0), (-8, 0), (-7, 0), (-6, 0), (-5, 0), (-4, 0),
        (3, 0), (4, 0), (5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (10, 0), (11, 0),
        (-8, -1), (-8, -2), (-8, -3), (-8, -4), (-8, -5),
        (7, -1), (7, -2), (7, -3), (7, -4), (7, -5),
        (0, -2), (0, -3), (0, -4), (0, -5),
        (-2, 2), (-2, 3), (-2, 4), (2, 2), (2, 3), (2, 4),
        (-5, 3), (-6, 4), (-7, 5), (5, 3), (6, 4), (7, 5),
        (-10, 1), (-9, 2), (-8, 3), (-7, 4),
        (10, 1), (9, 2), (8, 3), (7, 4),
        (-4, -1), (-5, -2), (-6, -3), (4, -1), (5, -2), (6, -3),
    ]
    for gx, gy in road_tiles:
        tile(8 if (gx + gy) % 2 else 9, gx, gy, 0.06, coll)

    for gx, gy in [(-10, -1.5), (-9, -1.5), (-8, -1.5), (-7, -1.5), (-6, -1.5), (-5, -1.5), (5, -1.5), (6, -1.5), (7, -1.5), (8, -1.5), (9, -1.5)]:
        tile(29, gx, gy, 0.08, coll)

    for gx in range(-8, -4):
        tile(24, gx, -2.5, 0.07, coll)
        tile(24, gx, -3.5, 0.07, coll)
    for gx in range(5, 8):
        tile(24, gx, 0.5, 0.07, coll)

    for name, x, y, w, h, color in [
        ("north_soft_meadow", -9.4, 3.75, 5.2, 2.2, (0.58, 0.9, 0.24, 0.22)),
        ("north_east_soft_meadow", 8.6, 3.55, 5.4, 2.1, (0.48, 0.86, 0.32, 0.2)),
        ("south_central_soft_meadow", -1.5, -4.1, 6.2, 2.4, (0.49, 0.84, 0.27, 0.22)),
        ("market_warm_square", 9.15, 0.6, 4.2, 2.4, (0.98, 0.76, 0.25, 0.16)),
        ("workshop_cool_square", 1.7, 1.0, 4.0, 2.35, (0.5, 0.66, 0.74, 0.14)),
        ("plaza_soft_shadow", -0.5, 0.0, 4.0, 2.25, (0.77, 0.53, 0.25, 0.16)),
    ]:
        ellipse(name, x, y, w, h, 0.065, color, coll)


def build_water(coll: bpy.types.Collection) -> None:
    pond = [(-10, -2), (-9, -2), (-8, -2), (-7, -2), (-6, -2), (-10, -3), (-9, -3), (-8, -3), (-7, -3), (-6, -3), (-10, -4), (-9, -4), (-8, -4), (6, -2), (7, -2), (8, -2), (9, -2), (10, -2), (6, -3), (7, -3), (8, -3), (9, -3), (10, -3), (8, -4), (9, -4), (10, -4)]
    for gx, gy in pond:
        tile(29, gx, gy, 0.12, coll)
    for gx, gy in [(-11, -2), (-5, -2), (-11, -3), (-5, -3), (-11, -4), (-7, -4), (5, -2), (11, -2), (5, -3), (11, -3), (7, -4), (11, -4)]:
        tile(28, gx, gy, 0.13, coll)
    for gx, gy in [(-10, -2), (-8, -3), (-6, -2), (7, -2), (9, -3), (10, -2)]:
        tile(33, gx, gy, 0.18, coll, 0.7)
    for gx, gy, tile_id in [
        (-11, -1, 10), (-10, -1, 11), (-9, -1, 11), (-8, -1, 11), (-7, -1, 12), (-5, -2, 30),
        (-11, -5, 44), (-10, -5, 45), (-9, -5, 45), (-8, -5, 46),
        (5, -1, 10), (6, -1, 11), (7, -1, 11), (8, -1, 11), (9, -1, 11), (10, -1, 12),
        (6, -5, 44), (7, -5, 45), (8, -5, 45), (9, -5, 45), (10, -5, 46),
    ]:
        tile(tile_id, gx, gy, 0.21, coll)


def build_buildings(coll: bpy.types.Collection) -> None:
    # Houses and structures are assembled from Kenney wall, roof and door tiles.
    structures = [
        ("需求信箱", -9.2, 0.9, 48, 107),
        ("委托公告板", -3.1, 1.55, 144, 105),
        ("机械工坊", 1.0, 1.25, 56, 114),
        ("成果温室", 4.3, 0.85, 56, 116),
        ("订单集市", 9.0, 1.1, 47, 105),
        ("Blender 场景棚", 0.0, -2.55, 48, 107),
        ("北山小屋", -7.1, 4.45, 48, 107),
        ("研究塔", 7.3, 4.45, 56, 114),
        ("湖边仓库", -9.5, -4.65, 47, 105),
        ("码头驿站", 9.2, -4.55, 48, 107),
    ]
    structures = [
        ("需求信箱", -9.2, 0.9, 48, 107),
        ("委托公告板", -3.1, 1.55, 144, 105),
        ("机械工坊", 1.0, 1.25, 56, 114),
        ("成果温室", 4.3, 0.85, 56, 116),
        ("订单集市", 9.0, 1.1, 47, 105),
        ("Blender 场景棚", 0.0, -2.55, 48, 107),
        ("北山小屋", -7.1, 4.45, 48, 107),
        ("研究塔", 7.3, 4.45, 56, 114),
        ("湖边仓库", -9.5, -4.65, 47, 105),
        ("码头驿站", 9.2, -4.55, 48, 107),
    ]
    structures = [
        ("需求信箱", -9.2, 0.9, 48, 107),
        ("委托公告板", -3.1, 1.55, 144, 105),
        ("机械工坊", 1.0, 1.25, 56, 114),
        ("成果温室", 4.3, 0.85, 56, 116),
        ("订单集市", 9.0, 1.1, 47, 105),
        ("Blender 场景棚", 0.0, -2.55, 48, 107),
        ("北山小屋", -7.1, 4.45, 48, 107),
        ("研究塔", 7.3, 4.45, 56, 114),
        ("湖边仓库", -9.5, -4.65, 47, 105),
        ("码头驿站", 9.2, -4.55, 48, 107),
    ]
    structures = [
        ("需求信箱", -9.2, 0.9, 48, 107),
        ("委托公告板", -3.1, 1.55, 144, 105),
        ("机械工坊", 1.0, 1.25, 56, 114),
        ("成果温室", 4.3, 0.85, 56, 116),
        ("订单集市", 9.0, 1.1, 47, 105),
        ("Blender 场景棚", 0.0, -2.55, 48, 107),
        ("北山小屋", -7.1, 4.45, 48, 107),
        ("研究塔", 7.3, 4.45, 56, 114),
        ("湖边仓库", -9.5, -4.65, 47, 105),
        ("码头驿站", 9.2, -4.55, 48, 107),
    ]
    for name, x, y, wall, roof in structures:
        tile(wall, x, y, 0.35, coll, 1.18, f"{name}_wall")
        tile(roof, x, y + 0.55, 0.48, coll, 1.18, f"{name}_roof")
        tile(165, x, y - 0.35, 0.52, coll, 0.52, f"{name}_door")
        label(name, x, y - 0.8, 0.62, coll)

    tile(161, -9.65, 0.8, 0.62, coll, 0.7, "mailbox_sign")
    tile(163, -2.65, 1.2, 0.64, coll, 0.72, "quest_crate_a")
    tile(164, -3.45, 1.05, 0.64, coll, 0.72, "quest_crate_b")
    tile(174, -0.2, 0.75, 0.66, coll, 0.85, "workshop_gate")
    tile(161, 8.2, -3.4, 0.62, coll, 1.0, "dock_bridge")
    tile(33, -0.5, -0.55, 0.74, coll, 0.78, "central_plaza_shadow")
    tile(155, -0.5, -0.15, 0.78, coll, 0.62, "central_plaza_tree")
    tile(33, -0.5, 0.15, 0.73, coll, 1.1, "central_plaza_ring_a")
    tile(34, -1.0, 0.15, 0.74, coll, 0.75, "central_plaza_bench_left")
    tile(34, 0.0, 0.15, 0.74, coll, 0.75, "central_plaza_bench_right")
    tile(174, -0.5, 0.45, 0.82, coll, 0.85, "central_plaza_portal_top")
    tile(163, -1.25, -0.45, 0.82, coll, 0.55, "central_notice_crate_left")
    tile(164, 0.25, -0.45, 0.82, coll, 0.55, "central_notice_crate_right")


def build_details(coll: bpy.types.Collection) -> None:
    for name, x, y, w, h, color in [
        ("west_lake_foam_a", -9.3, -1.7, 4.6, 0.28, (0.92, 1.0, 0.96, 0.34)),
        ("west_lake_foam_b", -7.2, -5.15, 3.7, 0.24, (0.92, 1.0, 0.96, 0.28)),
        ("east_lake_foam_a", 8.6, -1.68, 5.5, 0.28, (0.92, 1.0, 0.96, 0.34)),
        ("east_lake_foam_b", 9.0, -5.08, 4.5, 0.24, (0.92, 1.0, 0.96, 0.28)),
        ("farm_playable_glow", -9.9, -2.85, 5.1, 2.8, (0.94, 0.82, 0.32, 0.12)),
        ("quest_camp_glow", -3.15, 1.42, 3.2, 2.1, (1.0, 0.72, 0.34, 0.12)),
        ("dock_playable_glow", 8.8, -4.05, 4.7, 1.8, (0.2, 0.72, 0.94, 0.12)),
    ]:
        ellipse(name, x, y, w, h, 0.56, color, coll)

    for name, x, y, w, h, color in [
        ("farm_play_area", -9.9, -2.9, 5.5, 3.2, (0.93, 0.78, 0.35, 0.18)),
        ("workshop_play_area", 1.3, 1.0, 4.4, 3.4, (0.58, 0.67, 0.72, 0.16)),
        ("greenhouse_play_area", 4.7, 0.5, 3.8, 3.0, (0.52, 0.92, 0.72, 0.18)),
        ("market_play_area", 9.0, 0.5, 4.8, 3.6, (1.0, 0.83, 0.32, 0.18)),
        ("dock_play_area", 8.8, -4.0, 5.8, 2.6, (0.34, 0.78, 0.96, 0.16)),
        ("quest_play_area", -3.2, 1.25, 3.6, 2.8, (0.96, 0.68, 0.35, 0.16)),
    ]:
        area_wash(name, x, y, w, h, color, coll)

    for x, y, scale, tile_id in [
        (-11.6, 2.6, 0.8, 155),
        (-10.8, -4.8, 0.55, 156),
        (-7.3, 2.5, 0.8, 157),
        (-4.6, -5.8, 0.7, 159),
        (-5.6, 4.1, 0.7, 175),
        (-2.8, -3.6, 0.55, 176),
        (3.8, 3.0, 0.7, 176),
        (6.4, -4.0, 0.8, 155),
        (9.5, -4.6, 0.8, 179),
        (10.6, 2.6, 0.7, 175),
        (2.6, -5.8, 0.7, 159),
        (12.0, 4.7, 0.72, 157),
        (-12.4, 5.0, 0.62, 175),
        (-10.2, 4.2, 0.52, 176),
        (9.6, 4.1, 0.5, 179),
        (11.8, -1.1, 0.54, 156),
        (-1.8, 4.8, 0.46, 155),
        (1.8, 4.8, 0.46, 159),
    ]:
        tile(tile_id, x, y, 0.72, coll, scale)

    for x in [-12, -11, -10, -9, -8, -7]:
        tile(161, x, -1.25, 0.7, coll, 0.7, "farm_fence")
    for x in [-11.5, -10.5, -9.5, -8.5, -7.5]:
        tile(158, x, -1.75, 0.73, coll, 0.65, "crop_detail")
    for gx in [-12, -11, -10, -9, -8]:
        for gy in [-2, -3]:
            tile(24, gx, gy, 0.69, coll, 0.86, "task_field_soil")
            tile(158 if (gx + gy) % 2 else 160, gx, gy, 0.78, coll, 0.56, "task_field_crop")
    for x in [-12.5, -7.4]:
        tile(162, x, -2.5, 0.8, coll, 0.85, "task_field_side_fence")
    for x in [8, 9, 10, 11]:
        tile(162, x, -4.45, 0.7, coll, 0.7, "dock_fence")
    for x, y in [(-6, 3.2), (-5.2, 3.4), (5.6, 3.2), (6.4, 3.45), (10.6, 0.1), (-11.2, 0.1)]:
        tile(163, x, y, 0.76, coll, 0.55, "small_crate")
    for x, y, w, h, color in [
        (-11.35, -2.8, 0.22, 1.6, (0.45, 0.3, 0.13, 0.36)),
        (-10.05, -2.8, 0.22, 1.6, (0.45, 0.3, 0.13, 0.3)),
        (-8.75, -2.8, 0.22, 1.6, (0.45, 0.3, 0.13, 0.3)),
        (-7.45, -2.8, 0.22, 1.6, (0.45, 0.3, 0.13, 0.3)),
        (8.1, 2.03, 0.55, 0.18, (0.94, 0.2, 0.18, 0.78)),
        (9.0, 2.03, 0.55, 0.18, (0.2, 0.58, 0.95, 0.78)),
        (9.9, 2.03, 0.55, 0.18, (0.94, 0.72, 0.18, 0.78)),
        (0.5, 2.24, 2.8, 0.16, (0.2, 0.38, 0.46, 0.45)),
        (4.4, 1.55, 1.7, 0.14, (0.82, 1.0, 0.92, 0.52)),
    ]:
        plane("painted_detail_stroke", x, y, w, h, 0.92, flat_material("painted_detail_stroke", color), coll)
    for x, y, tile_id, scale in [
        (-10.9, -3.95, 158, 0.5), (-9.8, -3.95, 160, 0.5), (-8.7, -3.95, 158, 0.5), (-7.6, -3.95, 160, 0.5),
        (-10.8, -0.55, 175, 0.48), (-9.9, -0.45, 176, 0.48), (-7.0, -0.55, 155, 0.48),
        (-3.7, 2.55, 163, 0.55), (-2.9, 2.55, 164, 0.55), (-2.1, 2.55, 163, 0.55),
        (0.0, 2.55, 163, 0.55), (0.8, 2.65, 164, 0.55), (1.6, 2.55, 163, 0.55),
        (2.1, 0.05, 161, 0.62), (2.75, 0.05, 161, 0.62), (-0.5, 0.05, 162, 0.62),
        (3.6, 1.9, 155, 0.5), (4.6, 1.95, 159, 0.5), (5.4, 1.85, 155, 0.5),
        (8.1, 2.45, 163, 0.62), (9.0, 2.6, 164, 0.62), (9.9, 2.45, 163, 0.62),
        (7.9, -0.15, 175, 0.5), (10.2, -0.1, 176, 0.5), (11.2, 0.6, 155, 0.5),
        (7.2, -4.85, 163, 0.54), (8.2, -4.85, 164, 0.54), (9.2, -4.85, 163, 0.54), (10.2, -4.85, 164, 0.54),
        (-11.0, 4.7, 155, 0.52), (-9.7, 4.8, 159, 0.46), (9.9, 4.75, 155, 0.48), (11.0, 4.55, 159, 0.46),
    ]:
        tile(tile_id, x, y, 0.86, coll, scale, "area_identity_detail")

    glass = flat_material("greenhouse_glass_overlay", (0.54, 0.95, 0.88, 0.24))
    for x in [3.65, 4.35, 5.05]:
        plane("greenhouse_glass_strip", x, 0.95, 0.28, 1.05, 0.9, glass, coll)

    banner_mat = flat_material("warm_market_banner", (1.0, 0.42, 0.28, 0.88))
    for x in [8.05, 9.0, 9.95]:
        plane("market_banner", x, 1.95, 0.5, 0.18, 0.91, banner_mat, coll)

    path_mark_mat = flat_material("soft_path_marker", (1.0, 0.94, 0.58, 0.26))
    for x, y in [(-6.5, 3.5), (-5.5, 2.8), (-4.3, 2.1), (4.3, 2.1), (5.5, 2.8), (6.5, 3.5), (-5.4, -2.5), (5.4, -2.5)]:
        plane("soft_path_marker_dot", x, y, 0.42, 0.42, 0.58, path_mark_mat, coll)


def tiny_actor(coll: bpy.types.Collection, name: str, x: float, y: float, shirt: tuple[float, float, float, float], pose: float = 0.0) -> None:
    ellipse(f"{name}_shadow", x, y - 0.13, 0.32, 0.11, 0.96, (0, 0, 0, 0.18), coll, 24)
    ellipse(f"{name}_body", x, y, 0.23, 0.31, 1.02, shirt, coll, 28)
    ellipse(f"{name}_head", x, y + 0.2, 0.18, 0.18, 1.04, (1.0, 0.78, 0.56, 1), coll, 24)
    ellipse(f"{name}_hair", x, y + 0.26, 0.21, 0.12, 1.05, (0.36, 0.2, 0.12, 1), coll, 24)
    plane(f"{name}_arm_left", x - 0.16, y + pose * 0.7, 0.08, 0.22, 1.03, flat_material(f"{name}_shirt", shirt), coll).rotation_euler[2] = math.radians(12 + pose * 90)
    plane(f"{name}_arm_right", x + 0.16, y - pose * 0.7, 0.08, 0.22, 1.03, flat_material(f"{name}_shirt_r", shirt), coll).rotation_euler[2] = math.radians(-12 - pose * 90)
    plane(f"{name}_leg_left", x - 0.06 - pose * 0.14, y - 0.23, 0.07, 0.18, 1.01, flat_material(f"{name}_pants", (0.27, 0.48, 0.74, 1)), coll)
    plane(f"{name}_leg_right", x + 0.06 + pose * 0.14, y - 0.23, 0.07, 0.18, 1.01, flat_material(f"{name}_pants_r", (0.27, 0.48, 0.74, 1)), coll)


def build_scene_life(coll: bpy.types.Collection) -> None:
    for index, (x, y, shirt, pose) in enumerate([
        (-9.6, -0.55, (0.35, 0.72, 0.32, 1), 0.05),
        (-3.55, 0.55, (0.93, 0.54, 0.26, 1), -0.04),
        (1.95, -0.05, (0.32, 0.62, 0.86, 1), 0.06),
        (8.1, 0.25, (0.92, 0.78, 0.26, 1), -0.05),
        (7.65, -4.2, (0.44, 0.76, 0.86, 1), 0.04),
    ]):
        tiny_actor(coll, f"scene_actor_{index}", x, y, shirt, pose)

    route_mat = flat_material("active_route_glow", (1.0, 0.96, 0.52, 0.32))
    for index, (x, y, w, h) in enumerate([
        (-7.0, -0.15, 2.2, 0.18),
        (-4.0, 0.35, 1.8, 0.16),
        (0.3, 0.42, 1.9, 0.16),
        (3.6, 0.28, 1.6, 0.16),
        (7.1, 0.0, 2.1, 0.18),
        (7.4, -2.15, 0.18, 1.7),
    ]):
        ellipse(f"active_route_{index}", x, y, w, h, 0.88, route_mat.diffuse_color[:], coll, 24)


def build_occlusion(coll: bpy.types.Collection) -> None:
    for x, y, scale, tile_id in [
        (-10.85, -0.55, 0.62, 155),
        (-8.35, -1.0, 0.58, 157),
        (-3.8, 0.9, 0.5, 156),
        (2.5, 0.1, 0.52, 159),
        (7.7, 0.7, 0.56, 155),
        (10.65, 0.25, 0.58, 157),
        (7.25, -3.75, 0.54, 156),
        (9.7, -4.65, 0.52, 159),
    ]:
        tile(tile_id, x, y, 1.12, coll, scale, "foreground_occlusion_leaf")

    for name, x, y, w, h in [
        ("building_shadow_mailbox", -9.25, 0.06, 1.0, 0.16),
        ("building_shadow_board", -3.1, 0.72, 0.9, 0.14),
        ("building_shadow_workshop", 1.0, 0.38, 1.05, 0.16),
        ("building_shadow_market", 9.0, 0.28, 1.0, 0.16),
        ("building_shadow_dock", 9.2, -5.0, 1.08, 0.16),
    ]:
        ellipse(name, x, y, w, h, 1.1, (0.12, 0.1, 0.06, 0.16), coll, 32)


def build_path_soft_edges(coll: bpy.types.Collection) -> None:
    soft_edge = (0.52, 0.82, 0.28, 0.28)
    warm_dust = (0.88, 0.62, 0.32, 0.18)
    for index, (x, y, w, h, angle, color) in enumerate([
        (-10.2, 0.55, 2.7, 0.34, 8, soft_edge),
        (-7.35, 0.28, 2.4, 0.28, -4, warm_dust),
        (-4.65, 0.48, 2.2, 0.25, 10, soft_edge),
        (-1.6, 0.78, 2.1, 0.24, -8, warm_dust),
        (1.8, 0.62, 2.3, 0.25, 7, warm_dust),
        (4.8, 0.35, 2.2, 0.28, -6, soft_edge),
        (7.9, 0.16, 2.4, 0.28, 8, warm_dust),
        (10.1, 0.38, 2.0, 0.32, -10, soft_edge),
        (-7.85, -2.4, 0.42, 2.7, 2, soft_edge),
        (7.2, -2.55, 0.42, 2.8, -4, soft_edge),
        (-1.4, -2.2, 2.0, 0.24, -18, warm_dust),
        (2.1, -2.15, 2.0, 0.24, 18, warm_dust),
        (-6.0, 3.35, 1.8, 0.22, -34, warm_dust),
        (6.1, 3.2, 1.8, 0.22, 34, warm_dust),
    ]):
        ellipse(f"path_soft_edge_{index}", x, y, w, h, 0.89, color, coll, 48, angle)

    pebble = flat_material("path_pebble_ink", (0.5, 0.35, 0.18, 0.28))
    for index, (x, y) in enumerate([
        (-9.3, 0.22), (-6.8, 0.44), (-4.4, 0.1), (-1.0, 0.52),
        (1.4, 0.28), (3.2, 0.65), (5.4, 0.06), (8.6, 0.45),
        (-7.8, -1.7), (-7.95, -3.4), (7.25, -1.45), (7.05, -3.15),
        (-5.6, 3.05), (5.8, 2.98),
    ]):
        ellipse(f"path_pebble_{index}", x, y, 0.16, 0.07, 1.08, pebble.diffuse_color[:], coll, 16, (index * 37) % 180)


def build_world_composition_polish(coll: bpy.types.Collection) -> None:
    grass = (0.45, 0.78, 0.24, 0.11)
    light_grass = (0.72, 0.95, 0.35, 0.08)
    road_dust = (0.93, 0.7, 0.38, 0.08)
    blue_haze = (0.45, 0.82, 1.0, 0.025)
    dark_leaf = (0.18, 0.48, 0.22, 0.34)

    for index, (x, y, w, h, angle, color) in enumerate([
        (-9.4, 1.1, 5.2, 2.6, 4, (0.58, 0.86, 0.28, 0.08)),
        (-3.2, 1.05, 4.2, 2.2, -8, (0.72, 0.91, 0.35, 0.07)),
        (1.35, 0.9, 4.8, 2.5, 6, (0.52, 0.78, 0.38, 0.08)),
        (5.0, 0.75, 4.2, 2.2, -4, (0.62, 0.9, 0.42, 0.08)),
        (9.1, 0.85, 5.0, 2.5, 8, (0.78, 0.88, 0.3, 0.07)),
        (-9.5, -3.2, 5.5, 3.2, -6, (0.66, 0.84, 0.3, 0.08)),
        (8.9, -3.55, 5.7, 3.0, 5, (0.48, 0.82, 0.44, 0.08)),
        (-0.4, -3.8, 6.2, 3.4, 0, (0.56, 0.82, 0.28, 0.08)),
    ]):
        organic_blob(f"organic_playable_region_{index}", x, y, w, h, 0.18, color, coll, 24, angle, 0.14)

    for index, (x, y, w, h, angle, color) in enumerate([
        (-8.2, 0.34, 5.9, 0.72, -5, (0.95, 0.72, 0.38, 0.16)),
        (-2.6, 0.54, 5.5, 0.66, 7, (0.95, 0.72, 0.38, 0.14)),
        (3.0, 0.48, 5.7, 0.66, -6, (0.95, 0.72, 0.38, 0.14)),
        (8.6, 0.34, 6.0, 0.72, 5, (0.95, 0.72, 0.38, 0.16)),
        (-8.05, -2.9, 0.95, 4.3, 2, grass),
        (7.15, -2.85, 1.0, 4.3, -3, grass),
        (-5.7, 3.55, 3.2, 0.48, -32, road_dust),
        (5.8, 3.5, 3.2, 0.48, 32, road_dust),
        (-4.9, -1.95, 2.9, 0.42, -24, road_dust),
        (4.7, -1.95, 2.9, 0.42, 24, road_dust),
    ]):
        ellipse(f"painted_path_ribbon_{index}", x, y, w, h, 0.24, color, coll, 64, angle)

    for index, (x, y, w, h, angle) in enumerate([
        (-11.0, 0.62, 2.5, 0.72, 18), (-9.0, -0.28, 2.2, 0.55, -8),
        (-6.8, 0.75, 2.1, 0.55, 12), (-4.15, -0.1, 2.0, 0.5, -18),
        (-1.0, 0.18, 2.4, 0.55, 16), (1.45, -0.08, 2.2, 0.5, -14),
        (4.55, 0.75, 2.2, 0.52, 12), (6.75, -0.24, 2.1, 0.54, -10),
        (9.5, 0.72, 2.4, 0.6, 16), (11.0, -0.2, 2.0, 0.5, -12),
        (-8.0, -1.75, 1.0, 2.4, 6), (7.2, -1.65, 1.05, 2.3, -7),
        (-0.35, -2.7, 1.15, 2.7, 4), (-0.35, -4.4, 1.35, 2.5, -4),
    ]):
        ellipse(f"grass_bites_into_path_{index}", x, y, w, h, 0.28, grass if index % 2 else light_grass, coll, 56, angle)

    for index, (x, y, w, h, alpha) in enumerate([
        (-8.4, 5.25, 7.0, 1.2, 0.1), (-0.2, 5.45, 8.0, 1.0, 0.08), (8.4, 5.25, 7.2, 1.2, 0.1),
        (-8.8, -5.65, 6.8, 0.8, 0.1), (7.9, -5.55, 6.2, 0.75, 0.1),
    ]):
        ellipse(f"world_depth_color_band_{index}", x, y, w, h, 0.3, (dark_leaf[0], dark_leaf[1], dark_leaf[2], alpha), coll, 64)

    for index, (x, y, w, h, angle) in enumerate([
        (-4.3, 4.25, 5.5, 0.55, -7), (2.8, 4.2, 5.6, 0.48, 6),
        (-2.2, -5.55, 6.8, 0.42, 4), (3.9, -5.3, 5.2, 0.36, -8),
        (-10.0, -1.2, 4.8, 0.36, -4), (8.8, -1.25, 4.8, 0.36, 4),
    ]):
        ellipse(f"soft_air_perspective_{index}", x, y, w, h, 1.05, blue_haze, coll, 64, angle)

    sparkle = flat_material("tiny_feedback_spark", (1.0, 0.95, 0.42, 0.72))
    for index, (x, y) in enumerate([
        (-9.4, -2.25), (-8.6, -3.6), (-3.2, 1.85), (0.0, 0.55),
        (1.2, 1.5), (4.4, 1.2), (8.8, 1.35), (8.4, -4.25), (9.7, -3.8),
    ]):
        plane(f"world_task_spark_{index}_a", x, y, 0.22, 0.04, 1.32, sparkle, coll).rotation_euler[2] = math.radians(45)
        plane(f"world_task_spark_{index}_b", x, y, 0.22, 0.04, 1.33, sparkle, coll).rotation_euler[2] = math.radians(-45)

    for index, (x, y, w, h, angle) in enumerate([
        (-11.2, 3.6, 2.2, 0.45, -10), (-6.9, 5.0, 2.0, 0.4, 8),
        (-1.8, 3.9, 2.4, 0.42, -4), (3.2, 4.6, 2.5, 0.42, 7),
        (8.5, 3.7, 2.1, 0.38, -9), (11.0, 4.9, 2.0, 0.36, 6),
    ]):
        organic_blob(f"distant_meadow_patch_{index}", x, y, w, h, 0.2, (0.36, 0.68, 0.28, 0.1), coll, 18, angle, 0.2)

    for index, (x, y) in enumerate([(-10.9, -2.45), (-10.1, -3.15), (-9.2, -2.55), (-8.2, -3.25), (7.8, -3.2), (8.8, -3.75), (9.6, -3.2)]):
        ellipse(f"activity_hint_ring_{index}", x, y, 0.42, 0.18, 1.2, (1.0, 0.92, 0.36, 0.42), coll, 32, (index * 17) % 180)


def build_painted_terrain_pass(coll: bpy.types.Collection) -> None:
    road = (0.82, 0.58, 0.31, 0.24)
    road_light = (0.95, 0.74, 0.42, 0.12)
    grass_cut = (0.53, 0.82, 0.28, 0.16)
    meadow_light = (0.78, 0.96, 0.42, 0.1)
    water_air = (0.7, 0.95, 1.0, 0.08)

    for index, (x, y, w, h, angle, wobble) in enumerate([
        (-8.7, 0.0, 6.2, 0.72, 0, 0.04),
        (-2.45, 0.15, 5.5, 0.74, 4, 0.05),
        (3.4, 0.1, 5.6, 0.72, -3, 0.05),
        (8.9, 0.0, 5.9, 0.7, 0, 0.04),
        (-7.85, -2.55, 0.88, 5.2, -2, 0.06),
        (7.2, -2.5, 0.86, 5.1, 2, 0.06),
        (-0.25, -3.15, 0.9, 5.0, 0, 0.06),
        (-5.9, 3.55, 3.3, 0.56, -35, 0.06),
        (6.0, 3.55, 3.3, 0.56, 35, 0.06),
        (-5.1, -1.9, 3.0, 0.5, -25, 0.06),
        (4.9, -1.9, 3.0, 0.5, 25, 0.06),
    ]):
        organic_blob(f"painted_main_road_{index}", x, y, w, h, 0.82, road, coll, 30, angle, wobble)
        organic_blob(f"painted_main_road_highlight_{index}", x, y + 0.05, w * 0.72, h * 0.22, 0.84, road_light, coll, 22, angle + 2, wobble * 0.8)

    for index, (x, y, w, h, angle) in enumerate([
        (-11.4, 0.65, 1.5, 0.7, 10), (-9.7, -0.55, 1.4, 0.65, -8),
        (-6.5, 0.62, 1.55, 0.62, 7), (-4.0, -0.55, 1.45, 0.58, -10),
        (-0.6, 0.95, 1.5, 0.55, 9), (1.7, -0.65, 1.45, 0.56, -8),
        (4.8, 0.8, 1.45, 0.58, 8), (6.8, -0.7, 1.4, 0.56, -7),
        (9.8, 0.68, 1.5, 0.62, 8), (11.3, -0.58, 1.25, 0.54, -10),
        (-8.75, -1.85, 0.62, 1.55, 3), (-7.2, -4.15, 0.64, 1.35, -4),
        (6.4, -1.9, 0.62, 1.55, -3), (7.95, -4.05, 0.64, 1.35, 4),
        (-1.25, -2.4, 0.64, 1.65, -4), (0.75, -4.45, 0.66, 1.35, 4),
    ]):
        organic_blob(f"painted_grass_edge_{index}", x, y, w, h, 0.88, grass_cut if index % 2 else meadow_light, coll, 20, angle, 0.22)

    for index, (x, y, w, h, angle) in enumerate([
        (-10.1, -2.2, 4.4, 0.28, -4), (-9.0, -4.35, 4.0, 0.28, 6),
        (7.9, -2.15, 4.2, 0.28, 4), (9.0, -4.35, 4.0, 0.28, -6),
    ]):
        ellipse(f"water_surface_streak_{index}", x, y, w, h, 0.9, water_air, coll, 48, angle)


def build_region_identity_pass(coll: bpy.types.Collection) -> None:
    ink = flat_material("region_identity_ink", (0.16, 0.28, 0.18, 0.72))
    warm = flat_material("region_identity_warm", (1.0, 0.78, 0.32, 0.78))
    red = flat_material("region_identity_red", (0.95, 0.36, 0.28, 0.82))
    blue = flat_material("region_identity_blue", (0.28, 0.72, 0.95, 0.74))
    leaf = flat_material("region_identity_leaf", (0.2, 0.62, 0.28, 0.72))
    glass = flat_material("region_identity_glass", (0.65, 1.0, 0.88, 0.46))
    soil = flat_material("region_identity_soil", (0.56, 0.36, 0.16, 0.52))

    for index, y in enumerate([-2.25, -2.85, -3.45]):
        ellipse(f"farm_curved_crop_row_{index}", -9.9, y, 4.5, 0.18, 1.08, soil.diffuse_color[:], coll, 48, 2)
        for seed in range(5):
            ellipse(f"farm_crop_leaf_{index}_{seed}", -11.8 + seed * 0.95, y + 0.08, 0.16, 0.12, 1.22, leaf.diffuse_color[:], coll, 16, seed * 18)

    for index, x in enumerate([8.15, 8.95, 9.75]):
        plane(f"market_canopy_{index}", x, 1.82, 0.72, 0.22, 1.24, red if index % 2 == 0 else warm, coll)
        ellipse(f"market_lantern_{index}", x, 1.48, 0.12, 0.16, 1.26, (1.0, 0.9, 0.36, 0.9), coll, 16)
        plane(f"market_counter_{index}", x, 1.12, 0.58, 0.12, 1.22, ink, coll)

    for index, x in enumerate([3.65, 4.25, 4.85]):
        plane(f"greenhouse_glass_identity_{index}", x, 0.95, 0.24, 1.3, 1.2, glass, coll).rotation_euler[2] = math.radians(-4 + index * 4)
    for index, x in enumerate([0.35, 0.85, 1.35, 1.85]):
        ellipse(f"workshop_gear_hint_{index}", x, 1.0 + (index % 2) * 0.28, 0.22, 0.22, 1.22, (0.42, 0.52, 0.54, 0.62), coll, 20)
        ellipse(f"workshop_gear_core_{index}", x, 1.0 + (index % 2) * 0.28, 0.08, 0.08, 1.23, (0.2, 0.28, 0.3, 0.82), coll, 14)

    for index, (x, y) in enumerate([(7.65, -4.15), (8.25, -4.0), (8.85, -4.22), (9.45, -4.05)]):
        ellipse(f"dock_cargo_coin_{index}", x, y, 0.18, 0.18, 1.25, warm.diffuse_color[:], coll, 20)
        ellipse(f"dock_cargo_shadow_{index}", x, y - 0.1, 0.24, 0.06, 1.18, (0.08, 0.08, 0.04, 0.22), coll, 16)
    plane("dock_blue_route_tag", 8.85, -3.58, 1.25, 0.14, 1.24, blue, coll)

    for index, (x, y, sx, sy, color) in enumerate([
        (-11.9, 5.0, 1.8, 0.52, (0.24, 0.58, 0.25, 0.42)),
        (-4.2, 5.25, 2.2, 0.44, (0.28, 0.62, 0.26, 0.32)),
        (4.2, 5.25, 2.2, 0.44, (0.28, 0.62, 0.26, 0.32)),
        (11.9, 5.0, 1.8, 0.52, (0.24, 0.58, 0.25, 0.42)),
        (-11.9, -5.8, 1.9, 0.6, (0.16, 0.46, 0.24, 0.38)),
        (11.9, -5.8, 1.9, 0.6, (0.16, 0.46, 0.24, 0.38)),
    ]):
        organic_blob(f"foreground_leaf_depth_{index}", x, y, sx, sy, 1.34, color, coll, 22, index * 11, 0.2)


def build_world_depth_pass(coll: bpy.types.Collection) -> None:
    far_blue = (0.58, 0.86, 1.0, 0.08)
    far_green = (0.28, 0.58, 0.32, 0.12)
    cliff = (0.36, 0.52, 0.42, 0.12)
    sun = (1.0, 0.86, 0.38, 0.12)

    for index, (x, y, w, h, angle, color) in enumerate([
        (-9.5, 5.65, 6.8, 0.72, -3, far_green),
        (-2.6, 5.82, 7.4, 0.62, 2, far_blue),
        (5.2, 5.72, 7.2, 0.7, -2, far_green),
        (11.0, 5.55, 4.0, 0.6, 5, far_blue),
        (-12.0, -5.95, 3.6, 0.62, -6, cliff),
        (12.0, -5.95, 3.6, 0.62, 6, cliff),
    ]):
        organic_blob(f"far_horizon_layer_{index}", x, y, w, h, 0.32, color, coll, 26, angle, 0.16)

    for index, (x, y, w, h, angle) in enumerate([
        (-11.0, 4.1, 2.8, 0.18, 8), (-6.6, 4.9, 2.4, 0.14, -6),
        (-1.4, 4.55, 2.6, 0.16, 4), (3.4, 4.95, 2.4, 0.14, -4),
        (8.0, 4.4, 2.7, 0.16, 6), (11.4, 4.85, 2.2, 0.14, -5),
    ]):
        ellipse(f"far_path_hint_{index}", x, y, w, h, 0.5, (1.0, 0.86, 0.52, 0.08), coll, 32, angle)

    for index, (x, y, w, h, angle) in enumerate([
        (-12.6, 2.8, 1.6, 0.46, 18), (12.6, 2.75, 1.6, 0.46, -18),
        (-12.4, -1.1, 1.7, 0.42, -10), (12.2, -1.0, 1.7, 0.42, 10),
    ]):
        organic_blob(f"side_foreground_canopy_{index}", x, y, w, h, 1.38, (0.18, 0.48, 0.24, 0.16), coll, 22, angle, 0.24)

    for index, (x, y, w, h) in enumerate([
        (-9.2, 1.42, 1.35, 0.18), (-3.1, 2.1, 1.2, 0.16),
        (1.0, 1.85, 1.35, 0.16), (4.3, 1.45, 1.2, 0.16),
        (9.0, 1.55, 1.5, 0.18), (9.2, -4.1, 1.2, 0.14),
    ]):
        ellipse(f"building_top_warm_glint_{index}", x, y, w, h, 1.31, sun, coll, 32, -4 + index)


def build_building_upgrade_pass(coll: bpy.types.Collection) -> None:
    trim_dark = flat_material("building_upgrade_trim_dark", (0.18, 0.25, 0.2, 0.64))
    warm_trim = flat_material("building_upgrade_warm_trim", (1.0, 0.78, 0.36, 0.72))
    roof_red = flat_material("building_upgrade_roof_red", (0.82, 0.32, 0.24, 0.58))
    roof_blue = flat_material("building_upgrade_roof_blue", (0.22, 0.58, 0.82, 0.52))
    glass = flat_material("building_upgrade_glass", (0.62, 0.95, 1.0, 0.66))
    banner = flat_material("building_upgrade_banner", (0.96, 0.48, 0.28, 0.76))

    for index, (x, y, w, mat) in enumerate([
        (-9.2, 1.48, 1.25, warm_trim),
        (-3.1, 2.12, 1.35, banner),
        (1.0, 1.82, 1.2, roof_blue),
        (4.3, 1.42, 1.15, glass),
        (9.0, 1.78, 1.55, banner),
        (9.2, -4.02, 1.1, roof_red),
    ]):
        plane(f"building_upgrade_sign_band_{index}", x, y, w, 0.12, 1.42, mat, coll)
        ellipse(f"building_upgrade_sign_glow_{index}", x, y + 0.03, w * 0.82, 0.1, 1.43, (1.0, 0.95, 0.58, 0.24), coll, 32)

    for index, (x, y, color) in enumerate([
        (-9.62, 0.96, (0.75, 0.52, 0.3, 0.62)), (-8.78, 0.96, (0.75, 0.52, 0.3, 0.62)),
        (-3.56, 1.62, (0.32, 0.52, 0.68, 0.72)), (-2.64, 1.62, (0.32, 0.52, 0.68, 0.72)),
        (0.62, 1.28, (0.45, 0.56, 0.58, 0.72)), (1.38, 1.28, (0.45, 0.56, 0.58, 0.72)),
        (3.9, 0.9, (0.55, 0.95, 0.86, 0.72)), (4.7, 0.9, (0.55, 0.95, 0.86, 0.72)),
        (8.45, 1.05, (1.0, 0.82, 0.38, 0.72)), (9.55, 1.05, (1.0, 0.82, 0.38, 0.72)),
    ]):
        plane(f"building_upgrade_window_{index}", x, y, 0.18, 0.18, 1.41, flat_material(f"building_upgrade_window_mat_{index}", color), coll)
        plane(f"building_upgrade_window_sill_{index}", x, y - 0.12, 0.28, 0.04, 1.42, trim_dark, coll)

    for index, (x, y, h, color) in enumerate([
        (-2.32, 2.1, 0.52, (0.38, 0.28, 0.18, 0.76)),
        (1.56, 1.85, 0.48, (0.28, 0.36, 0.38, 0.76)),
        (8.42, 1.82, 0.42, (0.55, 0.3, 0.18, 0.72)),
    ]):
        plane(f"building_upgrade_chimney_{index}", x, y, 0.18, h, 1.39, flat_material(f"building_upgrade_chimney_mat_{index}", color), coll)
        ellipse(f"building_upgrade_smoke_{index}", x, y + h * 0.58, 0.38, 0.14, 1.44, (0.84, 0.96, 1.0, 0.28), coll, 24)


def build_set_piece_pass(coll: bpy.types.Collection) -> None:
    wood = flat_material("set_piece_wood", (0.55, 0.34, 0.18, 0.94))
    dark = flat_material("set_piece_dark", (0.14, 0.22, 0.18, 0.82))
    cloth = flat_material("set_piece_cloth", (0.94, 0.42, 0.32, 0.9))
    gold = flat_material("set_piece_gold", (1.0, 0.78, 0.28, 0.92))
    metal = flat_material("set_piece_metal", (0.48, 0.58, 0.6, 0.86))
    leaf = flat_material("set_piece_leaf", (0.18, 0.58, 0.28, 0.9))
    glass = flat_material("set_piece_glass", (0.56, 0.94, 1.0, 0.62))

    # Farm windmill silhouette.
    plane("farm_windmill_tower", -11.55, -1.72, 0.16, 1.0, 1.42, wood, coll)
    ellipse("farm_windmill_hub", -11.55, -1.12, 0.18, 0.18, 1.46, gold.diffuse_color[:], coll, 20)
    for index, angle in enumerate([0, 45, 90, 135]):
        blade = plane(f"farm_windmill_blade_{index}", -11.55, -1.12, 0.08, 0.72, 1.45, flat_material(f"farm_windmill_blade_mat_{index}", (0.96, 0.84, 0.52, 0.72)), coll)
        blade.rotation_euler[2] = math.radians(angle)

    # Workshop chimney and belt crane.
    plane("workshop_tall_chimney", 1.85, 1.85, 0.22, 0.85, 1.45, metal, coll)
    ellipse("workshop_smoke_puff_a", 1.85, 2.38, 0.42, 0.18, 1.48, (0.86, 0.96, 1.0, 0.32), coll, 24)
    ellipse("workshop_smoke_puff_b", 2.15, 2.58, 0.32, 0.14, 1.48, (0.86, 0.96, 1.0, 0.22), coll, 24)
    plane("workshop_crane_arm", 0.5, 1.78, 1.2, 0.08, 1.45, metal, coll).rotation_euler[2] = math.radians(-8)
    plane("workshop_crane_hook", -0.02, 1.48, 0.06, 0.32, 1.46, dark, coll)

    # Market identity sign and fabric edge.
    plane("market_big_sign", 9.0, 2.25, 1.45, 0.22, 1.46, cloth, coll)
    for index, x in enumerate([8.35, 8.78, 9.22, 9.65]):
        ellipse(f"market_hanging_lamp_{index}", x, 1.98, 0.12, 0.16, 1.48, gold.diffuse_color[:], coll, 16)

    # Greenhouse arched glass and planted vine.
    ellipse("greenhouse_arch_glass", 4.3, 1.25, 1.15, 1.35, 1.43, glass.diffuse_color[:], coll, 40)
    plane("greenhouse_arch_mask", 4.3, 0.78, 1.2, 0.7, 1.44, flat_material("greenhouse_arch_mask", (0.42, 0.82, 0.55, 0.22)), coll)
    for index, y in enumerate([0.45, 0.75, 1.05]):
        ellipse(f"greenhouse_vine_leaf_{index}", 3.72 + index * 0.28, y, 0.18, 0.12, 1.49, leaf.diffuse_color[:], coll, 16, index * 20)

    # Dock loading crane.
    plane("dock_crane_base", 10.2, -4.05, 0.22, 0.72, 1.46, wood, coll)
    arm = plane("dock_crane_arm", 9.75, -3.52, 1.2, 0.08, 1.47, wood, coll)
    arm.rotation_euler[2] = math.radians(18)
    plane("dock_crane_rope", 9.35, -3.72, 0.04, 0.48, 1.48, dark, coll)
    ellipse("dock_crane_hook", 9.35, -3.98, 0.16, 0.12, 1.49, gold.diffuse_color[:], coll, 16)


def build_interaction_devices(coll: bpy.types.Collection) -> None:
    panel = flat_material("device_panel", (0.25, 0.38, 0.26, 0.82))
    accent = flat_material("device_accent", (1.0, 0.82, 0.28, 0.9))
    blue = flat_material("device_blue", (0.25, 0.62, 0.92, 0.82))
    green = flat_material("device_green", (0.34, 0.78, 0.42, 0.82))

    for index, (x, y, mat) in enumerate([
        (-9.75, 0.18, accent), (-9.25, 0.18, panel), (-8.75, 0.18, green),
        (-3.45, 0.82, accent), (-3.05, 0.82, panel), (-2.65, 0.82, blue),
        (8.55, 0.48, accent), (9.0, 0.48, green), (9.45, 0.48, blue),
    ]):
        plane(f"task_chip_{index}", x, y, 0.24, 0.12, 1.18, mat, coll)

    for index, (x, y, value) in enumerate([
        (0.35, 0.1, 0.35),
        (0.95, 0.1, 0.58),
        (1.55, 0.1, 0.78),
        (4.0, 0.0, 0.45),
        (4.58, 0.0, 0.7),
        (5.16, 0.0, 0.52),
    ]):
        plane(f"progress_slot_{index}", x, y, 0.42, 0.12, 1.16, panel, coll)
        plane(f"progress_fill_{index}", x - (0.42 - 0.42 * value) / 2, y, 0.42 * value, 0.12, 1.17, green if index >= 3 else blue, coll)

    for index, (x, y) in enumerate([
        (7.85, -4.55), (8.45, -4.55), (9.05, -4.55), (9.65, -4.55),
        (7.9, -3.95), (8.5, -3.95), (9.1, -3.95),
    ]):
        ellipse(f"dock_delivery_marker_{index}", x, y, 0.22, 0.22, 1.15, (1.0, 0.86, 0.35, 0.68), coll, 24)

    for index, (x, y, w, h, angle) in enumerate([
        (-10.1, -2.7, 3.8, 0.18, 0),
        (-10.1, -3.35, 3.8, 0.18, 0),
        (-11.2, -3.0, 0.18, 1.45, 0),
        (-9.0, -3.0, 0.18, 1.45, 0),
        (8.95, 1.85, 2.0, 0.14, -6),
        (8.95, 2.25, 2.0, 0.14, 6),
    ]):
        ellipse(f"play_zone_border_{index}", x, y, w, h, 1.13, (0.22, 0.32, 0.16, 0.26), coll, 32, angle)


def build_center_landmark(coll: bpy.types.Collection) -> None:
    glow = (0.36, 0.82, 1.0, 0.22)
    glass = flat_material("landmark_glass", (0.48, 0.86, 1.0, 0.72))
    core = flat_material("landmark_core", (0.1, 0.46, 0.88, 0.92))
    gold = flat_material("landmark_gold", (1.0, 0.78, 0.24, 0.9))
    ink = flat_material("landmark_ink", (0.16, 0.26, 0.28, 0.78))

    for index, (w, h, alpha) in enumerate([(2.6, 1.4, 0.22), (1.8, 1.0, 0.28), (1.1, 0.62, 0.34)]):
        ellipse(f"hub_beacon_glow_{index}", -0.55, 0.05, w, h, 1.2 + index * 0.01, (glow[0], glow[1], glow[2], alpha), coll, 64)

    plane("hub_beacon_base", -0.55, -0.33, 0.78, 0.18, 1.24, ink, coll)
    plane("hub_beacon_column", -0.55, -0.05, 0.26, 0.62, 1.25, core, coll)
    top = plane("hub_beacon_crystal_top", -0.55, 0.36, 0.44, 0.44, 1.28, glass, coll)
    top.rotation_euler[2] = math.radians(45)
    mid = plane("hub_beacon_crystal_mid", -0.55, 0.05, 0.5, 0.5, 1.27, glass, coll)
    mid.rotation_euler[2] = math.radians(45)
    plane("hub_beacon_gold_left", -0.9, -0.18, 0.16, 0.45, 1.29, gold, coll).rotation_euler[2] = math.radians(-18)
    plane("hub_beacon_gold_right", -0.2, -0.18, 0.16, 0.45, 1.29, gold, coll).rotation_euler[2] = math.radians(18)

    for index, (x, y, color) in enumerate([
        (-9.8, 0.95, (1.0, 0.88, 0.3, 0.9)),
        (-3.2, 1.95, (0.38, 0.72, 1.0, 0.9)),
        (1.1, 1.7, (0.38, 1.0, 0.62, 0.9)),
        (4.35, 1.35, (0.38, 1.0, 0.82, 0.9)),
        (9.15, 1.7, (1.0, 0.66, 0.3, 0.9)),
    ]):
        ellipse(f"feedback_bubble_{index}", x, y, 0.34, 0.26, 1.3, color, coll, 32)
        plane(f"feedback_mark_{index}", x, y + 0.01, 0.05, 0.16, 1.31, ink, coll)
        ellipse(f"feedback_dot_{index}", x, y - 0.1, 0.06, 0.06, 1.31, ink.diffuse_color[:], coll, 16)

    for index, (x, y, w, h, angle) in enumerate([
        (-2.0, 0.3, 1.7, 0.08, 6),
        (1.0, 0.25, 1.8, 0.08, -5),
        (-0.6, 1.05, 0.08, 1.05, 0),
        (-0.6, -0.78, 0.08, 0.85, 0),
    ]):
        ellipse(f"hub_energy_route_{index}", x, y, w, h, 1.22, (0.42, 0.88, 1.0, 0.34), coll, 32, angle)


def build_debug(coll: bpy.types.Collection, collision_coll: bpy.types.Collection) -> None:
    hot_mat = flat_material("hotspot translucent red", (1, 0.24, 0.24, 0.3))
    col_mat = flat_material("collision translucent purple", (0.55, 0.12, 0.9, 0.28))
    for name, x, y, w, h in [
        ("需求信箱", -9.2, 0.65, 1.4, 1.6),
        ("委托公告板", -3.1, 1.2, 1.5, 1.5),
        ("机械工坊", 0.9, 0.75, 1.6, 1.6),
        ("成果温室", 4.3, 0.55, 1.7, 1.7),
        ("订单集市", 9.0, 0.8, 1.7, 1.6),
        ("农田种植区", -9.7, -2.9, 4.9, 2.5),
        ("交付码头", 8.6, -3.5, 2.8, 1.4),
    ]:
        plane(f"HOTSPOT__{name}", x, y, w, h, 0.95, hot_mat, coll)
        label(name, x, y, 1.0, coll, 0.2)
    plane("COLLISION__west_lake", -8.2, -3.1, 6.4, 2.2, 0.92, col_mat, collision_coll)
    plane("COLLISION__east_lake", 8.4, -3.1, 6.4, 2.2, 0.92, col_mat, collision_coll)
    label("水域碰撞", 1.2, -3.35, 1.01, collision_coll, 0.2)
    return
    for name, x, y, w, h in [
        ("需求信箱", -9.2, 0.65, 1.4, 1.6),
        ("委托公告板", -3.1, 1.2, 1.5, 1.5),
        ("机械工坊", 0.9, 0.75, 1.6, 1.6),
        ("成果温室", 4.3, 0.55, 1.7, 1.7),
        ("订单集市", 9.0, 0.8, 1.7, 1.6),
        ("农田种植区", -9.7, -2.9, 4.9, 2.5),
        ("交付码头", 8.6, -3.5, 2.8, 1.4),
    ]:
        plane(f"HOTSPOT__{name}", x, y, w, h, 0.95, hot_mat, coll)
        label(name, x, y, 1.0, coll, 0.2)
    plane("COLLISION__west_lake", -8.2, -3.1, 6.4, 2.2, 0.92, col_mat, collision_coll)
    plane("COLLISION__east_lake", 8.4, -3.1, 6.4, 2.2, 0.92, col_mat, collision_coll)
    label("水域碰撞", 1.2, -3.35, 1.01, collision_coll, 0.2)
    return
    hotspots = [
        ("需求信箱", -9.2, 0.65, 1.4, 1.6),
        ("委托公告板", -3.1, 1.2, 1.5, 1.5),
        ("机械工坊", 0.9, 0.75, 1.6, 1.6),
        ("成果温室", 4.3, 0.55, 1.7, 1.7),
        ("订单集市", 9.0, 0.8, 1.7, 1.6),
        ("交付码头", 8.6, -3.5, 2.8, 1.4),
    ]
    for name, x, y, w, h in hotspots:
        plane(f"HOTSPOT__{name}", x, y, w, h, 0.95, hot_mat, coll)
        label(name, x, y, 1.0, coll, 0.2)
    for name, x, y, w, h in [
        ("需求信箱", -9.2, 0.65, 1.4, 1.6),
        ("委托公告板", -3.1, 1.2, 1.5, 1.5),
        ("机械工坊", 0.9, 0.75, 1.6, 1.6),
        ("成果温室", 4.3, 0.55, 1.7, 1.7),
        ("订单集市", 9.0, 0.8, 1.7, 1.6),
        ("交付码头", 8.6, -3.5, 2.8, 1.4),
    ]:
        plane(f"HOTSPOT__{name}", x, y, w, h, 0.95, hot_mat, coll)
        label(name, x, y, 1.0, coll, 0.2)
    plane("COLLISION__west_lake", -8.2, -3.1, 6.4, 2.2, 0.92, col_mat, collision_coll)
    plane("COLLISION__east_lake", 8.4, -3.1, 6.4, 2.2, 0.92, col_mat, collision_coll)
    label("水域碰撞", 1.2, -3.2, 1.01, collision_coll, 0.2)
    label("水域碰撞", 1.2, -3.5, 1.0, collision_coll, 0.2)


def sprite_frame(coll: bpy.types.Collection, name: str, x: float, y: float, shirt: tuple[float, float, float, float], leg_swing: float, arm_swing: float, carry: bool = False) -> None:
    skin = (1.0, 0.78, 0.56, 1)
    hair = (0.35, 0.18, 0.1, 1)
    pants = (0.28, 0.58, 0.88, 1)
    outline = (0.1, 0.18, 0.2, 0.56)
    shadow = (0.05, 0.05, 0.04, 0.18)
    cheek = (1.0, 0.52, 0.48, 0.32)

    ellipse(f"sprite_{name}_shadow", x, y - 0.55, 0.62, 0.14, 1.1, shadow, coll, 32)
    ellipse(f"sprite_{name}_body_outline", x, y - 0.13, 0.55, 0.79, 1.155, outline, coll, 48)
    ellipse(f"sprite_{name}_body", x, y - 0.12, 0.48, 0.72, 1.17, shirt, coll, 48)
    ellipse(f"sprite_{name}_body_highlight", x - 0.08, y + 0.02, 0.16, 0.42, 1.18, (1.0, 1.0, 1.0, 0.12), coll, 32, -8)
    ellipse(f"sprite_{name}_neck_outline", x, y + 0.2, 0.22, 0.2, 1.175, outline, coll, 24)
    ellipse(f"sprite_{name}_neck", x, y + 0.2, 0.18, 0.16, 1.18, skin, coll, 24)
    ellipse(f"sprite_{name}_head_outline", x, y + 0.48, 0.58, 0.56, 1.195, outline, coll, 48)
    ellipse(f"sprite_{name}_head", x, y + 0.48, 0.52, 0.5, 1.2, skin, coll, 48)
    ellipse(f"sprite_{name}_face_warm", x - 0.02, y + 0.45, 0.42, 0.3, 1.205, (1.0, 0.84, 0.66, 0.32), coll, 48)
    ellipse(f"sprite_{name}_hair_back", x, y + 0.65, 0.56, 0.34, 1.22, hair, coll, 48)
    ellipse(f"sprite_{name}_hair_cap", x - 0.04, y + 0.73, 0.44, 0.22, 1.235, hair, coll, 32, -7)
    ellipse(f"sprite_{name}_bang", x - 0.13, y + 0.63, 0.38, 0.18, 1.24, hair, coll, 32, -18)
    ellipse(f"sprite_{name}_eye_l", x - 0.1, y + 0.49, 0.065, 0.075, 1.25, outline, coll, 16)
    ellipse(f"sprite_{name}_eye_r", x + 0.12, y + 0.49, 0.065, 0.075, 1.25, outline, coll, 16)
    ellipse(f"sprite_{name}_eye_glint_l", x - 0.09, y + 0.51, 0.018, 0.018, 1.26, (1, 1, 1, 0.8), coll, 12)
    ellipse(f"sprite_{name}_eye_glint_r", x + 0.13, y + 0.51, 0.018, 0.018, 1.26, (1, 1, 1, 0.8), coll, 12)
    ellipse(f"sprite_{name}_cheek_l", x - 0.18, y + 0.4, 0.09, 0.04, 1.245, cheek, coll, 16)
    ellipse(f"sprite_{name}_cheek_r", x + 0.22, y + 0.4, 0.09, 0.04, 1.245, cheek, coll, 16)
    ellipse(f"sprite_{name}_smile", x + 0.02, y + 0.35, 0.18, 0.045, 1.25, (0.38, 0.18, 0.15, 0.5), coll, 16)

    left_arm_outline = plane(f"sprite_{name}_arm_l_outline", x - 0.28, y - 0.18 + arm_swing * 0.65, 0.15, 0.43, 1.175, flat_material(f"sprite_{name}_outline_l", outline), coll)
    right_arm_outline = plane(f"sprite_{name}_arm_r_outline", x + 0.28, y - 0.18 - arm_swing * 0.65, 0.15, 0.43, 1.175, flat_material(f"sprite_{name}_outline_r", outline), coll)
    left_arm = plane(f"sprite_{name}_arm_l", x - 0.28, y - 0.18 + arm_swing * 0.65, 0.11, 0.38, 1.18, flat_material(f"sprite_{name}_shirt_l", shirt), coll)
    right_arm = plane(f"sprite_{name}_arm_r", x + 0.28, y - 0.18 - arm_swing * 0.65, 0.11, 0.38, 1.18, flat_material(f"sprite_{name}_shirt_r", shirt), coll)
    left_arm_outline.rotation_euler[2] = math.radians(8 + arm_swing * 58)
    right_arm_outline.rotation_euler[2] = math.radians(-8 - arm_swing * 58)
    left_arm.rotation_euler[2] = math.radians(8 + arm_swing * 58)
    right_arm.rotation_euler[2] = math.radians(-8 - arm_swing * 58)
    ellipse(f"sprite_{name}_shoulder_l", x - 0.21, y + 0.0, 0.16, 0.15, 1.205, shirt, coll, 18)
    ellipse(f"sprite_{name}_shoulder_r", x + 0.21, y + 0.0, 0.16, 0.15, 1.205, shirt, coll, 18)
    ellipse(f"sprite_{name}_hand_l", x - 0.28, y - 0.39 + arm_swing * 0.8, 0.12, 0.09, 1.21, skin, coll, 16)
    ellipse(f"sprite_{name}_hand_r", x + 0.28, y - 0.39 - arm_swing * 0.8, 0.12, 0.09, 1.21, skin, coll, 16)

    left_leg_outline = plane(f"sprite_{name}_leg_l_outline", x - 0.12 - leg_swing, y - 0.68, 0.18, 0.56, 1.15, flat_material(f"sprite_{name}_pants_outline_l", outline), coll)
    right_leg_outline = plane(f"sprite_{name}_leg_r_outline", x + 0.12 + leg_swing, y - 0.68, 0.18, 0.56, 1.15, flat_material(f"sprite_{name}_pants_outline_r", outline), coll)
    left_leg = plane(f"sprite_{name}_leg_l", x - 0.12 - leg_swing, y - 0.68, 0.14, 0.5, 1.16, flat_material(f"sprite_{name}_pants_l", pants), coll)
    right_leg = plane(f"sprite_{name}_leg_r", x + 0.12 + leg_swing, y - 0.68, 0.14, 0.5, 1.16, flat_material(f"sprite_{name}_pants_r", pants), coll)
    left_leg_outline.rotation_euler[2] = math.radians(-4 - leg_swing * 90)
    right_leg_outline.rotation_euler[2] = math.radians(4 + leg_swing * 90)
    left_leg.rotation_euler[2] = math.radians(-4 - leg_swing * 90)
    right_leg.rotation_euler[2] = math.radians(4 + leg_swing * 90)
    ellipse(f"sprite_{name}_shoe_l", x - 0.12 - leg_swing * 1.25, y - 0.96, 0.2, 0.08, 1.19, outline, coll, 16)
    ellipse(f"sprite_{name}_shoe_r", x + 0.12 + leg_swing * 1.25, y - 0.96, 0.2, 0.08, 1.19, outline, coll, 16)
    if abs(leg_swing) > 0.04:
        ellipse(f"sprite_{name}_step_dust_l", x - 0.2, y - 1.0, 0.26, 0.05, 1.15, (0.85, 0.72, 0.42, 0.28), coll, 16, 8)
        ellipse(f"sprite_{name}_step_dust_r", x + 0.2, y - 0.98, 0.22, 0.045, 1.15, (0.85, 0.72, 0.42, 0.2), coll, 16, -8)

    if name == "harvest":
        plane(f"sprite_{name}_hoe_handle", x + 0.28, y - 0.08, 0.06, 0.72, 1.29, flat_material(f"sprite_{name}_hoe_handle_mat", (0.66, 0.42, 0.2, 1)), coll).rotation_euler[2] = math.radians(-24)
        plane(f"sprite_{name}_hoe_head", x + 0.1, y + 0.22, 0.28, 0.05, 1.3, flat_material(f"sprite_{name}_hoe_head_mat", (0.42, 0.5, 0.48, 1)), coll).rotation_euler[2] = math.radians(-24)
        for spark_index, (sx, sy) in enumerate([(0.42, -0.58), (0.54, -0.46), (0.35, -0.43)]):
            ellipse(f"sprite_{name}_harvest_spark_{spark_index}", x + sx, y + sy, 0.08, 0.08, 1.31, (1.0, 0.9, 0.28, 0.7), coll, 12)

    if carry:
        plane(f"sprite_{name}_crate", x + 0.02, y - 0.1, 0.42, 0.28, 1.3, flat_material(f"sprite_{name}_crate_mat", (0.74, 0.48, 0.24, 1)), coll)
        plane(f"sprite_{name}_crate_slit", x + 0.02, y - 0.1, 0.34, 0.04, 1.31, flat_material(f"sprite_{name}_crate_slit_mat", (0.38, 0.23, 0.12, 0.6)), coll)

    label(name, x, y - 1.18, 1.25, coll, 0.13)


def build_character(coll: bpy.types.Collection) -> None:
    plane("sprite_preview_backdrop", 0, -4.25, 5.8, 3.1, 1.0, flat_material("sprite_preview_backdrop", (0.68, 0.9, 1.0, 1)), coll)
    plane("sprite_preview_sun_band", 0, -3.35, 5.8, 1.0, 1.01, flat_material("sprite_preview_sun_band", (0.9, 0.98, 1.0, 1)), coll)
    ellipse("sprite_preview_sky_glow", 0, -3.45, 4.8, 0.75, 1.02, (1.0, 1.0, 1.0, 0.72), coll, 64)
    ellipse("sprite_preview_cloud_left", -1.9, -3.55, 1.25, 0.28, 1.03, (1.0, 1.0, 1.0, 0.86), coll, 32)
    ellipse("sprite_preview_cloud_right", 1.75, -3.6, 1.45, 0.3, 1.03, (1.0, 1.0, 1.0, 0.82), coll, 32)
    ellipse("sprite_preview_low_glow", 0, -4.68, 5.1, 0.42, 1.02, (0.94, 1.0, 0.66, 0.88), coll, 64)
    plane("sprite_preview_floor", 0, -5.05, 5.5, 0.5, 1.01, flat_material("sprite_preview_floor", (0.68, 0.92, 0.42, 1)), coll)
    for hill_index, (x, w, color) in enumerate([(-1.6, 2.8, (0.54, 0.82, 0.38, 0.42)), (1.4, 3.2, (0.44, 0.76, 0.36, 0.32))]):
        ellipse(f"sprite_preview_far_hill_{hill_index}", x, -4.75, w, 0.5, 1.015, (color[0], color[1], color[2], 0.88), coll, 48)
    for index, x in enumerate([-2.2, -1.1, 0.0, 1.1, 2.2]):
        ellipse(f"sprite_stage_marker_{index}", x, -5.05, 0.7, 0.12, 1.08, (0.14, 0.28, 0.12, 0.16), coll, 32)
    sprite_frame(coll, "idle", -2.2, -4.25, (0.38, 0.76, 0.38, 1), 0.0, 0.0)
    sprite_frame(coll, "walk_1", -1.1, -4.25, (0.38, 0.76, 0.38, 1), 0.08, 0.12)
    sprite_frame(coll, "walk_2", 0.0, -4.25, (0.38, 0.76, 0.38, 1), -0.08, -0.12)
    sprite_frame(coll, "harvest", 1.1, -4.25, (0.9, 0.58, 0.28, 1), 0.04, 0.2)
    sprite_frame(coll, "carry", 2.2, -4.25, (0.38, 0.62, 0.86, 1), -0.02, -0.04, True)
    return
    plane("character_preview_backdrop", 0, -4.35, 4.6, 2.8, 1.0, flat_material("character_preview_backdrop", (0.83, 0.95, 1.0, 1)), coll)
    plane("character_preview_floor", 0, -5.0, 4.25, 0.34, 1.01, flat_material("character_preview_floor", (0.73, 0.9, 0.62, 1)), coll)
    parts = {
        "face": material_from_image(CHARACTER_DIR / "Face" / "Completes" / "face1.png", "character"),
        "hair": material_from_image(CHARACTER_DIR / "Hair" / "Brown 1" / "brown1Man1.png", "character"),
        "shirt": material_from_image(CHARACTER_DIR / "Shirts" / "Green" / "greenShirt1.png", "character"),
        "arm": material_from_image(CHARACTER_DIR / "Shirts" / "Green" / "greenArm_long.png", "character"),
        "pants": material_from_image(CHARACTER_DIR / "Pants" / "Blue 1" / "pantsBlue11.png", "character"),
        "leg": material_from_image(CHARACTER_DIR / "Pants" / "Blue 1" / "pantsBlue1_long.png", "character"),
    }
    for name, x, swing in [("待机", -1.2, 0), ("走路 A", 0, 0.14), ("走路 B", 1.2, -0.14)]:
        plane(f"player_{name}_shadow", x, -4.92, 0.7, 0.16, 1.06, flat_material("soft player shadow", (0, 0, 0, 0.18)), coll)
        left_arm = plane(f"player_{name}_left_arm", x - 0.34, -4.42 + swing, 0.42, 0.35, 1.11, parts["arm"], coll)
        right_arm = plane(f"player_{name}_right_arm", x + 0.34, -4.42 - swing, 0.42, 0.35, 1.11, parts["arm"], coll)
        left_arm.rotation_euler[2] = math.radians(16 + swing * 120)
        right_arm.rotation_euler[2] = math.radians(-16 - swing * 120)
        plane(f"player_{name}_shirt", x, -4.45, 0.52, 0.58, 1.13, parts["shirt"], coll)
        left_leg = plane(f"player_{name}_left_leg", x - 0.14 - swing * 0.25, -4.9, 0.24, 0.54, 1.12, parts["leg"], coll)
        right_leg = plane(f"player_{name}_right_leg", x + 0.14 + swing * 0.25, -4.9, 0.24, 0.54, 1.12, parts["leg"], coll)
        left_leg.rotation_euler[2] = math.radians(-4 - swing * 70)
        right_leg.rotation_euler[2] = math.radians(4 + swing * 70)
        plane(f"player_{name}_pants", x, -4.68, 0.5, 0.16, 1.14, parts["pants"], coll)
        plane(f"player_{name}_face", x, -4.02, 0.42, 0.42, 1.15, parts["face"], coll)
        plane(f"player_{name}_hair", x, -3.9, 0.56, 0.42, 1.16, parts["hair"], coll)
        label(name, x, -5.22, 1.14, coll, 0.16)


def configure_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.world.color = (0.78, 0.93, 1.0)
    bpy.ops.object.camera_add(location=(0, 0, 10), rotation=(0, 0, 0))
    camera = bpy.context.object
    camera.name = "CAMERA_kenney_true_2d"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 20.8
    bpy.context.scene.camera = camera
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 6))
    bpy.context.object.name = "flat_no_shadow_sun"
    bpy.context.object.data.energy = 0.8


def render(path: Path) -> None:
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def set_labels_visible(visible: bool) -> None:
    for obj in bpy.context.scene.objects:
        if obj.name.startswith("label_"):
            obj.hide_render = not visible


def main() -> None:
    clear_scene()
    ground = collection("00_ground_tiles")
    water = collection("01_water_tiles")
    buildings = collection("02_buildings_tiles")
    details = collection("03_details_tiles")
    hotspots = collection("04_hotspots_debug")
    collisions = collection("05_collision_debug")
    character = collection("06_character_preview")

    build_ground(ground)
    build_water(water)
    build_buildings(buildings)
    build_details(details)
    build_scene_life(details)
    build_path_soft_edges(details)
    build_world_composition_polish(details)
    build_painted_terrain_pass(details)
    build_region_identity_pass(details)
    build_world_depth_pass(details)
    build_building_upgrade_pass(details)
    build_set_piece_pass(details)
    build_interaction_devices(details)
    build_center_landmark(details)
    build_occlusion(details)
    build_debug(hotspots, collisions)
    build_character(character)
    configure_scene()

    bpy.ops.wm.save_as_mainfile(filepath=str(ART_DIR / "2d-upgrade-kenney-tile-scene.blend"))

    hotspots.hide_render = True
    collisions.hide_render = True
    character.hide_render = True
    set_labels_visible(False)
    render(RENDER_DIR / "kenney-overworld-preview.png")

    hotspots.hide_render = False
    collisions.hide_render = False
    set_labels_visible(True)
    render(RENDER_DIR / "kenney-overworld-debug-hotspots-collision.png")

    for coll in [ground, water, buildings, details, hotspots, collisions]:
        coll.hide_render = True
    character.hide_render = False
    bpy.context.scene.camera.data.ortho_scale = 5.6
    bpy.context.scene.camera.location.x = 0
    bpy.context.scene.camera.location.y = -4.35
    set_labels_visible(True)
    render(RENDER_DIR / "kenney-character-action-preview.png")

    print("KENNEY_2D_SCENE", ART_DIR / "2d-upgrade-kenney-tile-scene.blend")
    print(
        "KENNEY_2D_RENDERS",
        RENDER_DIR / "kenney-overworld-preview.png",
        RENDER_DIR / "kenney-overworld-debug-hotspots-collision.png",
        RENDER_DIR / "kenney-character-action-preview.png",
    )


if __name__ == "__main__":
    main()
