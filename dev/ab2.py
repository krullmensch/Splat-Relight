"""H1: Cycles picks reflection vs transmission per splat from its own Ng.
Test: add Translucent with flipped normal (-N) so the transmission side also gets N.L."""
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
g = sr.build.group_node(o.data.materials[0])

def render(eng, tag):
    sc.render.engine = eng
    if eng == "CYCLES": sc.cycles.samples = 64; sc.cycles.device = 'CPU'
    else: sc.eevee.taa_render_samples = 64
    f = os.path.join(out, f"ab2_{tag}.png"); sc.render.filepath = f
    bpy.ops.render.render(write_still=True)
    px = np.array(bpy.data.images.load(f).pixels[:]).reshape(210, 300, 4)[..., :3].mean(-1)
    crop = px[5:45, 20:280]
    print("AB2", tag, "mean %.3f std %.3f dark%% %.1f" % (crop.mean(), crop.std(), 100 * (crop < 0.5 * np.median(crop)).mean()))

render("BLENDER_EEVEE", "eevee")
render("CYCLES", "cycles")
# H1 variant: Translucent(-N) added on top
nt = g.node_tree
nrm = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeVectorMath" and n.operation == 'NORMALIZE')
hsv = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeHueSaturation")
mix_lit = next(n for n in nt.nodes if n.label == "Translucent-Anteil")
mix_out = next(n for n in nt.nodes if n.label == "Original-Look")
neg = nt.nodes.new("ShaderNodeVectorMath"); neg.operation = 'SCALE'; neg.inputs["Scale"].default_value = -1
nt.links.new(nrm.outputs[0], neg.inputs[0])
tb = nt.nodes.new("ShaderNodeBsdfTranslucent")
nt.links.new(hsv.outputs["Color"], tb.inputs["Color"]); nt.links.new(neg.outputs[0], tb.inputs["Normal"])
add = nt.nodes.new("ShaderNodeAddShader")
nt.links.new(mix_lit.outputs[0], add.inputs[0]); nt.links.new(tb.outputs[0], add.inputs[1])
nt.links.new(add.outputs[0], mix_out.inputs[1])
render("CYCLES", "cycles_h1")
render("BLENDER_EEVEE", "eevee_h1")
