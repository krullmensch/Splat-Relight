"""Run every panel's draw() headlessly with a strict fake layout.
Catches invalid icons, unknown property names and Python errors in UI code.
blender -b --factory-startup --python check_panels.py -- <addon_parent_dir> <ply>
"""
import bpy, sys, math, types
addon_dir, ply = sys.argv[-2:]
sys.path.insert(0, addon_dir)
bpy.ops.wm.read_factory_settings(use_empty=True)
import splat_relight as sr
sr.register()
ICONS = set(bpy.types.UILayout.bl_rna.functions['label'].parameters['icon'].enum_items.keys())
errors = []


class Layout:
    active = True
    enabled = True

    def _icon(self, kw):
        ic = kw.get("icon")
        if ic is not None and ic not in ICONS:
            errors.append(f"invalid icon {ic}")

    def label(self, text="", **kw): self._icon(kw)
    def separator(self, **kw): pass
    def row(self, **kw): return Layout()
    def column(self, **kw): return Layout()
    def box(self): return Layout()

    def prop(self, data, prop, **kw):
        self._icon(kw)
        if prop.startswith('["'):
            if prop[2:-2] not in data.keys():
                errors.append(f"missing id prop {prop} on {data}")
        elif prop not in data.bl_rna.properties:
            errors.append(f"unknown prop {prop} on {data.bl_rna.identifier}")

    def operator(self, idname, **kw):
        self._icon(kw)
        mod, name = idname.split(".")
        if not hasattr(getattr(bpy.ops, mod), name):
            errors.append(f"unknown operator {idname}")
        return types.SimpleNamespace()


def draw_all(tag):
    ctx = types.SimpleNamespace(scene=bpy.context.scene, active_object=bpy.context.view_layer.objects.active)
    for cls in sr.classes:
        if not issubclass(cls, bpy.types.Panel):
            continue
        if hasattr(cls, "poll") and not cls.poll(ctx):
            continue
        p = types.SimpleNamespace(layout=Layout())
        try:
            cls.draw(p, ctx)
        except Exception as e:
            errors.append(f"{tag} {cls.__name__}: {type(e).__name__}: {e}")
    print("DRAWN", tag)


draw_all("no selection")
bpy.ops.wm.ply_import(filepath=ply)
o = bpy.context.active_object
draw_all("splat before setup")
camd = bpy.data.cameras.new("C"); cam = bpy.data.objects.new("Cam", camd); bpy.context.scene.collection.objects.link(cam)
cam.location = (5, -5, 3.5); bpy.context.scene.camera = cam
bpy.context.scene.splat_relight.make_rig = True
with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
    bpy.ops.splat_relight.setup()
draw_all("splat after setup")
bpy.context.view_layer.objects.active = bpy.data.objects[o.name + " Schattenproxy"]
draw_all("proxy selected")
print("ERRORS", errors if errors else "none")
