from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "apps" / "web" / "public" / "assets" / "2d-dev-upgrade"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def mat(name: str, color: tuple[float, float, float, float], roughness: float = 0.82):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        return material
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return material


MATS = {
    "leaf": mat("leaf", (0.28, 0.76, 0.34, 1)),
    "leaf_dark": mat("leaf_dark", (0.16, 0.48, 0.22, 1)),
    "soil": mat("soil", (0.55, 0.33, 0.18, 1)),
    "wood": mat("wood", (0.62, 0.38, 0.17, 1)),
    "cream": mat("cream", (1.0, 0.92, 0.62, 1)),
    "gold": mat("gold", (1.0, 0.72, 0.22, 1)),
    "rose": mat("rose", (1.0, 0.45, 0.43, 1)),
    "pink": mat("pink", (1.0, 0.68, 0.78, 1)),
    "blue": mat("blue", (0.34, 0.72, 1.0, 1)),
    "glass": mat("glass", (0.62, 0.96, 0.9, 0.72), 0.2),
    "green_roof": mat("green_roof", (0.47, 0.78, 0.34, 1)),
    "skin": mat("skin", (1.0, 0.72, 0.48, 1)),
    "shirt": mat("shirt", (0.24, 0.68, 0.42, 1)),
    "pants": mat("pants", (0.34, 0.48, 0.82, 1)),
    "dark": mat("dark", (0.12, 0.18, 0.13, 1)),
}


def assign(obj, material):
    obj.data.materials.append(material)
    return obj


def cube(name: str, loc, scale, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign(obj, material)
    bevel = obj.modifiers.new("soft bevel", "BEVEL")
    bevel.width = min(scale) * 0.12
    bevel.segments = 4
    obj.modifiers.new("cartoon shade", "WEIGHTED_NORMAL")
    return obj


def sphere(name: str, loc, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    assign(obj, material)
    obj.modifiers.new("cartoon shade", "WEIGHTED_NORMAL")
    return obj


def cylinder(name: str, loc, radius: float, depth: float, material, vertices: int = 32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, material)
    obj.modifiers.new("cartoon shade", "WEIGHTED_NORMAL")
    return obj


def cone(name: str, loc, radius1: float, radius2: float, depth: float, material, vertices: int = 32):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius1, radius2=radius2, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, material)
    obj.modifiers.new("cartoon shade", "WEIGHTED_NORMAL")
    return obj


def rotate(obj, x=0, y=0, z=0):
    obj.rotation_euler = (math.radians(x), math.radians(y), math.radians(z))
    return obj


def setup_camera() -> None:
    bpy.ops.object.light_add(type="AREA", location=(0, -4, 6))
    light = bpy.context.object
    light.name = "softbox"
    light.data.energy = 450
    light.data.size = 5
    bpy.ops.object.camera_add(location=(4.8, -7.4, 5.2), rotation=(math.radians(60), 0, math.radians(38)))
    camera = bpy.context.object
    direction = Vector((0, 0, 0.6)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 4.8
    bpy.context.scene.camera = camera


def setup_panorama_camera() -> None:
    bpy.ops.object.light_add(type="SUN", location=(0, -6, 8))
    sun = bpy.context.object
    sun.name = "warm sun"
    sun.data.energy = 2.3
    sun.rotation_euler = (math.radians(42), 0, math.radians(-28))
    bpy.ops.object.light_add(type="AREA", location=(0, -4, 7))
    fill = bpy.context.object
    fill.name = "sky fill"
    fill.data.energy = 360
    fill.data.size = 10
    bpy.ops.object.camera_add(location=(0, -9.8, 4.2), rotation=(math.radians(68), 0, 0))
    camera = bpy.context.object
    direction = Vector((0, 0, 1.2)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = 22
    bpy.context.scene.camera = camera


def configure_render() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 64
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.world.color = (0.78, 0.9, 1.0)


def configure_panorama_render() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 96
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 940
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.world.color = (0.42, 0.78, 0.96)


def render_asset(name: str, builder) -> None:
    clear_scene()
    setup_camera()
    builder()
    configure_render()
    bpy.context.scene.render.filepath = str(OUTPUT_DIR / f"{name}.png")
    bpy.ops.render.render(write_still=True)


def render_panorama(name: str, builder) -> None:
    clear_scene()
    setup_panorama_camera()
    builder()
    configure_panorama_render()
    bpy.context.scene.render.filepath = str(OUTPUT_DIR / f"{name}.png")
    bpy.ops.render.render(write_still=True)


def build_avatar() -> None:
    sphere("head", (0, 0, 1.8), (0.42, 0.42, 0.42), MATS["skin"])
    sphere("hair", (-0.08, 0.03, 2.08), (0.46, 0.42, 0.22), MATS["wood"])
    cube("body", (0, 0, 1.05), (0.62, 0.42, 0.72), MATS["shirt"])
    cube("left_leg", (-0.18, 0, 0.48), (0.22, 0.22, 0.62), MATS["pants"])
    cube("right_leg", (0.18, 0, 0.48), (0.22, 0.22, 0.62), MATS["pants"])
    cube("left_arm", (-0.48, -0.02, 1.1), (0.18, 0.18, 0.62), MATS["skin"])
    cube("right_arm", (0.48, -0.02, 1.1), (0.18, 0.18, 0.62), MATS["skin"])
    brim = cube("hat_brim", (0, 0, 2.24), (0.94, 0.62, 0.08), MATS["gold"])
    rotate(brim, z=-4)
    cone("hat_top", (0, 0, 2.43), 0.34, 0.18, 0.34, MATS["gold"])
    handle = cube("tool_handle", (-0.76, -0.06, 0.92), (0.06, 0.06, 1.0), MATS["wood"])
    rotate(handle, z=-28)
    blade = cube("tool_blade", (-0.96, -0.06, 0.42), (0.38, 0.08, 0.14), MATS["dark"])
    rotate(blade, z=-28)


def build_avatar_walk_a() -> None:
    sphere("head", (0, 0, 1.8), (0.42, 0.42, 0.42), MATS["skin"])
    sphere("hair", (-0.08, 0.03, 2.08), (0.46, 0.42, 0.22), MATS["wood"])
    cube("body", (0, 0, 1.05), (0.62, 0.42, 0.72), MATS["shirt"])
    left_leg = cube("left_leg", (-0.22, 0, 0.5), (0.22, 0.22, 0.64), MATS["pants"])
    right_leg = cube("right_leg", (0.22, 0, 0.5), (0.22, 0.22, 0.64), MATS["pants"])
    rotate(left_leg, x=-10, z=9)
    rotate(right_leg, x=10, z=-10)
    left_arm = cube("left_arm", (-0.5, -0.02, 1.12), (0.18, 0.18, 0.62), MATS["skin"])
    right_arm = cube("right_arm", (0.5, -0.02, 1.12), (0.18, 0.18, 0.62), MATS["skin"])
    rotate(left_arm, x=12, z=-16)
    rotate(right_arm, x=-12, z=16)
    brim = cube("hat_brim", (0, 0, 2.24), (0.94, 0.62, 0.08), MATS["gold"])
    rotate(brim, z=-8)
    cone("hat_top", (0, 0, 2.43), 0.34, 0.18, 0.34, MATS["gold"])


def build_avatar_walk_b() -> None:
    build_avatar_walk_a()
    for obj in bpy.context.scene.objects:
        if "left_leg" in obj.name or "right_arm" in obj.name:
            obj.rotation_euler.z *= -1
        if "right_leg" in obj.name or "left_arm" in obj.name:
            obj.rotation_euler.z *= -1


def build_task_field() -> None:
    cube("field_base", (0, 0, 0.18), (2.4, 1.7, 0.34), MATS["soil"])
    for row in range(3):
        for col in range(4):
            x = -0.78 + col * 0.52
            y = -0.48 + row * 0.48
            cylinder("stem", (x, y, 0.56), 0.035, 0.42, MATS["leaf_dark"], 12)
            leaf_a = sphere("leaf", (x - 0.08, y, 0.72), (0.16, 0.07, 0.07), MATS["leaf"])
            rotate(leaf_a, z=28)
            leaf_b = sphere("leaf", (x + 0.08, y, 0.77), (0.16, 0.07, 0.07), MATS["leaf"])
            rotate(leaf_b, z=-28)
            sphere("bud", (x, y, 0.93), (0.08, 0.08, 0.08), MATS["gold"])


def build_mailbox() -> None:
    cube("post", (0, 0, 0.55), (0.22, 0.22, 1.1), MATS["wood"])
    cube("box", (0, 0, 1.42), (1.35, 0.8, 0.64), MATS["rose"])
    cyl = cylinder("rounded_top", (0, 0, 1.76), 0.4, 1.35, MATS["rose"])
    rotate(cyl, y=90)
    cube("door", (-0.7, 0, 1.42), (0.08, 0.74, 0.56), MATS["pink"])
    cube("flag", (0.62, -0.45, 1.86), (0.08, 0.36, 0.28), MATS["gold"])
    cube("flag_pole", (0.62, -0.45, 1.55), (0.06, 0.06, 0.74), MATS["wood"])


def build_workshop() -> None:
    cube("house", (0, 0, 0.88), (1.7, 1.2, 1.2), MATS["gold"])
    roof = cone("roof", (0, 0, 1.7), 1.25, 0.24, 0.7, MATS["blue"], 4)
    rotate(roof, z=45)
    cube("screen", (0, -0.62, 1.0), (0.92, 0.08, 0.52), MATS["cream"])
    cube("screen_glow", (0, -0.67, 1.02), (0.68, 0.04, 0.28), MATS["blue"])
    cylinder("online_light", (-0.68, -0.62, 1.42), 0.11, 0.08, MATS["leaf"], 24)
    cylinder("alert_light", (0.68, -0.62, 1.42), 0.11, 0.08, MATS["rose"], 24)


def build_greenhouse() -> None:
    cube("base", (0, 0, 0.35), (2.0, 1.2, 0.32), MATS["green_roof"])
    arch = cylinder("glass_arch", (0, 0, 1.0), 0.78, 2.0, MATS["glass"], 48)
    rotate(arch, y=90)
    cube("door", (0, -0.62, 0.8), (0.5, 0.08, 0.9), MATS["cream"])
    for x in [-0.7, 0, 0.7]:
        cylinder("plant", (x, -0.2, 0.78), 0.04, 0.45, MATS["leaf_dark"], 12)
        sphere("plant_top", (x, -0.2, 1.05), (0.16, 0.16, 0.1), MATS["leaf"])


def build_art_studio() -> None:
    cube("studio", (0, 0, 0.85), (1.65, 1.14, 1.18), MATS["pink"])
    roof = cone("roof", (0, 0, 1.66), 1.18, 0.22, 0.64, MATS["green_roof"], 4)
    rotate(roof, z=45)
    cube("canvas", (-0.38, -0.62, 0.95), (0.55, 0.08, 0.62), MATS["cream"])
    sphere("paint_yellow", (-0.45, -0.68, 1.02), (0.09, 0.04, 0.09), MATS["gold"])
    sphere("paint_blue", (-0.25, -0.68, 0.86), (0.08, 0.04, 0.08), MATS["blue"])
    brush = cube("brush", (0.48, -0.66, 0.8), (0.08, 0.08, 0.78), MATS["wood"])
    rotate(brush, z=-26)
    sphere("brush_tip", (0.65, -0.7, 1.12), (0.12, 0.05, 0.08), MATS["rose"])


def build_seed_bag() -> None:
    cube("bag", (0, 0, 0.82), (1.1, 0.78, 1.25), MATS["cream"])
    cube("bag_fold", (0, -0.05, 1.56), (0.95, 0.7, 0.2), MATS["gold"])
    sphere("badge", (0, -0.42, 0.95), (0.28, 0.08, 0.28), MATS["leaf"])
    for x in [-0.24, 0, 0.24]:
        sphere("seed", (x, -0.48, 0.55), (0.07, 0.04, 0.07), MATS["soil"])


def build_coin_stack() -> None:
    for index in range(5):
        coin = cylinder("coin", (0, 0, 0.18 + index * 0.14), 0.58, 0.12, MATS["gold"], 48)
        rotate(coin, z=index * 8)
    sphere("spark", (-0.55, -0.28, 1.15), (0.12, 0.04, 0.12), MATS["cream"])
    sphere("spark", (0.48, -0.18, 1.02), (0.09, 0.04, 0.09), MATS["cream"])


def build_calendar() -> None:
    cube("calendar", (0, 0, 0.9), (1.32, 0.18, 1.45), MATS["cream"])
    cube("top", (0, -0.11, 1.52), (1.32, 0.12, 0.34), MATS["rose"])
    for col in range(3):
        for row in range(3):
            cube("calendar_square", (-0.36 + col * 0.36, -0.16, 1.16 - row * 0.28), (0.18, 0.05, 0.12), MATS["blue" if (col + row) % 2 else "leaf"])
    cylinder("ring_left", (-0.38, -0.16, 1.82), 0.07, 0.08, MATS["dark"], 16)
    cylinder("ring_right", (0.38, -0.16, 1.82), 0.07, 0.08, MATS["dark"], 16)


def build_windmill() -> None:
    cube("tower", (0, 0, 0.95), (0.82, 0.72, 1.55), MATS["cream"])
    roof = cone("roof", (0, 0, 1.9), 0.72, 0.12, 0.52, MATS["rose"], 4)
    rotate(roof, z=45)
    hub = cylinder("hub", (0, -0.43, 1.45), 0.12, 0.12, MATS["gold"], 24)
    rotate(hub, x=90)
    for angle in [0, 90, 180, 270]:
        blade = cube("blade", (0, -0.52, 1.45), (0.14, 0.05, 0.92), MATS["wood"])
        rotate(blade, x=90, z=angle)
    cube("door", (0, -0.38, 0.54), (0.34, 0.08, 0.56), MATS["wood"])


def build_market_stall() -> None:
    cube("counter", (0, 0, 0.55), (1.65, 0.78, 0.5), MATS["wood"])
    cube("cloth", (0, -0.08, 1.22), (1.95, 0.9, 0.14), MATS["rose"])
    for x in [-0.65, 0.0, 0.65]:
        cube("stripe", (x, -0.12, 1.29), (0.24, 0.92, 0.08), MATS["cream"])
    for x, material in [(-0.45, MATS["leaf"]), (0, MATS["gold"]), (0.45, MATS["pink"])]:
        sphere("produce", (x, -0.45, 0.92), (0.14, 0.14, 0.14), material)
    cube("left_post", (-0.82, 0, 0.9), (0.08, 0.08, 1.2), MATS["wood"])
    cube("right_post", (0.82, 0, 0.9), (0.08, 0.08, 1.2), MATS["wood"])


def build_bridge() -> None:
    for x in [-0.72, -0.36, 0, 0.36, 0.72]:
        plank = cube("plank", (x, 0, 0.42), (0.26, 1.24, 0.14), MATS["wood"])
        rotate(plank, z=x * 4)
    cube("left_rail", (-0.98, 0, 0.82), (0.08, 1.42, 0.12), MATS["cream"])
    cube("right_rail", (0.98, 0, 0.82), (0.08, 1.42, 0.12), MATS["cream"])
    for x in [-1.0, 1.0]:
        for y in [-0.58, 0.58]:
            cube("post", (x, y, 0.62), (0.11, 0.11, 0.56), MATS["wood"])


def build_quest_board() -> None:
    cube("board", (0, 0, 1.12), (1.36, 0.14, 0.92), MATS["wood"])
    cube("paper_a", (-0.28, -0.09, 1.22), (0.36, 0.04, 0.42), MATS["cream"])
    cube("paper_b", (0.28, -0.09, 1.04), (0.34, 0.04, 0.32), MATS["gold"])
    cube("roof", (0, 0, 1.72), (1.58, 0.28, 0.18), MATS["green_roof"])
    cube("post_l", (-0.52, 0, 0.46), (0.1, 0.1, 0.92), MATS["wood"])
    cube("post_r", (0.52, 0, 0.46), (0.1, 0.1, 0.92), MATS["wood"])


def build_tree_cluster() -> None:
    for x, y, scale in [(-0.52, -0.08, 1.0), (0.1, 0.16, 1.14), (0.58, -0.06, 0.92)]:
        cube("trunk", (x, y, 0.48 * scale), (0.18 * scale, 0.18 * scale, 0.72 * scale), MATS["wood"])
        sphere("leaf_ball", (x, y, 1.02 * scale), (0.46 * scale, 0.42 * scale, 0.38 * scale), MATS["leaf"])
        sphere("leaf_light", (x - 0.12, y - 0.04, 1.18 * scale), (0.22 * scale, 0.2 * scale, 0.18 * scale), MATS["green_roof"])


def build_pet_helper() -> None:
    sphere("body", (0, 0, 0.72), (0.54, 0.38, 0.32), MATS["cream"])
    sphere("head", (-0.44, -0.02, 0.92), (0.3, 0.3, 0.28), MATS["cream"])
    sphere("ear_a", (-0.58, -0.02, 1.16), (0.13, 0.06, 0.18), MATS["pink"])
    sphere("ear_b", (-0.34, -0.02, 1.16), (0.13, 0.06, 0.18), MATS["pink"])
    sphere("tail", (0.54, 0.02, 0.86), (0.18, 0.08, 0.14), MATS["cream"])
    for x in [-0.2, 0.16]:
        cube("leg", (x, -0.02, 0.36), (0.12, 0.12, 0.28), MATS["wood"])


def build_fountain() -> None:
    cylinder("base", (0, 0, 0.32), 0.82, 0.24, MATS["blue"], 48)
    cylinder("bowl", (0, 0, 0.62), 0.62, 0.2, MATS["cream"], 48)
    cylinder("pillar", (0, 0, 0.98), 0.18, 0.62, MATS["cream"], 32)
    sphere("water_top", (0, 0, 1.38), (0.28, 0.28, 0.12), MATS["blue"])
    for x, y in [(-0.34, 0), (0.34, 0), (0, -0.34), (0, 0.34)]:
        sphere("splash", (x, y, 1.16), (0.08, 0.08, 0.08), MATS["blue"])


def build_boat_dock() -> None:
    cube("dock", (0, 0, 0.42), (1.5, 0.78, 0.16), MATS["wood"])
    for x in [-0.62, 0, 0.62]:
        cube("plank", (x, 0, 0.54), (0.18, 0.9, 0.07), MATS["cream"])
    hull = cube("boat", (0.18, -0.56, 0.62), (1.0, 0.34, 0.24), MATS["rose"])
    rotate(hull, z=-8)
    cube("mast", (0.06, -0.56, 1.02), (0.06, 0.06, 0.74), MATS["wood"])
    cube("sail", (0.26, -0.58, 1.12), (0.42, 0.05, 0.54), MATS["cream"])


def torus(name: str, loc, major: float, minor: float, material):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=96, minor_segments=12, location=loc)
    obj = bpy.context.object
    obj.name = name
    assign(obj, material)
    obj.modifiers.new("cartoon shade", "WEIGHTED_NORMAL")
    return obj


def build_world_panorama() -> None:
    cube("far_sky_panel", (0, 2.8, 3.2), (18, 0.12, 5.2), MATS["blue"])
    cube("ground", (0, 0.9, -0.08), (18, 11, 0.14), MATS["leaf"])
    cube("lake", (0.8, -1.62, 0.02), (5.6, 1.9, 0.08), MATS["blue"])
    cube("river", (-3.4, -0.76, 0.03), (7.2, 0.38, 0.06), MATS["blue"])
    main_path = cube("main_path", (-0.3, -0.34, 0.04), (8.8, 0.42, 0.06), MATS["gold"])
    rotate(main_path, z=-8)
    market_path = cube("market_path", (3.2, -0.72, 0.05), (3.0, 0.34, 0.06), MATS["gold"])
    rotate(market_path, z=17)
    field_path = cube("field_path", (-2.9, -1.28, 0.05), (2.6, 0.32, 0.06), MATS["gold"])
    rotate(field_path, z=-22)
    for x, y, z, sx, sy, sz in [
        (-5.2, 2.2, 1.1, 1.5, 1.2, 2.4),
        (-2.6, 2.7, 1.6, 1.2, 1.0, 3.3),
        (1.5, 2.6, 1.55, 1.6, 1.3, 3.2),
        (4.2, 2.2, 1.25, 1.4, 1.0, 2.6),
        (6.3, 2.9, 1.4, 1.0, 0.9, 2.9),
    ]:
        rock = cone("distant_cliff", (x, y, z), sx, 0.28, sz, MATS["wood"], 6)
        rotate(rock, z=12)
        sphere("cliff_green", (x - 0.1, y - 0.15, z + sz * 0.36), (sx * 0.42, sy * 0.32, 0.16), MATS["green_roof"])
    arc = torus("sky_gate", (-0.5, 2.45, 2.25), 2.25, 0.055, MATS["cream"])
    rotate(arc, x=72)
    cube("gate_left", (-2.66, 2.26, 1.3), (0.15, 0.15, 2.1), MATS["cream"])
    cube("gate_right", (1.66, 2.26, 1.3), (0.15, 0.15, 2.1), MATS["cream"])
    for x, y, scale in [(-4.5, -1.5, 0.9), (-2.0, -2.3, 0.7), (2.5, -2.35, 0.8), (4.8, -1.2, 0.72), (6.0, -2.0, 0.62)]:
        cube("village_house", (x, y, 0.28 * scale), (0.72 * scale, 0.58 * scale, 0.56 * scale), MATS["cream"])
        roof = cone("village_roof", (x, y, 0.72 * scale), 0.54 * scale, 0.12 * scale, 0.42 * scale, MATS["rose"], 4)
        rotate(roof, z=45)
    for x, y, sx, sy in [(-3.8, -1.06, 1.55, 0.9), (-3.0, -1.42, 1.28, 0.78)]:
        cube("task_field_block", (x, y, 0.08), (sx, sy, 0.08), MATS["soil"])
        for row in range(3):
            for col in range(5):
                cylinder("field_crop", (x - sx * 0.34 + col * sx * 0.17, y - sy * 0.26 + row * sy * 0.22, 0.25), 0.025, 0.25, MATS["leaf_dark"], 10)
                sphere("field_bud", (x - sx * 0.34 + col * sx * 0.17, y - sy * 0.26 + row * sy * 0.22, 0.43), (0.055, 0.055, 0.055), MATS["gold"])
    cube("mailbox_scene_post", (-3.1, -0.32, 0.34), (0.08, 0.08, 0.68), MATS["wood"])
    cube("mailbox_scene_box", (-3.1, -0.32, 0.78), (0.48, 0.28, 0.24), MATS["rose"])
    cube("quest_scene_board", (-0.72, -0.28, 0.72), (0.78, 0.09, 0.54), MATS["wood"])
    cube("quest_scene_paper_a", (-0.86, -0.35, 0.78), (0.2, 0.03, 0.24), MATS["cream"])
    cube("quest_scene_paper_b", (-0.58, -0.35, 0.66), (0.18, 0.03, 0.18), MATS["gold"])
    cube("workshop_scene_house", (0.55, -0.56, 0.42), (1.1, 0.74, 0.84), MATS["cream"])
    roof = cone("workshop_scene_roof", (0.55, -0.56, 0.98), 0.78, 0.16, 0.42, MATS["blue"], 4)
    rotate(roof, z=45)
    cube("workshop_scene_screen", (0.55, -0.95, 0.52), (0.52, 0.04, 0.3), MATS["blue"])
    cube("greenhouse_scene_base", (2.15, -1.15, 0.24), (1.18, 0.72, 0.24), MATS["green_roof"])
    arch = cylinder("greenhouse_scene_arch", (2.15, -1.15, 0.72), 0.48, 1.18, MATS["glass"], 40)
    rotate(arch, y=90)
    cube("market_scene_counter", (3.55, -0.62, 0.32), (1.0, 0.48, 0.32), MATS["wood"])
    cube("market_scene_cloth", (3.55, -0.62, 0.75), (1.18, 0.54, 0.09), MATS["rose"])
    cube("dock_scene", (3.95, -1.9, 0.18), (1.35, 0.42, 0.12), MATS["wood"])
    boat = cube("dock_scene_boat", (4.4, -2.26, 0.24), (0.76, 0.22, 0.18), MATS["rose"])
    rotate(boat, z=-12)
    cylinder("fountain_scene_base", (-0.15, -0.98, 0.2), 0.38, 0.16, MATS["blue"], 42)
    cylinder("fountain_scene_pillar", (-0.15, -0.98, 0.52), 0.11, 0.44, MATS["cream"], 30)
    cube("studio_scene_house", (1.2, -1.74, 0.34), (0.82, 0.58, 0.68), MATS["cream"])
    studio_roof = cone("studio_scene_roof", (1.2, -1.74, 0.84), 0.58, 0.12, 0.34, MATS["green_roof"], 4)
    rotate(studio_roof, z=45)
    for x in [-6.8, -5.8, -4.9, 3.7, 4.5, 5.3, 6.4]:
        build_tree_cluster()
        cluster = bpy.context.selected_objects
        for obj in cluster:
            obj.location.x += x
            obj.location.y += -0.6 + (x % 1.5)
            obj.scale *= 0.58
    for x, z, sx in [(-6.2, 4.5, 1.2), (-5.5, 4.1, 0.9), (4.6, 4.3, 1.05), (5.4, 4.0, 0.72)]:
        sphere("cloud", (x, 1.5, z), (sx, 0.16, 0.32), MATS["cream"])


def save_panorama_scene() -> None:
    clear_scene()
    setup_panorama_camera()
    build_world_panorama()
    configure_panorama_render()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_DIR / "world-panorama-blender.blend"))


assets = {
    "avatar-gardener-blender": build_avatar,
    "avatar-walk-a-blender": build_avatar_walk_a,
    "avatar-walk-b-blender": build_avatar_walk_b,
    "task-field-blender": build_task_field,
    "mailbox-blender": build_mailbox,
    "workshop-blender": build_workshop,
    "greenhouse-blender": build_greenhouse,
    "art-studio-blender": build_art_studio,
    "seed-bag-blender": build_seed_bag,
    "coin-stack-blender": build_coin_stack,
    "calendar-blender": build_calendar,
    "windmill-blender": build_windmill,
    "market-stall-blender": build_market_stall,
    "bridge-blender": build_bridge,
    "quest-board-blender": build_quest_board,
    "tree-cluster-blender": build_tree_cluster,
    "pet-helper-blender": build_pet_helper,
    "fountain-blender": build_fountain,
    "boat-dock-blender": build_boat_dock,
}

for asset_name, builder in assets.items():
    render_asset(asset_name, builder)

save_panorama_scene()
render_panorama("world-panorama-blender", build_world_panorama)

print("BLENDER_2D_UPGRADE_ASSETS", [str(OUTPUT_DIR / f"{name}.png") for name in assets])
