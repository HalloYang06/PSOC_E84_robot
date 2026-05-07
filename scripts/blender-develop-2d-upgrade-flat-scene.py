from __future__ import annotations

import math
from pathlib import Path

import bpy

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
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll


def link_to(obj: bpy.types.Object, coll: bpy.types.Collection) -> bpy.types.Object:
    for source in list(obj.users_collection):
        source.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def mat(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    nodes = material.node_tree.nodes
    bsdf = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 1
    return material


MATS: dict[str, bpy.types.Material] = {}


def init_materials() -> None:
    MATS.update(
        sky=mat("flat sky blue", (0.47, 0.78, 0.95, 1)),
        far_blue=mat("distant blue hills", (0.44, 0.67, 0.79, 1)),
        far_green=mat("distant green hills", (0.55, 0.76, 0.55, 1)),
        grass=mat("soft grass", (0.55, 0.83, 0.43, 1)),
        grass_light=mat("sun grass", (0.68, 0.91, 0.52, 1)),
        grass_dark=mat("shadow grass", (0.34, 0.67, 0.36, 1)),
        path=mat("warm walking path", (0.93, 0.78, 0.42, 1)),
        path_shadow=mat("path shadow", (0.76, 0.58, 0.28, 1)),
        water=mat("clean water", (0.31, 0.76, 0.92, 1)),
        water_light=mat("water light", (0.63, 0.94, 1.0, 1)),
        cream=mat("building cream", (1.0, 0.9, 0.62, 1)),
        wall_shadow=mat("building soft shadow", (0.77, 0.64, 0.42, 1)),
        roof_red=mat("berry roof", (0.95, 0.42, 0.48, 1)),
        roof_blue=mat("blue roof", (0.22, 0.55, 0.88, 1)),
        roof_green=mat("green roof", (0.38, 0.76, 0.39, 1)),
        wood=mat("wood", (0.59, 0.36, 0.18, 1)),
        soil=mat("soft soil", (0.55, 0.36, 0.2, 1)),
        gold=mat("gold detail", (1.0, 0.74, 0.22, 1)),
        pink=mat("pink accent", (1.0, 0.58, 0.68, 1)),
        white=mat("warm white", (1.0, 0.96, 0.78, 1)),
        outline=mat("ink outline", (0.17, 0.28, 0.24, 1)),
        hotspot=mat("debug hotspot", (1.0, 0.28, 0.24, 0.32)),
        collision=mat("debug collision", (0.58, 0.12, 0.9, 0.28)),
        skin=mat("skin flat", (1.0, 0.72, 0.5, 1)),
        shirt=mat("shirt flat", (0.28, 0.72, 0.46, 1)),
        pants=mat("pants flat", (0.38, 0.52, 0.86, 1)),
        hair=mat("hair flat", (0.33, 0.2, 0.12, 1)),
    )
    for key in ["hotspot", "collision"]:
        MATS[key].blend_method = "BLEND"


def assign(obj: bpy.types.Object, material_key: str) -> bpy.types.Object:
    obj.data.materials.append(MATS[material_key])
    return obj


def poly(name: str, points: list[tuple[float, float]], z: float, material_key: str, coll: bpy.types.Collection) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(x, y, z) for x, y in points], [], [list(range(len(points)))])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    assign(obj, material_key)
    return link_to(obj, coll)


def rect(name: str, x: float, y: float, w: float, h: float, z: float, material_key: str, coll: bpy.types.Collection) -> bpy.types.Object:
    return poly(name, [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2), (x - w / 2, y + h / 2)], z, material_key, coll)


def ellipse(name: str, x: float, y: float, rx: float, ry: float, z: float, material_key: str, coll: bpy.types.Collection, segments: int = 72) -> bpy.types.Object:
    points = [(x + math.cos(i / segments * math.tau) * rx, y + math.sin(i / segments * math.tau) * ry) for i in range(segments)]
    return poly(name, points, z, material_key, coll)


def path_ribbon(name: str, points: list[tuple[float, float]], width: float, z: float, material_key: str, coll: bpy.types.Collection) -> None:
    for index, (a, b) in enumerate(zip(points, points[1:])):
        ax, ay = a
        bx, by = b
        mx = (ax + bx) / 2
        my = (ay + by) / 2
        length = math.hypot(bx - ax, by - ay)
        obj = rect(f"{name}_{index}", mx, my, length, width, z, material_key, coll)
        obj.rotation_euler[2] = math.atan2(by - ay, bx - ax)
    for index, (x, y) in enumerate(points):
        ellipse(f"{name}_cap_{index}", x, y, width / 2, width / 2, z + 0.001, material_key, coll, 36)


def add_label(text: str, x: float, y: float, z: float, coll: bpy.types.Collection, size: float = 0.22) -> None:
    bpy.ops.object.text_add(location=(x, y, z), rotation=(0, 0, 0))
    obj = bpy.context.object
    obj.name = f"label_{text}"
    obj.data.body = text
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    assign(obj, "outline")
    link_to(obj, coll)


def house(name: str, x: float, y: float, scale: float, roof_key: str, coll: bpy.types.Collection) -> None:
    ellipse(f"{name}_shadow", x + 0.08 * scale, y - 0.08 * scale, 0.52 * scale, 0.22 * scale, 0.12, "path_shadow", coll, 42)
    rect(f"{name}_body", x, y, 0.78 * scale, 0.58 * scale, 0.2, "cream", coll)
    rect(f"{name}_body_bottom_shadow", x, y - 0.2 * scale, 0.78 * scale, 0.16 * scale, 0.21, "wall_shadow", coll)
    poly(
        f"{name}_roof",
        [
            (x - 0.48 * scale, y + 0.22 * scale),
            (x, y + 0.55 * scale),
            (x + 0.48 * scale, y + 0.22 * scale),
            (x + 0.34 * scale, y - 0.05 * scale),
            (x - 0.34 * scale, y - 0.05 * scale),
        ],
        0.32,
        roof_key,
        coll,
    )
    rect(f"{name}_door", x, y - 0.24 * scale, 0.18 * scale, 0.28 * scale, 0.34, "wood", coll)


def create_world(collections: dict[str, bpy.types.Collection]) -> None:
    bg = collections["00_background_2d"]
    terrain = collections["01_terrain_2d"]
    buildings = collections["02_buildings_2d"]
    details = collections["03_details_2d"]

    rect("sky_band", 0, 3.45, 16.8, 2.1, 0, "sky", bg)
    poly("far_hills_blue", [(-8.4, 2.5), (-6.2, 3.35), (-4.1, 2.62), (-2.5, 3.4), (-0.8, 2.64), (1.1, 3.38), (3.6, 2.52), (5.6, 3.28), (8.4, 2.56), (8.4, 1.88), (-8.4, 1.88)], 0.04, "far_blue", bg)
    poly("far_hills_green", [(-8.4, 1.98), (-6.6, 2.55), (-4.6, 2.15), (-2.1, 2.72), (0.0, 2.18), (2.5, 2.62), (4.6, 2.08), (6.8, 2.62), (8.4, 2.18), (8.4, 1.55), (-8.4, 1.55)], 0.06, "far_green", bg)
    rect("play_field", 0, -0.45, 16.8, 6.2, 0.08, "grass", terrain)
    poly("sunlit_meadow_patch", [(-8.4, 1.2), (-4.8, 1.45), (-1.6, 1.08), (1.5, 1.42), (5.2, 1.05), (8.4, 1.28), (8.4, -0.1), (-8.4, 0.05)], 0.09, "grass_light", terrain)
    poly("foreground_grass_band", [(-8.4, -3.55), (8.4, -3.55), (8.4, -2.45), (4.4, -2.25), (1.4, -2.48), (-1.4, -2.22), (-4.2, -2.48), (-8.4, -2.24)], 0.5, "grass_light", terrain)

    path_ribbon("main_path", [(-7.2, -0.42), (-4.8, -0.18), (-2.6, -0.28), (-0.4, -0.55), (1.8, -0.48), (4.0, -0.25), (7.2, -0.42)], 0.35, 0.2, "path", terrain)
    path_ribbon("field_path", [(-5.3, -0.28), (-5.85, -1.0), (-6.25, -1.62)], 0.28, 0.19, "path", terrain)
    path_ribbon("dock_path", [(2.8, -0.5), (3.6, -1.18), (4.8, -1.78)], 0.27, 0.19, "path", terrain)
    path_ribbon("studio_path", [(0.2, -0.55), (0.85, -1.18), (1.2, -1.92)], 0.24, 0.19, "path", terrain)

    poly("lake", [(-2.2, -1.15), (-0.4, -1.0), (1.0, -1.25), (2.7, -1.1), (4.8, -1.52), (5.55, -2.15), (4.1, -2.65), (1.4, -2.7), (-1.8, -2.55), (-4.7, -2.42), (-5.45, -1.92), (-4.25, -1.35)], 0.18, "water", terrain)
    path_ribbon("river", [(-8.2, -1.05), (-6.5, -1.18), (-5.0, -1.28), (-3.6, -1.35), (-2.2, -1.15)], 0.42, 0.19, "water", terrain)
    for x in [-1.2, 0.7, 2.5, 4.1]:
        ellipse("water_glint", x, -1.85 + (x % 0.4), 0.38, 0.035, 0.23, "water_light", terrain, 28)

    bpy.ops.mesh.primitive_torus_add(major_radius=1.25, minor_radius=0.025, major_segments=96, minor_segments=8, location=(0.0, 2.48, 0.2))
    gate = bpy.context.object
    gate.name = "flat_story_gate"
    gate.scale.y = 0.1
    assign(gate, "white")
    link_to(gate, bg)

    for cx, cy, s in [(-6.9, 2.65, 0.72), (-3.5, 2.72, 0.66), (3.5, 2.66, 0.7), (6.6, 2.82, 0.6)]:
        ellipse("round_cloud_a", cx, cy, 0.42 * s, 0.16 * s, 0.3, "white", bg, 40)
        ellipse("round_cloud_b", cx + 0.38 * s, cy - 0.04 * s, 0.36 * s, 0.14 * s, 0.31, "white", bg, 40)

    house("mail_house", -4.2, 0.0, 0.82, "roof_red", buildings)
    rect("mailbox_post", -5.25, -0.08, 0.08, 0.48, 0.45, "wood", details)
    rect("mailbox_box", -5.25, 0.25, 0.56, 0.28, 0.48, "pink", details)

    for px, py, sx, sy in [(-6.4, -1.46, 1.2, 0.72), (-5.25, -1.65, 1.04, 0.62)]:
        rect("field_soil", px, py, sx, sy, 0.35, "soil", buildings)
        for row in range(3):
            for col in range(5):
                cx = px - sx * 0.36 + col * sx * 0.18
                cy = py - sy * 0.28 + row * sy * 0.24
                rect("crop_stem", cx, cy, 0.035, 0.22, 0.5, "grass_dark", details)
                ellipse("crop_bud", cx, cy + 0.12, 0.07, 0.07, 0.52, "gold", details, 22)

    rect("quest_board", -1.25, 0.08, 1.0, 0.55, 0.44, "wood", buildings)
    rect("quest_paper_a", -1.45, 0.15, 0.22, 0.28, 0.48, "white", details)
    rect("quest_paper_b", -1.1, 0.0, 0.2, 0.22, 0.49, "gold", details)

    house("workshop", 0.8, -0.25, 1.12, "roof_blue", buildings)
    rect("workshop_screen", 0.8, -0.43, 0.52, 0.24, 0.52, "water", details)
    ellipse("fountain_pool", -0.35, -0.5, 0.58, 0.26, 0.46, "water", details, 48)
    ellipse("fountain_top", -0.35, -0.28, 0.22, 0.11, 0.54, "water_light", details, 36)

    rect("greenhouse_body", 2.55, -0.55, 1.12, 0.78, 0.36, "glass", buildings)
    rect("greenhouse_base", 2.55, -0.98, 1.2, 0.18, 0.38, "roof_green", buildings)
    house("studio", 1.15, -1.75, 0.86, "roof_green", buildings)

    rect("market_counter", 5.25, -0.22, 1.24, 0.44, 0.43, "wood", buildings)
    rect("market_awning", 5.25, 0.08, 1.42, 0.24, 0.52, "roof_red", details)
    for dx, key in [(-0.34, "grass_light"), (0, "gold"), (0.34, "pink")]:
        ellipse("market_goods", 5.25 + dx, -0.12, 0.1, 0.1, 0.58, key, details, 22)

    rect("dock", 4.82, -2.0, 1.42, 0.32, 0.44, "wood", details)
    poly("boat", [(5.22, -2.23), (5.78, -2.12), (5.96, -2.28), (5.56, -2.42), (5.1, -2.36)], 0.5, "pink", details)

    for x, y, s, roof in [(-7.0, -2.4, 0.55, "roof_red"), (-3.25, -2.52, 0.5, "roof_green"), (-0.2, -2.46, 0.46, "roof_red"), (3.0, -2.38, 0.48, "roof_blue"), (6.4, -1.7, 0.48, "roof_red")]:
        house("foreground_house", x, y, s, roof, buildings)

    for x, y, s in [(-7.6, -0.5, 0.55), (-6.8, -2.85, 0.48), (3.2, -2.75, 0.44), (6.8, -2.15, 0.5), (7.3, 0.55, 0.5)]:
        tree(x, y, s, details)


def tree(x: float, y: float, scale: float, coll: bpy.types.Collection) -> None:
    rect("tree_trunk", x, y - 0.15 * scale, 0.12 * scale, 0.38 * scale, 0.62, "wood", coll)
    ellipse("tree_crown_a", x - 0.16 * scale, y + 0.08 * scale, 0.24 * scale, 0.2 * scale, 0.66, "grass_dark", coll, 30)
    ellipse("tree_crown_b", x + 0.12 * scale, y + 0.1 * scale, 0.24 * scale, 0.2 * scale, 0.67, "grass_dark", coll, 30)
    ellipse("tree_crown_c", x, y + 0.25 * scale, 0.26 * scale, 0.2 * scale, 0.68, "grass_light", coll, 30)


def create_hotspots(collections: dict[str, bpy.types.Collection]) -> None:
    hot = collections["04_hotspots_debug"]
    col = collections["05_collision_debug"]
    zones = [
        ("需求信箱", -5.25, 0.08, 0.95, 0.72),
        ("任务农场", -5.9, -1.56, 2.4, 1.0),
        ("委托公告板", -1.25, 0.08, 1.15, 0.72),
        ("机械工坊", 0.8, -0.25, 1.28, 0.96),
        ("恢复喷泉", -0.35, -0.5, 1.0, 0.7),
        ("成果温室", 2.55, -0.65, 1.3, 0.98),
        ("订单集市", 5.25, -0.1, 1.55, 0.88),
        ("交付码头", 5.15, -2.05, 1.65, 0.65),
        ("Blender 场景棚", 1.15, -1.75, 1.0, 0.78),
    ]
    for label, x, y, w, h in zones:
        rect(f"HOTSPOT__{label}", x, y, w, h, 0.9, "hotspot", hot)
        add_label(label, x, y, 0.92, hot, 0.22)
    for label, x, y, w, h in [
        ("水域碰撞", 0.15, -1.9, 10.2, 1.18),
        ("远景不可达", 0, 2.1, 16.8, 0.95),
    ]:
        rect(f"COLLISION__{label}", x, y, w, h, 0.88, "collision", col)
        add_label(label, x, y, 0.93, col, 0.2)


def create_character(collections: dict[str, bpy.types.Collection]) -> None:
    chars = collections["06_character_2d"]
    for index, (name, x) in enumerate([("idle", -1.2), ("walk_a", 0), ("walk_b", 1.2)]):
        y = -4.35
        ellipse(f"player_{name}_shadow", x, y - 0.48, 0.3, 0.08, 0.8, "path_shadow", chars, 32)
        ellipse(f"player_{name}_head", x, y + 0.38, 0.18, 0.22, 0.86, "skin", chars, 36)
        poly(f"player_{name}_hair", [(x - 0.2, y + 0.52), (x, y + 0.72), (x + 0.2, y + 0.52), (x + 0.14, y + 0.42), (x - 0.14, y + 0.42)], 0.88, "hair", chars)
        rect(f"player_{name}_body", x, y - 0.05, 0.36, 0.48, 0.84, "shirt", chars)
        arm_shift = 0.08 if name == "walk_a" else -0.08 if name == "walk_b" else 0
        leg_shift = -arm_shift
        rect(f"player_{name}_left_arm", x - 0.27, y - arm_shift, 0.09, 0.42, 0.83, "skin", chars)
        rect(f"player_{name}_right_arm", x + 0.27, y + arm_shift, 0.09, 0.42, 0.83, "skin", chars)
        rect(f"player_{name}_left_leg", x - 0.1 + leg_shift, y - 0.46, 0.11, 0.42, 0.82, "pants", chars)
        rect(f"player_{name}_right_leg", x + 0.1 - leg_shift, y - 0.46, 0.11, 0.42, 0.82, "pants", chars)
        add_label(name, x, y - 0.88, 0.9, chars, 0.22)


def configure_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.world.color = (0.47, 0.78, 0.95)

    bpy.ops.object.light_add(type="SUN", location=(0, 0, 5))
    sun = bpy.context.object
    sun.name = "flat_scene_soft_sun"
    sun.data.energy = 1.0

    bpy.ops.object.camera_add(location=(0, 0, 10), rotation=(0, 0, 0))
    camera = bpy.context.object
    camera.name = "CAMERA_true_2d_orthographic"
    camera.rotation_euler = (0, 0, 0)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 7.2
    bpy.context.scene.camera = camera


def set_debug(collections: dict[str, bpy.types.Collection], debug: bool) -> None:
    collections["04_hotspots_debug"].hide_render = not debug
    collections["05_collision_debug"].hide_render = not debug
    collections["06_character_2d"].hide_render = True


def render(path: Path) -> None:
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main() -> None:
    clear_scene()
    init_materials()
    collections = {
        name: collection(name)
        for name in [
            "00_background_2d",
            "01_terrain_2d",
            "02_buildings_2d",
            "03_details_2d",
            "04_hotspots_debug",
            "05_collision_debug",
            "06_character_2d",
        ]
    }
    create_world(collections)
    create_hotspots(collections)
    create_character(collections)
    configure_scene()

    bpy.ops.wm.save_as_mainfile(filepath=str(ART_DIR / "2d-upgrade-world-flat-dev.blend"))

    set_debug(collections, debug=False)
    render(RENDER_DIR / "flat-overworld-preview.png")

    set_debug(collections, debug=True)
    render(RENDER_DIR / "flat-overworld-debug-hotspots-collision.png")

    for name in ["00_background_2d", "01_terrain_2d", "02_buildings_2d", "03_details_2d", "04_hotspots_debug", "05_collision_debug"]:
        collections[name].hide_render = True
    collections["06_character_2d"].hide_render = False
    bpy.context.scene.camera.data.ortho_scale = 2.1
    render(RENDER_DIR / "flat-character-action-preview.png")

    print("BLENDER_TRUE_2D_SCENE", ART_DIR / "2d-upgrade-world-flat-dev.blend")
    print(
        "BLENDER_TRUE_2D_RENDERS",
        RENDER_DIR / "flat-overworld-preview.png",
        RENDER_DIR / "flat-overworld-debug-hotspots-collision.png",
        RENDER_DIR / "flat-character-action-preview.png",
    )


if __name__ == "__main__":
    main()
