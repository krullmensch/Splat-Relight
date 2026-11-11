import bpy, sys, os, math, numpy as np
addon_dir, ply, out = sys.argv[-3:]
sys.path.insert(0, addon_dir)
bpy.ops.wm.read_factory_settings(use_empty=True)
import splat_relight as sr
sr.register()
sc = bpy.context.scene
bpy.ops.wm.ply_import(filepath=ply)
o = bpy.context.active_object
o.rotation_euler = (math.radians(-90), 0, 0)
camd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("Cam", camd); sc.collection.objects.link(cam)
cam.location = (5, -5, 3.5); sc.camera = cam
d = -cam.location.normalized(); cam.rotation_mode = 'QUATERNION'; cam.rotation_quaternion = d.to_track_quat('-Z', 'Y')
sc.splat_relight.make_rig = False
with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
    bpy.ops.splat_relight.setup()
proxy = bpy.data.objects[o.name + " Schattenproxy"]
sc.world = bpy.data.worlds.new("black")
sc.render.resolution_x, sc.render.resolution_y = 150, 105
sc.render.image_settings.file_format = 'OPEN_EXR'
vt_in = [s.name for s in bpy.data.node_groups.new("x","ShaderNodeTree").nodes.new("ShaderNodeVectorTransform").inputs]
print("VT inputs", vt_in)

def mat(src, transform):
    m = bpy.data.materials.new("dbg"); nt = m.node_tree; nt.nodes.clear(); L = nt.links.new
    a = nt.nodes.new("ShaderNodeAttribute"); a.attribute_type = 'GEOMETRY'; a.attribute_name = "relight_N"
    v = a.outputs["Vector"]
    vt = nt.nodes.new("ShaderNodeVectorTransform"); vt.vector_type, vt.convert_from, vt.convert_to = 'NORMAL', 'OBJECT', 'WORLD'
    if src == "attr":
        L(v, vt.inputs["Vector"])
    else:
        vt.inputs["Vector"].default_value = (0, -1, 0)
    v = vt.outputs["Vector"] if transform else (v if src == "attr" else vt.inputs["Vector"])
    e = nt.nodes.new("ShaderNodeEmission"); on = nt.nodes.new("ShaderNodeOutputMaterial")
    L(v if transform or src == "attr" else vt.outputs["Vector"], e.inputs["Color"]); L(e.outputs[0], on.inputs[0])
    return m
for eng in ("CYCLES", "BLENDER_EEVEE"):
    sc.render.engine = eng
    if eng == "CYCLES": sc.cycles.samples = 16; sc.cycles.device = 'CPU'; sc.cycles.use_denoising = False
    else: sc.eevee.taa_render_samples = 16
    for src, tr in (("attr", False), ("attr", True), ("const", True)):
        o.data.materials.clear(); o.data.materials.append(mat(src, tr))
        f = os.path.join(out, f"n2_{eng}_{src}_{int(tr)}.exr"); sc.render.filepath = f
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(f); px = np.array(img.pixels[:]).reshape(105, 150, 4)[..., :3]
        crop = px[3:20, 15:135].reshape(-1, 3)   # ground front
        print("N2", eng, src, "xform" if tr else "raw", "ground mean", np.round(crop.mean(0), 3), "std", np.round(crop.std(0), 3))
