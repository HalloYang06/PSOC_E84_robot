from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
ART_DIR = ROOT / "art" / "blender" / "2d-upgrade"
RENDER_DIR = ART_DIR / "renders"
ART_DIR.mkdir(parents=True, exist_ok=True)
RENDER_DIR.mkdir(parents=True, exist_ok=True)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for collection in list(bpy.data.collections):
        bpy.data.collections.remove(collection)


def collection(name: str) -> bpy.types.Collection:
    item = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(item)
    return item


def link_to(obj: bpy.types.Object, target: bpy.types.Collection) -> bpy.types.Object:
    for source in list(obj.users_collection):
        source.objects.unlink(obj)
    target.objects.link(obj)
    return obj


def material(name: str, color: tuple[float, float, float, float], roughness: float = 0.86) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = next((node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
    return mat


MATS: dict[str, bpy.types.Material] = {}


def init_materials() -> None:
    MATS.update(
        sky=material("sky blue", (0.38, 0.75, 0.96, 1)),
        cloud=material("warm cloud", (1.0, 0.94, 0.76, 1)),
        grass=material("world grass", (0.43, 0.83, 0.45, 1)),
        grass_dark=material("shadow grass", (0.25, 0.58, 0.30, 1)),
        hill=material("soft hill", (0.46, 0.74, 0.42, 1)),
        cliff=material("sun cliff", (0.67, 0.47, 0.28, 1)),
        cliff_shadow=material("cliff shadow", (0.37, 0.25, 0.16, 1)),
        path=material("gold path", (0.95, 0.74, 0.35, 1)),
        water=material("clear water", (0.34, 0.75, 0.91, 1), 0.34),
        wood=material("warm wood", (0.56, 0.34, 0.16, 1)),
        roof_red=material("strawberry roof", (0.93, 0.43, 0.44, 1)),
        roof_blue=material("workshop blue roof", (0.26, 0.56, 0.9, 1)),
        roof_green=material("green roof", (0.45, 0.76, 0.34, 1)),
        wall=material("cream wall", (1.0, 0.9, 0.62, 1)),
        glass=material("greenhouse glass", (0.64, 0.96, 0.9, 0.62), 0.24),
        gold=material("reward gold", (1.0, 0.72, 0.2, 1)),
        pink=material("soft pink", (1.0, 0.55, 0.62, 1)),
        dark=material("ink dark", (0.11, 0.16, 0.13, 1)),
        skin=material("character skin", (1.0, 0.72, 0.48, 1)),
        shirt=material("character shirt", (0.24, 0.68, 0.42, 1)),
        pants=material("character pants", (0.34, 0.48, 0.82, 1)),
        hotspot=material("hotspot translucent amber", (1.0, 0.83, 0.22, 0.32), 0.5),
        collision=material("collision translucent red", (1.0, 0.16, 0.16, 0.26), 0.5),
    )
    for key in ["glass", "hotspot", "collision"]:
        MATS[key].blend_method = "BLEND"
        MATS[key].use_nodes = True
        bsdf = next((node for node in MATS[key].node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
        if bsdf:
            bsdf.inputs["Alpha"].default_value = MATS[key].diffuse_color[3]


def assign(obj: bpy.types.Object, mat: bpy.types.Material) -> bpy.types.Object:
    obj.data.materials.append(mat)
    return obj


def cube(name: str, loc, scale, mat_key: str, coll: bpy.types.Collection) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign(obj, MATS[mat_key])
    bevel = obj.modifiers.new("soft bevel", "BEVEL")
    bevel.width = min(scale) * 0.08
    bevel.segments = 4
    obj.modifiers.new("weighted cartoon normals", "WEIGHTED_NORMAL")
    return link_to(obj, coll)


def cylinder(name: str, loc, radius: float, depth: float, mat_key: str, coll: bpy.types.Collection, vertices: int = 36) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, MATS[mat_key])
    obj.modifiers.new("weighted cartoon normals", "WEIGHTED_NORMAL")
    return link_to(obj, coll)


def sphere(name: str, loc, scale, mat_key: str, coll: bpy.types.Collection) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    assign(obj, MATS[mat_key])
    obj.modifiers.new("weighted cartoon normals", "WEIGHTED_NORMAL")
    return link_to(obj, coll)


def cone(name: str, loc, radius1: float, radius2: float, depth: float, mat_key: str, coll: bpy.types.Collection, vertices: int = 4) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius1, radius2=radius2, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, MATS[mat_key])
    obj.modifiers.new("weighted cartoon normals", "WEIGHTED_NORMAL")
    return link_to(obj, coll)


def rotate(obj: bpy.types.Object, x: float = 0, y: float = 0, z: float = 0) -> bpy.types.Object:
    obj.rotation_euler = (math.radians(x), math.radians(y), math.radians(z))
    return obj


def add_label(text: str, loc, coll: bpy.types.Collection, size: float = 0.22) -> bpy.types.Object:
    bpy.ops.object.text_add(location=loc, rotation=(math.radians(68), 0, 0))
    obj = bpy.context.object
    obj.name = f"label_{text}"
    obj.data.body = text
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    assign(obj, MATS["dark"])
    return link_to(obj, coll)


def create_world(collections: dict[str, bpy.types.Collection]) -> None:
    terrain = collections["01_terrain"]
    background = collections["00_background"]
    props = collections["03_props_foreground"]

    cube("sky_backdrop_panel", (0, 3.2, 3.4), (20, 0.12, 5.4), "sky", background)
    cube("playable_ground_blockout", (0, -0.2, -0.08), (18, 8.5, 0.16), "grass", terrain)
    cube("distant_valley_band", (0, 2.0, 0.12), (17.2, 1.3, 0.18), "hill", terrain)

    for x, y, height, width in [(-6.6, 2.35, 1.55, 1.05), (-3.9, 2.62, 2.25, 0.92), (0.4, 2.58, 2.55, 1.25), (3.8, 2.45, 2.0, 1.1), (6.3, 2.75, 2.35, 0.9)]:
        rock = cone("distant_cliff_mass", (x, y, height * 0.45), width, 0.2, height, "cliff", background, 6)
        rotate(rock, z=10)
        sphere("cliff_green_cap", (x - 0.04, y - 0.08, height * 0.9), (width * 0.42, width * 0.28, 0.16), "roof_green", background)

    bpy.ops.mesh.primitive_torus_add(major_radius=2.05, minor_radius=0.045, major_segments=96, minor_segments=12, location=(-0.2, 2.35, 1.9))
    sky_gate = bpy.context.object
    sky_gate.name = "distant_sky_gate_story_landmark"
    assign(sky_gate, MATS["cloud"])
    rotate(sky_gate, x=68)
    link_to(sky_gate, background)
    cube("sky_gate_left_support", (-2.24, 2.22, 0.9), (0.08, 0.08, 1.6), "cloud", background)
    cube("sky_gate_right_support", (1.84, 2.22, 0.9), (0.08, 0.08, 1.6), "cloud", background)

    for x, z, sx in [(-6.2, 4.5, 1.1), (-5.3, 4.15, 0.82), (4.9, 4.3, 1.0), (5.8, 4.0, 0.74)]:
        sphere("painted_cloud", (x, 1.7, z), (sx, 0.16, 0.3), "cloud", background)

    lake = cube("central_lake_surface", (0.7, -1.85, 0.02), (5.9, 1.9, 0.08), "water", terrain)
    rotate(lake, z=-2)
    river = cube("west_river_surface", (-3.8, -0.88, 0.03), (7.5, 0.42, 0.06), "water", terrain)
    rotate(river, z=-6)

    main_path = cube("main_loop_path", (-0.3, -0.44, 0.05), (9.2, 0.42, 0.06), "path", terrain)
    rotate(main_path, z=-7)
    for name, loc, scale, angle in [
        ("field_branch_path", (-3.4, -1.35, 0.06), (2.7, 0.32, 0.06), -20),
        ("market_branch_path", (3.55, -0.78, 0.06), (3.3, 0.34, 0.06), 16),
        ("dock_branch_path", (3.55, -1.72, 0.06), (2.5, 0.34, 0.06), -10),
        ("workshop_branch_path", (0.52, -0.82, 0.06), (1.6, 0.28, 0.06), 34),
    ]:
        rotate(cube(name, loc, scale, "path", terrain), z=angle)

    for x, y, s in [(-7.4, -2.2, 0.76), (-6.6, -1.35, 0.64), (5.9, -0.95, 0.72), (6.8, -1.75, 0.66), (7.4, -2.6, 0.58), (-5.7, -2.95, 0.52), (2.2, -2.95, 0.44)]:
        build_tree_cluster((x, y, 0), s, props)


def build_tree_cluster(base, scale: float, coll: bpy.types.Collection) -> None:
    bx, by, bz = base
    for x, y, size in [(-0.28, -0.04, 0.88), (0.1, 0.1, 1.0), (0.42, -0.05, 0.78)]:
        cube("tree_trunk", (bx + x * scale, by + y * scale, bz + 0.32 * scale), (0.12 * scale, 0.12 * scale, 0.58 * scale), "wood", coll)
        sphere("tree_crown", (bx + x * scale, by + y * scale, bz + 0.88 * scale), (0.34 * scale * size, 0.3 * scale * size, 0.28 * scale * size), "grass_dark", coll)
        sphere("tree_highlight", (bx + (x - 0.08) * scale, by + (y - 0.04) * scale, bz + 1.0 * scale), (0.15 * scale * size, 0.13 * scale * size, 0.1 * scale * size), "roof_green", coll)


def house(name: str, loc, scale: float, roof_key: str, coll: bpy.types.Collection) -> None:
    x, y, z = loc
    cube(f"{name}_wall", (x, y, z + 0.32 * scale), (0.88 * scale, 0.62 * scale, 0.64 * scale), "wall", coll)
    roof = cone(f"{name}_roof", (x, y, z + 0.85 * scale), 0.64 * scale, 0.13 * scale, 0.42 * scale, roof_key, coll, 4)
    rotate(roof, z=45)
    cube(f"{name}_door", (x, y - 0.33 * scale, z + 0.22 * scale), (0.22 * scale, 0.05 * scale, 0.34 * scale), "wood", coll)


def create_buildings(collections: dict[str, bpy.types.Collection]) -> None:
    buildings = collections["02_buildings_integrated"]
    labels = collections["06_design_labels"]

    cube("mailbox_post", (-3.6, -0.52, 0.36), (0.08, 0.08, 0.72), "wood", buildings)
    cube("mailbox_body", (-3.6, -0.52, 0.82), (0.52, 0.3, 0.26), "pink", buildings)
    add_label("需求信箱", (-3.6, -0.9, 0.12), labels)

    for px, py, sx, sy in [(-4.38, -1.42, 1.45, 0.86), (-3.2, -1.78, 1.26, 0.76)]:
        cube("task_field_soil_plot", (px, py, 0.08), (sx, sy, 0.08), "wood", buildings)
        cube("task_field_soil_inner", (px, py, 0.14), (sx * 0.86, sy * 0.72, 0.07), "cliff_shadow", buildings)
        for row in range(3):
            for col in range(5):
                cx = px - sx * 0.31 + col * sx * 0.155
                cy = py - sy * 0.23 + row * sy * 0.22
                cylinder("task_crop_stem", (cx, cy, 0.35), 0.022, 0.28, "grass_dark", buildings, 10)
                sphere("task_crop_bud", (cx, cy, 0.54), (0.055, 0.055, 0.055), "gold", buildings)
    add_label("任务农场", (-3.78, -2.3, 0.12), labels)

    cube("quest_board_frame", (-1.08, -0.55, 0.74), (0.86, 0.1, 0.56), "wood", buildings)
    cube("quest_board_paper_left", (-1.22, -0.62, 0.78), (0.2, 0.03, 0.24), "wall", buildings)
    cube("quest_board_paper_right", (-0.92, -0.62, 0.66), (0.18, 0.03, 0.18), "gold", buildings)
    add_label("委托公告板", (-1.08, -0.92, 0.12), labels)

    cube("workshop_wall", (0.58, -0.78, 0.48), (1.18, 0.78, 0.9), "wall", buildings)
    roof = cone("workshop_roof", (0.58, -0.78, 1.12), 0.84, 0.18, 0.48, "roof_blue", buildings, 4)
    rotate(roof, z=45)
    cube("workshop_screen", (0.58, -1.19, 0.58), (0.58, 0.05, 0.34), "water", buildings)
    cylinder("workshop_online_light", (0.08, -1.2, 0.98), 0.07, 0.04, "grass", buildings, 24)
    add_label("机械工坊", (0.58, -1.48, 0.12), labels)

    cylinder("fountain_pool", (-0.26, -1.17, 0.18), 0.42, 0.16, "water", buildings, 48)
    cylinder("fountain_pillar", (-0.26, -1.17, 0.52), 0.11, 0.44, "wall", buildings, 32)
    sphere("fountain_splash", (-0.26, -1.17, 0.82), (0.16, 0.16, 0.08), "water", buildings)
    add_label("恢复喷泉", (-0.26, -1.55, 0.12), labels)

    cube("greenhouse_base", (2.08, -1.36, 0.24), (1.22, 0.74, 0.24), "roof_green", buildings)
    arch = cylinder("greenhouse_glass_arch", (2.08, -1.36, 0.72), 0.48, 1.22, "glass", buildings, 48)
    rotate(arch, y=90)
    add_label("成果温室", (2.08, -1.84, 0.12), labels)

    cube("market_counter", (3.5, -0.82, 0.34), (1.08, 0.5, 0.34), "wood", buildings)
    cube("market_awning", (3.5, -0.82, 0.82), (1.28, 0.58, 0.1), "roof_red", buildings)
    for dx, key in [(-0.32, "grass"), (0, "gold"), (0.32, "pink")]:
        sphere("market_goods", (3.5 + dx, -1.1, 0.58), (0.09, 0.09, 0.09), key, buildings)
    add_label("订单集市", (3.5, -1.24, 0.12), labels)

    cube("dock_planks", (4.1, -2.12, 0.18), (1.42, 0.44, 0.12), "wood", buildings)
    boat = cube("delivery_boat", (4.56, -2.5, 0.28), (0.78, 0.24, 0.2), "pink", buildings)
    rotate(boat, z=-12)
    add_label("交付码头", (4.1, -2.58, 0.12), labels)

    house("blender_scene_studio", (1.18, -2.04, 0), 0.94, "roof_green", buildings)
    add_label("Blender 场景棚", (1.18, -2.54, 0.12), labels, 0.18)

    for x, y, scale, roof in [(-5.15, -2.25, 0.72, "roof_red"), (-2.0, -2.62, 0.62, "roof_red"), (5.35, -1.48, 0.64, "roof_red"), (6.45, -2.18, 0.56, "roof_red"), (-6.2, -2.9, 0.52, "roof_green"), (0.0, -2.72, 0.5, "roof_red"), (2.9, -2.74, 0.48, "roof_blue")]:
        house("background_village_house", (x, y, 0), scale, roof, buildings)


def create_hotspots_and_collisions(collections: dict[str, bpy.types.Collection]) -> None:
    hotspots = collections["04_hotspots_export"]
    collisions = collections["05_collision_export"]
    data = [
        ("mailbox", (-3.6, -0.52, 0.08), (0.85, 0.56, 0.04)),
        ("field", (-3.8, -1.62, 0.08), (2.5, 1.25, 0.04)),
        ("quest", (-1.08, -0.55, 0.08), (0.96, 0.56, 0.04)),
        ("workshop", (0.58, -0.78, 0.08), (1.36, 0.86, 0.04)),
        ("fountain", (-0.26, -1.17, 0.08), (0.8, 0.8, 0.04)),
        ("greenhouse", (2.08, -1.36, 0.08), (1.42, 0.9, 0.04)),
        ("market", (3.5, -0.82, 0.08), (1.34, 0.8, 0.04)),
        ("dock", (4.1, -2.12, 0.08), (1.6, 0.72, 0.04)),
        ("studio", (1.18, -2.04, 0.08), (1.14, 0.86, 0.04)),
    ]
    for zone_id, loc, scale in data:
        obj = cube(f"HOTSPOT__{zone_id}", loc, scale, "hotspot", hotspots)
        obj["zone_id"] = zone_id
        obj["verb"] = {
            "mailbox": "整理需求",
            "field": "培育任务",
            "quest": "接新委托",
            "workshop": "维护电脑",
            "fountain": "恢复体力",
            "greenhouse": "收获成果",
            "market": "交付订单",
            "dock": "发出成果包",
            "studio": "检查场景",
        }[zone_id]

    for name, loc, scale in [
        ("lake_blocker", (0.72, -1.86, 0.13), (5.9, 1.9, 0.08)),
        ("west_river_blocker", (-3.8, -0.88, 0.13), (7.5, 0.42, 0.08)),
        ("cliff_wall_left", (-6.8, 1.45, 0.16), (1.6, 1.6, 0.08)),
        ("cliff_wall_mid", (0.4, 2.0, 0.16), (2.0, 1.4, 0.08)),
        ("cliff_wall_right", (5.0, 1.85, 0.16), (2.4, 1.4, 0.08)),
    ]:
        obj = cube(f"COLLISION__{name}", loc, scale, "collision", collisions)
        obj["collision"] = True


def create_character(collections: dict[str, bpy.types.Collection]) -> None:
    chars = collections["07_character_animation"]
    frame_locs = [(-0.7, -3.85, 0), (0, -3.85, 0), (0.7, -3.85, 0)]
    frame_names = ["idle", "walk_a", "walk_b"]
    for index, (loc, frame_name) in enumerate(zip(frame_locs, frame_names)):
        x, y, z = loc
        sphere(f"player_{frame_name}_head", (x, y, z + 1.22), (0.18, 0.18, 0.18), "skin", chars)
        cone(f"player_{frame_name}_hat", (x, y, z + 1.48), 0.24, 0.1, 0.2, "gold", chars, 32)
        cube(f"player_{frame_name}_body", (x, y, z + 0.78), (0.28, 0.2, 0.44), "shirt", chars)
        arm_offset = 0.08 if frame_name == "walk_a" else -0.08 if frame_name == "walk_b" else 0
        leg_offset = -arm_offset
        left_arm = cube(f"player_{frame_name}_left_arm", (x - 0.22, y, z + 0.78), (0.08, 0.08, 0.38), "skin", chars)
        right_arm = cube(f"player_{frame_name}_right_arm", (x + 0.22, y, z + 0.78), (0.08, 0.08, 0.38), "skin", chars)
        left_leg = cube(f"player_{frame_name}_left_leg", (x - 0.08, y, z + 0.42), (0.1, 0.1, 0.4), "pants", chars)
        right_leg = cube(f"player_{frame_name}_right_leg", (x + 0.08, y, z + 0.42), (0.1, 0.1, 0.4), "pants", chars)
        rotate(left_arm, z=arm_offset * 90)
        rotate(right_arm, z=-arm_offset * 90)
        rotate(left_leg, z=leg_offset * 100)
        rotate(right_leg, z=-leg_offset * 100)
        add_label(frame_name, (x, y - 0.38, z + 0.1), chars, 0.13)
        for obj in bpy.context.scene.objects:
            if obj.name.startswith(f"player_{frame_name}_"):
                obj["animation_frame"] = frame_name
                obj["frame_index"] = index


def setup_lighting_and_camera() -> None:
    bpy.ops.object.light_add(type="SUN", location=(0, -5, 8))
    sun = bpy.context.object
    sun.name = "GAME_SUN_warm_key"
    sun.data.energy = 2.7
    sun.rotation_euler = (math.radians(44), 0, math.radians(-30))

    bpy.ops.object.light_add(type="AREA", location=(0, -4, 7))
    fill = bpy.context.object
    fill.name = "GAME_SKY_soft_fill"
    fill.data.energy = 420
    fill.data.size = 10

    bpy.ops.object.camera_add(location=(0, -8.8, 5.1))
    camera = bpy.context.object
    camera.name = "CAMERA_game_export_2_5d"
    direction = Vector((0, -0.95, 1.0)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 9.8
    bpy.context.scene.camera = camera


def setup_character_camera() -> None:
    bpy.ops.object.camera_add(location=(0, -6.9, 2.85))
    camera = bpy.context.object
    camera.name = "CAMERA_character_action_sheet"
    direction = Vector((0, -3.85, 0.8)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 3.0
    bpy.context.scene.camera = camera


def configure_render() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 96
    if hasattr(scene.eevee, "use_gtao"):
        scene.eevee.use_gtao = True
    if hasattr(scene.eevee, "gtao_distance"):
        scene.eevee.gtao_distance = 3
    if hasattr(scene.eevee, "gtao_factor"):
        scene.eevee.gtao_factor = 1.2
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.world.color = (0.44, 0.72, 0.92)


def set_collection_visibility(collections: dict[str, bpy.types.Collection], *, debug: bool, character: bool) -> None:
    collections["04_hotspots_export"].hide_render = not debug
    collections["05_collision_export"].hide_render = not debug
    collections["06_design_labels"].hide_render = not debug
    collections["07_character_animation"].hide_render = not character


def set_world_visibility(collections: dict[str, bpy.types.Collection], visible: bool) -> None:
    for name in [
        "00_background",
        "01_terrain",
        "02_buildings_integrated",
        "03_props_foreground",
        "04_hotspots_export",
        "05_collision_export",
        "06_design_labels",
    ]:
        collections[name].hide_render = not visible


def render(path: Path) -> None:
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    clear_scene()
    init_materials()
    collections = {
        name: collection(name)
        for name in [
            "00_background",
            "01_terrain",
            "02_buildings_integrated",
            "03_props_foreground",
            "04_hotspots_export",
            "05_collision_export",
            "06_design_labels",
            "07_character_animation",
        ]
    }
    create_world(collections)
    create_buildings(collections)
    create_hotspots_and_collisions(collections)
    create_character(collections)
    setup_lighting_and_camera()
    configure_render()

    bpy.ops.wm.save_as_mainfile(filepath=str(ART_DIR / "2d-upgrade-world-dev.blend"))
    set_collection_visibility(collections, debug=False, character=False)
    render(RENDER_DIR / "overworld-preview.png")
    set_collection_visibility(collections, debug=True, character=False)
    render(RENDER_DIR / "overworld-debug-hotspots-collision.png")
    set_world_visibility(collections, visible=False)
    collections["07_character_animation"].hide_render = False
    setup_character_camera()
    render(RENDER_DIR / "character-action-preview.png")
    print("BLENDER_2D_DEV_SCENE", ART_DIR / "2d-upgrade-world-dev.blend")
    print(
        "BLENDER_2D_DEV_RENDERS",
        RENDER_DIR / "overworld-preview.png",
        RENDER_DIR / "overworld-debug-hotspots-collision.png",
        RENDER_DIR / "character-action-preview.png",
    )


if __name__ == "__main__":
    main()
