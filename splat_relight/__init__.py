"""Splat Relight: relighting pipeline for native Gaussian Splats (Blender 5.3+).

Sidebar (N) > Splat Relight.
"""

import datetime
import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       IntProperty, PointerProperty)

from . import build, compute, sun


def _is_splat(obj):
    return obj is not None and obj.type == 'POINTCLOUD' and "radiance:base" in obj.data.attributes


def _sun_update(self, context):
    sun.update(context.scene)


# --------------------------------------------------------------------------- properties

class SR_Settings(bpy.types.PropertyGroup):
    scale: FloatProperty(
        name="Maßstab", default=1.0, min=0.001, soft_max=100,
        description="Blender-Einheiten pro realem Meter. Alle Meter-Werte unten werden damit multipliziert")
    voxel_m: FloatProperty(
        name="Normalen-Voxel (m)", default=0.15, min=0.005, soft_max=1.0, precision=3,
        description="Nachbarschaft für die PCA-Normale. Kleiner = mehr Detail, größer = ruhiger")
    blur_m: FloatProperty(
        name="Delight-Blur (m)", default=1.0, min=0.05, soft_max=10.0,
        description="Größe, über die eingebackenes Licht gemittelt wird")
    ref_mode: EnumProperty(
        name="Normalen zeigen zu",
        items=[('CAMERA', "Szenenkamera", "Normalen zur aktiven Kamera ausrichten (≈ Aufnahmeposition)"),
               ('OBJECT', "Objekt", "Normalen zu einem gewählten Objekt (z. B. Empty an der Aufnahmeposition)"),
               ('UP', "Oben", "Normalen nach oben (Welt +Z) ausrichten, gut für Böden und Außenaufnahmen")],
        default='CAMERA')
    ref_object: PointerProperty(name="Referenz", type=bpy.types.Object)
    make_material: BoolProperty(name="Material", default=True)
    make_proxy: BoolProperty(name="Schattenproxy", default=True,
                             description="Zweites Objekt, das nur Schatten wirft (ohne Selbstschatten-Rauschen)")
    min_opacity: FloatProperty(name="Min Opazität", default=0.35, min=0, max=1)
    bias_m: FloatProperty(name="Shadow Bias (m)", default=0.05, min=0, soft_max=1, precision=3)
    make_rig: BoolProperty(name="Licht-Rig", default=False,
                           description="Sonne, Himmel und Mond nach Uhrzeit, Datum und Ort")


class SR_Sun(bpy.types.PropertyGroup):
    enabled: BoolProperty(name="Rig aktiv", default=False, update=_sun_update)
    hour: FloatProperty(name="Uhrzeit", default=17.5, min=0, max=24, update=_sun_update,
                        description="Lokale Uhrzeit (Dezimal, 17.5 = 17:30). Keyframes möglich")
    day: IntProperty(name="Tag im Jahr", default=288, min=1, max=366, update=_sun_update)
    latitude: FloatProperty(name="Breite", default=52.02, min=-90, max=90, update=_sun_update)
    longitude: FloatProperty(name="Länge", default=8.53, min=-180, max=180, update=_sun_update)
    utc_offset: FloatProperty(name="UTC-Offset", default=2.0, min=-12, max=14, update=_sun_update,
                              description="MESZ = 2, MEZ = 1")
    north: FloatProperty(name="Nordrichtung", default=0.0, soft_min=-180, soft_max=180, update=_sun_update,
                         description="Dreht Sonne/Mond gegen die Szene (Grad)")
    sun_strength: FloatProperty(name="Sonne", default=4.0, min=0, soft_max=20, update=_sun_update)
    sky_strength: FloatProperty(name="Himmel", default=0.06, min=0, soft_max=1, precision=3,
                                update=_sun_update)
    moon_strength: FloatProperty(name="Mond", default=0.05, min=0, soft_max=1, precision=3,
                                 update=_sun_update)
    moon_elevation: FloatProperty(name="Mond Höhe", default=35, min=-10, max=90, update=_sun_update)
    moon_azimuth: FloatProperty(name="Mond Azimut", default=150, min=0, max=360, update=_sun_update)
    night_color: FloatVectorProperty(name="Nachthimmel", subtype='COLOR', size=3,
                                     default=(0.08, 0.12, 0.3), min=0, max=1, update=_sun_update)
    night_strength: FloatProperty(name="Nachthimmel Stärke", default=0.02, min=0, soft_max=1,
                                  precision=3, update=_sun_update)
    couple_original: BoolProperty(name="Original-Look an Tageslicht koppeln", default=True,
                                  update=_sun_update)
    # display only, written by sun.update
    sun_elevation: FloatProperty(name="Sonnenhöhe")
    sun_azimuth: FloatProperty(name="Azimut")
    daylight: FloatProperty(name="Tageslicht")


# --------------------------------------------------------------------------- operators

class SR_OT_setup(bpy.types.Operator):
    bl_idname = "splat_relight.setup"
    bl_label = "Relight einrichten"
    bl_description = ("Normalen, Albedo und eingebackenes Licht berechnen, Material, "
                      "Schattenproxy und optional Licht-Rig anlegen")
    bl_options = {'REGISTER', 'UNDO'}

    attributes_only: BoolProperty(default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return _is_splat(build.splat_of(context.active_object))

    def execute(self, context):
        st = context.scene.splat_relight
        obj = build.splat_of(context.active_object)
        ref = None
        if st.ref_mode == 'CAMERA':
            ref = context.scene.camera
            if ref is None:
                self.report({'WARNING'}, "Keine Szenenkamera, richte Normalen nach oben aus")
        elif st.ref_mode == 'OBJECT':
            ref = st.ref_object
            if ref is None:
                self.report({'ERROR'}, "Referenz-Objekt fehlt")
                return {'CANCELLED'}
        mode = st.ref_mode if ref is not None else 'UP'

        context.window_manager.progress_begin(0, 1)
        try:
            info = compute.compute(obj, st.voxel_m * st.scale, st.blur_m * st.scale, mode, ref,
                                   report=lambda m: self.report({'INFO'}, m))
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        finally:
            context.window_manager.progress_end()

        if not self.attributes_only:
            if st.make_material:
                build.material_for(obj)
            if st.make_proxy:
                lo, hi = compute.robust_bounds(obj, min_opacity=st.min_opacity)
                box = build.make_box(obj, lo, hi)
                build.make_proxy(obj, box, st.min_opacity, st.bias_m * st.scale)
            if st.make_rig:
                sun.create(context.scene)
            if context.scene.render.engine != 'CYCLES':
                self.report({'INFO'}, "Tipp: Pipeline ist für Cycles gebaut")
        obj.data.update_tag()
        self.report({'INFO'}, f"Splat Relight: {info['points']:,} Splats in {info['seconds']:.1f}s")
        return {'FINISHED'}


class SR_OT_fit_box(bpy.types.Operator):
    bl_idname = "splat_relight.fit_box"
    bl_label = "Box neu anpassen"
    bl_description = "Schattenbereich auf den dichten Teil des Splats (ohne Floater) setzen"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _is_splat(build.splat_of(context.active_object))

    def execute(self, context):
        obj = build.splat_of(context.active_object)
        lo, hi = compute.robust_bounds(obj, min_opacity=context.scene.splat_relight.min_opacity)
        build.make_box(obj, lo, hi)
        return {'FINISHED'}


class SR_OT_rig(bpy.types.Operator):
    bl_idname = "splat_relight.create_rig"
    bl_label = "Licht-Rig anlegen"
    bl_description = "Sonne, Mond und Himmel (Multiple Scattering) anlegen"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sun.create(context.scene)
        return {'FINISHED'}


class SR_OT_now(bpy.types.Operator):
    bl_idname = "splat_relight.today"
    bl_label = "Heute"
    bl_description = "Tag im Jahr auf das heutige Datum setzen"

    def execute(self, context):
        context.scene.splat_relight_sun.day = datetime.date.today().timetuple().tm_yday
        return {'FINISHED'}


class SR_OT_remove(bpy.types.Operator):
    bl_idname = "splat_relight.remove"
    bl_label = "Entfernen"
    bl_description = "Schattenproxy und Box löschen, Selbstschatten wieder an. Material und Attribute bleiben"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return build.splat_of(context.active_object) is not None

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        obj = build.splat_of(context.active_object)
        for o in (build.proxy_of(obj), bpy.data.objects.get(f"{obj.name} Schattenbereich")):
            if o is not None:
                bpy.data.objects.remove(o)
        obj.pop("splat_relight_proxy", None)
        obj.visible_shadow = True
        return {'FINISHED'}


# --------------------------------------------------------------------------- UI

class SR_PT_base(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Splat Relight"


class SR_PT_main(SR_PT_base):
    bl_label = "Splat Relight"

    def draw(self, context):
        lay = self.layout
        st = context.scene.splat_relight
        obj = build.splat_of(context.active_object)
        if not _is_splat(obj):
            lay.label(text="Gaussian Splat auswählen", icon='INFO')
            return
        lay.label(text=obj.name, icon='POINTCLOUD_DATA')
        has = "relight_N" in obj.data.attributes
        lay.label(text="Attribute berechnet" if has else "Noch nicht berechnet",
                  icon='CHECKMARK' if has else 'DOT')

        col = lay.column(align=True)
        col.prop(st, "scale")
        col.prop(st, "voxel_m")
        col.prop(st, "blur_m")
        lay.prop(st, "ref_mode", text="Normalen →")
        if st.ref_mode == 'OBJECT':
            lay.prop(st, "ref_object")

        row = lay.row(align=True)
        row.prop(st, "make_material", toggle=True)
        row.prop(st, "make_proxy", toggle=True)
        row.prop(st, "make_rig", toggle=True)
        if st.make_proxy:
            row = lay.row(align=True)
            row.prop(st, "min_opacity")
            row.prop(st, "bias_m")

        lay.operator(SR_OT_setup.bl_idname, icon='LIGHT_SUN')
        op = lay.operator(SR_OT_setup.bl_idname, text="Nur Attribute neu berechnen", icon='FILE_REFRESH')
        op.attributes_only = True


class SR_PT_material(SR_PT_base):
    bl_label = "Shader"
    bl_parent_id = "SR_PT_main"

    @classmethod
    def poll(cls, context):
        obj = build.splat_of(context.active_object)
        return _is_splat(obj) and obj.active_material is not None and build.group_node(obj.active_material)

    def draw(self, context):
        obj = build.splat_of(context.active_object)
        node = build.group_node(obj.active_material)
        col = self.layout.column(align=True)
        for s in node.inputs:
            if s.is_linked or not hasattr(s, "default_value"):
                continue
            if s.name == "Tageslicht" and context.scene.splat_relight_sun.enabled \
                    and context.scene.splat_relight_sun.couple_original:
                col.label(text=f"Tageslicht: {s.default_value:.2f} (Rig)")
                continue
            col.prop(s, "default_value", text=s.name)


class SR_PT_shadow(SR_PT_base):
    bl_label = "Schatten"
    bl_parent_id = "SR_PT_main"

    @classmethod
    def poll(cls, context):
        return _is_splat(build.splat_of(context.active_object))

    def draw(self, context):
        lay = self.layout
        obj = build.splat_of(context.active_object)
        lay.prop(obj, "visible_shadow", text="Selbstschatten (Splat)")
        proxy = build.proxy_of(obj)
        mod = build.proxy_modifier(proxy)
        if mod is None:
            lay.label(text="Kein Schattenproxy", icon='INFO')
            return
        lay.label(text=proxy.name, icon='GEOMETRY_NODES')
        col = lay.column(align=True)
        for name, *_ in build.PROXY_INPUTS:
            try:
                owner, prop = build.input_owner(mod, name)
            except (KeyError, AttributeError):
                continue
            col.prop(owner, prop, text=name)
        row = lay.row(align=True)
        row.prop(proxy, "hide_render", text="Proxy aus", toggle=True)
        row.operator(SR_OT_fit_box.bl_idname, icon='CUBE')
        lay.operator(SR_OT_remove.bl_idname, icon='TRASH')


class SR_PT_sun(SR_PT_base):
    bl_label = "Licht-Rig"
    bl_parent_id = "SR_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        lay = self.layout
        s = context.scene.splat_relight_sun
        if bpy.data.objects.get(sun.SUN) is None:
            lay.operator(SR_OT_rig.bl_idname, icon='LIGHT_SUN')
            return
        lay.prop(s, "enabled")
        col = lay.column(align=True)
        col.active = s.enabled
        h = int(s.hour)
        col.prop(s, "hour", text=f"Uhrzeit ({h:02d}:{int(round((s.hour - h) * 60)) % 60:02d})")
        row = col.row(align=True)
        d = datetime.date(2026, 1, 1) + datetime.timedelta(days=s.day - 1)
        row.prop(s, "day", text=f"Tag ({d.day}.{d.month}.)")
        row.operator(SR_OT_now.bl_idname, text="", icon='TIME')
        col.separator()
        col.prop(s, "latitude")
        col.prop(s, "longitude")
        col.prop(s, "utc_offset")
        col.prop(s, "north")
        col.separator()
        col.label(text=f"Sonne: {s.sun_elevation:.1f}° hoch, {s.sun_azimuth:.0f}° Azimut, "
                       f"Tageslicht {s.daylight:.2f}")
        col.separator()
        col.prop(s, "sun_strength")
        col.prop(s, "sky_strength")
        col.prop(s, "moon_strength")
        row = col.row(align=True)
        row.prop(s, "moon_elevation", text="Höhe")
        row.prop(s, "moon_azimuth", text="Azimut")
        col.prop(s, "night_color")
        col.prop(s, "night_strength")
        col.prop(s, "couple_original")


classes = (SR_Settings, SR_Sun, SR_OT_setup, SR_OT_fit_box, SR_OT_rig, SR_OT_now, SR_OT_remove,
           SR_PT_main, SR_PT_material, SR_PT_shadow, SR_PT_sun)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.splat_relight = PointerProperty(type=SR_Settings)
    bpy.types.Scene.splat_relight_sun = PointerProperty(type=SR_Sun)
    if sun.frame_handler not in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.append(sun.frame_handler)


def unregister():
    if sun.frame_handler in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(sun.frame_handler)
    del bpy.types.Scene.splat_relight_sun
    del bpy.types.Scene.splat_relight
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
