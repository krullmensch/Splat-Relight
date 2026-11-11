"""Render the same relit splat in Cycles and EEVEE, plus a normal-debug pass.
blender -b --factory-startup --python compare_engines.py -- <addon_parent_dir> <ply> <outdir>
"""
import bpy, sys, os, math
addon_dir, ply, out = sys.argv[-3:]
sys.path.insert(0, addon_dir)
bpy.ops.wm.read_factory_settings(use_empty=True)
import splat_relight as sr
sr.register()
sc = bpy.context.scene
bpy.ops.wm.ply_import(filepath=ply)
o = bpy.context.active_object
o.rotation_euler = (math.radians(-90), 0, 0)   # Y-down data -> Z-up
camd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("Cam", camd); sc.collection.objects.link(cam)
cam.location = (5, -5, 3.5); sc.camera = cam
d = -cam.location.normalized(); cam.rotation_mode = 'QUATERNION'; cam.rotation_quaternion = d.to_track_quat('-Z', 'Y')
st = sc.splat_relight; st.make_rig = True
with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
    bpy.ops.splat_relight.setup()
s = sc.splat_relight_sun; s.hour = 15.0; s.north = 0.0
sc.render.resolution_x, sc.render.resolution_y = 400, 280
mat = o.data.materials[0]

def normal_debug():
    m = bpy.data.materials.new("dbgN"); nt = m.node_tree; nt.nodes.clear()
    a = nt.nodes.new("ShaderNodeAttribute"); a.attribute_type = 'GEOMETRY'; a.attribute_name = "relight_N"
    vt = nt.nodes.new("ShaderNodeVectorTransform"); vt.vector_type, vt.convert_from, vt.convert_to = 'NORMAL', 'OBJECT', 'WORLD'
    mp = nt.nodes.new("ShaderNodeVectorMath"); mp.operation = 'MULTIPLY_ADD'
    mp.inputs[1].default_value = (.5, .5, .5); mp.inputs[2].default_value = (.5, .5, .5)
    e = nt.nodes.new("ShaderNodeEmission"); outn = nt.nodes.new("ShaderNodeOutputMaterial")
    L = nt.links.new
    L(a.outputs["Vector"], vt.inputs[0]); L(vt.outputs[0], mp.inputs[0]); L(mp.outputs[0], e.inputs[0]); L(e.outputs[0], outn.inputs[0])
    return m
dbg = normal_debug()

for eng in ("CYCLES", "BLENDER_EEVEE"):
    sc.render.engine = eng
    if eng == "CYCLES":
        sc.cycles.samples = 64; sc.cycles.device = 'CPU'
    else:
        sc.eevee.taa_render_samples = 64
    for tag, m in (("relit", mat), ("normals", dbg)):
        o.data.materials[0] = m
        sc.render.filepath = os.path.join(out, f"{eng.lower()}_{tag}.png")
        bpy.ops.render.render(write_still=True)
    o.data.materials[0] = mat
print("DONE")
