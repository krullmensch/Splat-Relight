"""Cycles vs EEVEE with the fixed add-on, plus upgrade of an old material."""
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
sc.splat_relight.make_rig = True
with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
    bpy.ops.splat_relight.setup()
sc.splat_relight_sun.hour = 15.0
sc.render.resolution_x, sc.render.resolution_y = 300, 210
mat = o.data.materials[0]
print("OUTPUTS", [(n.label, n.target, n.is_active_output, n.inputs["Surface"].is_linked) for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial"])

def render(eng, tag):
    sc.render.engine = eng
    if eng == "CYCLES": sc.cycles.samples = 64; sc.cycles.device = 'CPU'
    else: sc.eevee.taa_render_samples = 64
    f = os.path.join(out, f"fix_{tag}.png"); sc.render.filepath = f
    bpy.ops.render.render(write_still=True)
    px = np.array(bpy.data.images.load(f).pixels[:]).reshape(210, 300, 4)[..., :3].mean(-1)
    for name, crop in (("ground", px[5:45, 20:280]), ("box_lit", px[95:140, 135:175])):
        print("FIX", tag, name, "mean %.3f std %.3f" % (crop.mean(), crop.std()))

render("CYCLES", "cycles")
render("BLENDER_EEVEE", "eevee")
g = sr.build.group_node(mat)
for t in (0.0, 0.5):
    g.inputs["Translucent"].default_value = t
    render("CYCLES", f"cycles_tr{t}")
g.inputs["Translucent"].default_value = 0.15

# upgrade path: pretend the group is old, user value must survive, outputs rewired
g.inputs["Delight"].default_value = 0.33
sr.build.shader_group().pop("sr_version")
sr.build.shader_group()
g = sr.build.group_node(mat)
print("UPGRADE delight", round(g.inputs["Delight"].default_value, 2),
      [(n.target, n.inputs["Surface"].is_linked) for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial"])
