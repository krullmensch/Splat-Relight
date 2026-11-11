"""Numeric evidence: what does the shader see as relight_N in Cycles vs EEVEE?"""
import bpy, sys, os, math, numpy as np
addon_dir, ply, out = sys.argv[-3:]
sys.path.insert(0, addon_dir)
bpy.ops.wm.read_factory_settings(use_empty=True)
import splat_relight as sr
sr.register()
sc = bpy.context.scene
sc.view_settings.view_transform = 'Standard'
bpy.ops.wm.ply_import(filepath=ply)
o = bpy.context.active_object
o.rotation_euler = (math.radians(-90), 0, 0)
camd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("Cam", camd); sc.collection.objects.link(cam)
cam.location = (5, -5, 3.5); sc.camera = cam
d = -cam.location.normalized(); cam.rotation_mode = 'QUATERNION'; cam.rotation_quaternion = d.to_track_quat('-Z', 'Y')
sc.splat_relight.make_rig = False
with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
    bpy.ops.splat_relight.setup()
sc.world = bpy.data.worlds.new("black")
sc.render.resolution_x, sc.render.resolution_y = 200, 140

def dbg(src, transform):
    m = bpy.data.materials.new("dbg"); nt = m.node_tree; nt.nodes.clear(); L = nt.links.new
    if src == "attr":
        a = nt.nodes.new("ShaderNodeAttribute"); a.attribute_type = 'GEOMETRY'; a.attribute_name = "relight_N"; v = a.outputs["Vector"]
    elif src == "geomN":
        a = nt.nodes.new("ShaderNodeNewGeometry"); v = a.outputs["Normal"]
    elif src == "alb":
        a = nt.nodes.new("ShaderNodeAttribute"); a.attribute_type = 'GEOMETRY'; a.attribute_name = "albedo_srgb"; v = a.outputs["Color"]
    if transform:
        vt = nt.nodes.new("ShaderNodeVectorTransform"); vt.vector_type, vt.convert_from, vt.convert_to = 'NORMAL', 'OBJECT', 'WORLD'
        L(v, vt.inputs[0]); v = vt.outputs[0]
    mp = nt.nodes.new("ShaderNodeVectorMath"); mp.operation = 'MULTIPLY_ADD'
    mp.inputs[1].default_value = (.5, .5, .5); mp.inputs[2].default_value = (.5, .5, .5)
    e = nt.nodes.new("ShaderNodeEmission"); on = nt.nodes.new("ShaderNodeOutputMaterial")
    L(v, mp.inputs[0]); L(mp.outputs[0], e.inputs[0]); L(e.outputs[0], on.inputs[0])
    return m

# pixel probes (x,y from bottom-left) on ground and box faces, picked for 200x140
probes = {"ground_front": (100, 20), "ground_right": (170, 50), "box_top": (100, 92), "box_left": (85, 70), "box_right": (115, 70)}
for eng in ("CYCLES", "BLENDER_EEVEE"):
    sc.render.engine = eng
    if eng == "CYCLES": sc.cycles.samples = 32; sc.cycles.device = 'CPU'; sc.cycles.use_denoising = False
    else: sc.eevee.taa_render_samples = 32
    for src, tr in (("attr", False), ("attr", True), ("geomN", False), ("alb", False)):
        o.data.materials.clear(); o.data.materials.append(dbg(src, tr))
        f = os.path.join(out, f"probe_{eng}_{src}_{int(tr)}.png"); sc.render.filepath = f
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(f); px = np.array(img.pixels[:]).reshape(140, 200, 4)
        vals = {k: tuple(np.round(px[y-2:y+3, x-2:x+3, :3].reshape(-1, 3).mean(0) * 2 - 1, 2)) for k, (x, y) in probes.items()}
        print("PROBE", eng, src, "xform" if tr else "raw", vals)
