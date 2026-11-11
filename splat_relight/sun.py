"""Sun / sky / moon rig driven by time, date and location."""

import math
import bpy
from mathutils import Vector

from . import build

SUN = "SR Sonne"
MOON = "SR Mond"
WORLD = "SR Himmel"


def solar_position(day, hour, lat, lon, utc):
    """NOAA approximation. Returns (elevation_deg, azimuth_deg from north, clockwise)."""
    g = 2 * math.pi / 365.0 * (day - 1 + (hour - utc - 12) / 24.0)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    dec = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
           - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
           - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    tst = hour * 60 + eqt + 4 * lon - 60 * utc
    ha = math.radians(tst / 4 - 180)
    phi = math.radians(lat)
    cz = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(ha)
    zen = math.acos(max(-1.0, min(1.0, cz)))
    az = math.degrees(math.atan2(math.sin(ha),
                                 math.cos(ha) * math.sin(phi) - math.tan(dec) * math.cos(phi))) + 180
    return 90 - math.degrees(zen), az % 360


def air_mass(el):
    z = 90 - el
    if el <= 0:
        return 40.0
    return 1.0 / (math.cos(math.radians(z)) + 0.50572 * (96.07995 - z) ** -1.6364)


def sun_factor(el):
    """Relative direct irradiance (Meinel), 1.0 at zenith."""
    if el <= -1:
        return 0.0
    rel = 0.7 ** (air_mass(max(el, 0.01)) ** 0.678) / 0.7
    fade = min(1.0, (el + 1) / 2)  # soften the sun going below the horizon
    return rel * fade


def sun_temperature(el):
    return 1900 + 4100 * (1 - math.exp(-max(el, 0) / 12.0))


def smoothstep(a, b, x):
    t = min(1.0, max(0.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def direction(el, az, north):
    """World vector pointing toward the light. az clockwise from north, north = +Y rotated by `north`."""
    a = math.radians(az + north)
    e = math.radians(el)
    return Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))


def _aim(obj, d):
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = d.to_track_quat('Z', 'Y')  # lamp shines along -Z


def _ensure_light(name, energy, angle_deg):
    ob = bpy.data.objects.get(name)
    if ob is None:
        lamp = bpy.data.lights.new(name, 'SUN')
        ob = bpy.data.objects.new(name, lamp)
        bpy.context.scene.collection.objects.link(ob)
    ob.data.energy = energy
    ob.data.angle = math.radians(angle_deg)
    ob.data.use_temperature = True
    return ob


def _ensure_world(scene):
    w = bpy.data.worlds.get(WORLD)
    if w is None:
        w = bpy.data.worlds.new(WORLD)
        nt = w.node_tree
        nt.nodes.clear()
        sky = nt.nodes.new("ShaderNodeTexSky")
        sky.name = "SR Sky"
        sky.sky_type = 'MULTIPLE_SCATTERING'
        sky.sun_disc = False          # direct light comes from the sun lamp
        sky.location = (-500, 100)
        bg = nt.nodes.new("ShaderNodeBackground")
        bg.name = "SR Sky BG"
        bg.location = (-250, 100)
        night = nt.nodes.new("ShaderNodeBackground")
        night.name = "SR Night BG"
        night.location = (-250, -100)
        add = nt.nodes.new("ShaderNodeAddShader")
        add.location = (0, 0)
        out = nt.nodes.new("ShaderNodeOutputWorld")
        out.location = (200, 0)
        L = nt.links.new
        L(sky.outputs["Color"], bg.inputs["Color"])
        L(bg.outputs[0], add.inputs[0])
        L(night.outputs[0], add.inputs[1])
        L(add.outputs[0], out.inputs["Surface"])
    scene.world = w
    return w


def create(scene):
    _ensure_light(SUN, 4.0, 0.53)
    _ensure_light(MOON, 0.0, 0.52)
    _ensure_world(scene)
    scene.splat_relight_sun.enabled = True
    update(scene)


def _fcurves(scene):
    ad = scene.animation_data
    if ad is None or ad.action is None:
        return {}
    fcs = []
    try:
        from bpy_extras import anim_utils
        cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
        fcs = cb.fcurves if cb else []
    except Exception:
        fcs = getattr(ad.action, "fcurves", [])
    return {fc.data_path: fc for fc in fcs if fc.data_path.startswith("splat_relight_sun.")}


class _Values:
    """Rig settings, with keyframed values evaluated at the current frame.

    frame_change_pre runs before animation is evaluated, so read the F-Curves directly.
    """

    def __init__(self, scene, use_fcurves):
        self._s = scene.splat_relight_sun
        self._fc = _fcurves(scene) if use_fcurves else {}
        self._f = scene.frame_current

    def __getattr__(self, name):
        fc = self._fc.get("splat_relight_sun." + name)
        if fc is not None:
            return fc.evaluate(self._f)
        return getattr(self._s, name)


def update(scene, from_frame_change=False):
    if not scene.splat_relight_sun.enabled:
        return
    s = _Values(scene, from_frame_change)
    el, az = solar_position(s.day, s.hour, s.latitude, s.longitude, s.utc_offset)
    disp = scene.splat_relight_sun   # display values
    night = smoothstep(-4.0, -10.0, el)
    day = smoothstep(-6.0, 4.0, el)
    disp.sun_elevation, disp.sun_azimuth, disp.daylight = el, az, day

    sun = bpy.data.objects.get(SUN)
    if sun is not None:
        _aim(sun, direction(el, az, s.north))
        sun.data.energy = s.sun_strength * sun_factor(el)
        sun.data.temperature = sun_temperature(el)
        sun.hide_render = sun.hide_viewport = el < -1.5

    moon = bpy.data.objects.get(MOON)
    if moon is not None:
        _aim(moon, direction(s.moon_elevation, s.moon_azimuth, s.north))
        moon.data.energy = s.moon_strength * night
        moon.data.temperature = 4100
        moon.hide_render = moon.hide_viewport = night <= 0.0

    w = bpy.data.worlds.get(WORLD)
    if w is not None and w.node_tree is not None:
        nodes = w.node_tree.nodes
        sky = nodes.get("SR Sky")
        if sky is not None:
            sky.sun_elevation = math.radians(el)
            # sky texture: rotation 0 = sun at +Y, positive = clockwise toward +X (checked by render)
            sky.sun_rotation = math.radians(az + s.north)
        bg = nodes.get("SR Sky BG")
        if bg is not None:
            bg.inputs["Strength"].default_value = s.sky_strength
        nbg = nodes.get("SR Night BG")
        if nbg is not None:
            nbg.inputs["Color"].default_value = (*scene.splat_relight_sun.night_color[:3], 1.0)
            nbg.inputs["Strength"].default_value = s.night_strength * night

    if s.couple_original:
        for m in build.relight_materials():
            g = build.group_node(m)
            if g is not None and "Tageslicht" in g.inputs:
                g.inputs["Tageslicht"].default_value = day


@bpy.app.handlers.persistent
def frame_handler(scene, *_):
    try:
        update(scene, from_frame_change=True)
    except Exception as e:  # never break playback / rendering
        print("Splat Relight sun update failed:", e)
