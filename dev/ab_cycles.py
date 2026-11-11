"""A/B experiments in Cycles to isolate the blotchy ground."""
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
s = sc.splat_relight_sun; s.hour = 15.0
sc.render.engine = 'CYCLES'; sc.cycles.samples = 64; sc.cycles.device = 'CPU'
sc.render.resolution_x, sc.render.resolution_y = 300, 210
proxy = bpy.data.objects[o.name + " Schattenproxy"]
g = sr.build.group_node(o.data.materials[0])

def render(tag):
    f = os.path.join(out, f"ab_{tag}.png"); sc.render.filepath = f
    bpy.ops.render.render(write_still=True)
    px = np.array(bpy.data.images.load(f).pixels[:]).reshape(210, 300, 4)[..., :3].mean(-1)
    crop = px[5:45, 20:280]          # ground in front of the box
    print("AB", tag, "mean %.3f std %.3f dark%% %.1f" % (crop.mean(), crop.std(), 100 * (crop < 0.5 * np.median(crop)).mean()))

render("baseline")
proxy.hide_render = True; render("no_proxy"); proxy.hide_render = False
sun = bpy.data.objects["SR Sonne"]; sun.data.use_shadow = False; render("sun_no_shadow"); sun.data.use_shadow = True
g.inputs["Translucent"].default_value = 0.0; render("no_translucent"); g.inputs["Translucent"].default_value = 0.15
o.visible_shadow = True; proxy.hide_render = True; render("self_shadow_on_no_proxy"); o.visible_shadow = False; proxy.hide_render = False
# replace attribute normal by constant world up -> does blotch vanish?
nt = g.node_tree
vt = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeVectorTransform")
lk = vt.inputs["Vector"].links[0]; src = lk.from_socket; nt.links.remove(lk)
vt.inputs["Vector"].default_value = (0, -1, 0)   # local -Y == world +Z for this object
render("const_normal")
nt.links.new(src, vt.inputs["Vector"])
