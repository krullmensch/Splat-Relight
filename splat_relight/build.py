"""Node groups, material, shadow proxy and shadow box."""

import bpy
from mathutils import Matrix, Vector

SHADER_GROUP = "Splat Relight"
PROXY_GROUP = "Splat Relight Schattenproxy"
MAT_PREFIX = "Splat Relight"

# name, default, min, max, description
SHADER_INPUTS = [
    ("Delight", 0.6, 0.0, 1.5, "Eingebackenes Licht abschwächen: Albedo / baked_light^Delight"),
    ("Albedo Gamma", 2.2, 1.0, 3.0, "sRGB-Albedo linearisieren"),
    ("Helligkeit", 1.0, 0.0, 4.0, "Albedo-Helligkeit"),
    ("Sättigung", 1.0, 0.0, 2.0, "Albedo-Sättigung"),
    ("Translucent", 0.15, 0.0, 1.0, "Anteil Translucent BSDF (Licht von hinten)"),
    ("Rauheit", 0.8, 0.0, 1.0, "Roughness des Principled BSDF"),
    ("Specular", 0.3, 0.0, 1.0, "Specular IOR Level"),
    ("Original-Look", 0.0, 0.0, 1.0, "Original-Radiance als Emission beimischen (0 = voll neu beleuchtet)"),
    ("Tageslicht", 1.0, 0.0, 1.0, "Wird vom Licht-Rig gesetzt, blendet Original-Look nachts aus"),
    ("Emission Stärke", 1.0, 0.0, 10.0, "Stärke der Original-Radiance"),
]

PROXY_INPUTS = [
    # name, socket type, default, min, max
    ("Min Opazität", 'NodeSocketFloat', 0.35, 0.0, 1.0),
    ("Shadow Bias", 'NodeSocketFloat', 0.05, 0.0, 10.0),
    ("Box nutzen", 'NodeSocketBool', True, None, None),
    ("Box", 'NodeSocketObject', None, None, None),
]


def _new(nt, idname, x, y, label=None):
    n = nt.nodes.new(idname)
    n.location = (x, y)
    if label:
        n.label = label
    return n


def _attr(nt, name, x, y):
    a = _new(nt, "ShaderNodeAttribute", x, y, name)
    a.attribute_type = 'GEOMETRY'
    a.attribute_name = name
    return a


def _math(nt, op, x, y, a=None, b=None):
    m = _new(nt, "ShaderNodeMath", x, y)
    m.operation = op
    if a is not None:
        m.inputs[0].default_value = a
    if b is not None:
        m.inputs[1].default_value = b
    return m


# --------------------------------------------------------------------------- shader

SHADER_VERSION = 2


def shader_group():
    """Shader group. Rebuilt in place when it comes from an older add-on version."""
    ng = bpy.data.node_groups.get(SHADER_GROUP)
    if ng is not None and ng.get("sr_version") == SHADER_VERSION:
        return ng
    users = []
    if ng is None:
        ng = bpy.data.node_groups.new(SHADER_GROUP, "ShaderNodeTree")
    else:
        users = [m for m in bpy.data.materials if group_node(m) is not None]
        saved = {m.name: _saved_inputs(m) for m in users}
        ng.nodes.clear()
        ng.interface.clear()
    ng["sr_version"] = SHADER_VERSION
    _fill_shader_group(ng)
    for m in users:   # materials made with an older version: rewire to the new outputs
        build_material_tree(m, saved[m.name])
    return ng


def _fill_shader_group(ng):
    it = ng.interface
    it.new_socket("Shader", in_out='OUTPUT', socket_type='NodeSocketShader',
                  description="Für EEVEE")
    it.new_socket("Cycles", in_out='OUTPUT', socket_type='NodeSocketShader',
                  description="Für Cycles: beleuchtet auch Splats, deren Geometrie-Normale vom Licht weg zeigt")
    for name, dv, lo, hi, desc in SHADER_INPUTS:
        s = it.new_socket(name, in_out='INPUT', socket_type='NodeSocketFloat')
        s.default_value, s.min_value, s.max_value, s.description = dv, lo, hi, desc

    nt, L = ng, ng.links.new
    gi = _new(nt, "NodeGroupInput", -1400, 0)
    go = _new(nt, "NodeGroupOutput", 900, 0)

    # albedo (linear, delit)
    alb = _attr(nt, "albedo_srgb", -1150, 300)
    gam = _new(nt, "ShaderNodeGamma", -900, 300)
    L(alb.outputs["Color"], gam.inputs["Color"])
    L(gi.outputs["Albedo Gamma"], gam.inputs["Gamma"])

    bl = _attr(nt, "baked_light", -1150, 50)
    bl_max = _math(nt, 'MAXIMUM', -900, 50, b=0.02)
    L(bl.outputs["Factor"], bl_max.inputs[0])
    bl_pow = _math(nt, 'POWER', -700, 50)
    L(bl_max.outputs[0], bl_pow.inputs[0])
    L(gi.outputs["Delight"], bl_pow.inputs[1])

    div = _new(nt, "ShaderNodeVectorMath", -500, 250, "Delight")
    div.operation = 'DIVIDE'
    L(gam.outputs["Color"], div.inputs[0])
    L(bl_pow.outputs[0], div.inputs[1])

    hsv = _new(nt, "ShaderNodeHueSaturation", -300, 250)
    hsv.inputs["Hue"].default_value = 0.5
    L(div.outputs["Vector"], hsv.inputs["Color"])
    L(gi.outputs["Sättigung"], hsv.inputs["Saturation"])
    L(gi.outputs["Helligkeit"], hsv.inputs["Value"])

    # normal: object space attribute -> world space
    na = _attr(nt, "relight_N", -1150, -250)
    vt = _new(nt, "ShaderNodeVectorTransform", -900, -250)
    vt.vector_type, vt.convert_from, vt.convert_to = 'NORMAL', 'OBJECT', 'WORLD'
    L(na.outputs["Vector"], vt.inputs["Vector"])
    nrm = _new(nt, "ShaderNodeVectorMath", -700, -250)
    nrm.operation = 'NORMALIZE'
    L(vt.outputs["Vector"], nrm.inputs[0])

    pb = _new(nt, "ShaderNodeBsdfPrincipled", -50, 300)
    L(hsv.outputs["Color"], pb.inputs["Base Color"])
    L(gi.outputs["Rauheit"], pb.inputs["Roughness"])
    L(nrm.outputs["Vector"], pb.inputs["Normal"])
    if "Specular IOR Level" in pb.inputs:
        L(gi.outputs["Specular"], pb.inputs["Specular IOR Level"])

    tr = _new(nt, "ShaderNodeBsdfTranslucent", -50, -150)
    L(hsv.outputs["Color"], tr.inputs["Color"])
    L(nrm.outputs["Vector"], tr.inputs["Normal"])

    mix_lit = _new(nt, "ShaderNodeMixShader", 300, 100, "Translucent-Anteil")
    L(gi.outputs["Translucent"], mix_lit.inputs[0])
    L(pb.outputs[0], mix_lit.inputs[1])
    L(tr.outputs[0], mix_lit.inputs[2])

    # original radiance as emission, faded by daylight
    rad = _attr(nt, "radiance", -50, -400)
    em = _new(nt, "ShaderNodeEmission", 300, -350)
    L(rad.outputs["Color"], em.inputs["Color"])
    L(gi.outputs["Emission Stärke"], em.inputs["Strength"])

    fac = _math(nt, 'MULTIPLY', 300, -150)
    fac.use_clamp = True
    L(gi.outputs["Original-Look"], fac.inputs[0])
    L(gi.outputs["Tageslicht"], fac.inputs[1])

    mix_out = _new(nt, "ShaderNodeMixShader", 600, 0, "Original-Look")
    L(fac.outputs[0], mix_out.inputs[0])
    L(mix_lit.outputs[0], mix_out.inputs[1])
    L(em.outputs[0], mix_out.inputs[2])
    L(mix_out.outputs[0], go.inputs["Shader"])

    # Cycles: per splat, Cycles takes the shortest ellipsoid axis as geometric normal (random for
    # ordinary 3DGS) and only lets light reach reflection closures from that side, transmission
    # closures from the other. Without help about half of the splats get no light -> dark, spotty.
    # Translucent with the flipped normal returns albedo * max(0, N.L) / pi exactly on the side where
    # the Principled BSDF gets nothing, so every splat ends up lit by N.L.
    neg = _new(nt, "ShaderNodeVectorMath", -50, -650, "-N")
    neg.operation = 'SCALE'
    neg.inputs["Scale"].default_value = -1.0
    L(nrm.outputs["Vector"], neg.inputs[0])
    tr_back = _new(nt, "ShaderNodeBsdfTranslucent", 150, -650, "Rückseite (Cycles)")
    L(hsv.outputs["Color"], tr_back.inputs["Color"])
    L(neg.outputs["Vector"], tr_back.inputs["Normal"])
    back_w = _new(nt, "ShaderNodeMixShader", 350, -650, "× (1 − Translucent)")
    L(gi.outputs["Translucent"], back_w.inputs[0])
    L(tr_back.outputs[0], back_w.inputs[1])          # second input empty = no closure
    add = _new(nt, "ShaderNodeAddShader", 500, -500)
    L(mix_lit.outputs[0], add.inputs[0])
    L(back_w.outputs[0], add.inputs[1])
    mix_cy = _new(nt, "ShaderNodeMixShader", 700, -400, "Original-Look (Cycles)")
    L(fac.outputs[0], mix_cy.inputs[0])
    L(add.outputs[0], mix_cy.inputs[1])
    L(em.outputs[0], mix_cy.inputs[2])
    L(mix_cy.outputs[0], go.inputs["Cycles"])


def _saved_inputs(mat):
    grp = group_node(mat)
    if grp is None:
        return {}
    return {s.name: s.default_value for s in grp.inputs if hasattr(s, "default_value")}


def build_material_tree(mat, saved=None):
    """Group node -> one Material Output for EEVEE, one for Cycles. Keeps the user's values."""
    if saved is None:
        saved = _saved_inputs(mat)
    ng = shader_group()
    nt = mat.node_tree
    nt.nodes.clear()
    grp = _new(nt, "ShaderNodeGroup", 0, 0, SHADER_GROUP)
    grp.node_tree = ng
    grp.width = 220
    for k, v in saved.items():
        if k in grp.inputs:
            grp.inputs[k].default_value = v
    out_ev = _new(nt, "ShaderNodeOutputMaterial", 320, 80, "EEVEE")
    out_ev.target = 'EEVEE'
    out_cy = _new(nt, "ShaderNodeOutputMaterial", 320, -120, "Cycles")
    out_cy.target = 'CYCLES'
    nt.links.new(grp.outputs["Shader"], out_ev.inputs["Surface"])
    nt.links.new(grp.outputs["Cycles"], out_cy.inputs["Surface"])
    out_ev.is_active_output = True
    out_cy.is_active_output = True


def material_for(obj):
    """Create or repair the relight material and assign it to the splat."""
    name = f"{MAT_PREFIX} – {obj.name}"
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    build_material_tree(mat)
    pc = obj.data
    pc.materials.clear()
    pc.materials.append(mat)
    return mat


def group_node(mat):
    if mat is None or mat.node_tree is None:
        return None
    for n in mat.node_tree.nodes:
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree and n.node_tree.name.startswith(SHADER_GROUP):
            return n
    return None


def relight_materials():
    return [m for m in bpy.data.materials if group_node(m) is not None]


# --------------------------------------------------------------------------- shadow proxy

def proxy_group():
    ng = bpy.data.node_groups.get(PROXY_GROUP)
    if ng is not None:
        return ng
    ng = bpy.data.node_groups.new(PROXY_GROUP, "GeometryNodeTree")
    ng.is_modifier = True
    it = ng.interface
    it.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    it.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    for name, st, dv, lo, hi in PROXY_INPUTS:
        s = it.new_socket(name, in_out='INPUT', socket_type=st)
        if dv is not None:
            s.default_value = dv
        if lo is not None:
            s.min_value, s.max_value = lo, hi

    nt, L = ng, ng.links.new
    gi = _new(nt, "NodeGroupInput", -1200, 0)
    go = _new(nt, "NodeGroupOutput", 700, 0)

    # opacity threshold
    op = _new(nt, "GeometryNodeInputNamedAttribute", -900, 300)
    op.data_type = 'FLOAT'
    op.inputs["Name"].default_value = "opacity"
    cmp_op = _new(nt, "FunctionNodeCompare", -650, 300)
    cmp_op.data_type, cmp_op.operation = 'FLOAT', 'LESS_EQUAL'
    L(op.outputs["Attribute"], cmp_op.inputs[0])
    L(gi.outputs["Min Opazität"], cmp_op.inputs[1])

    # outside box (empty cube, local extent +-1)
    oi = _new(nt, "GeometryNodeObjectInfo", -900, 0)
    oi.transform_space = 'RELATIVE'
    L(gi.outputs["Box"], oi.inputs["Object"])
    inv = _new(nt, "FunctionNodeInvertMatrix", -700, 0)
    L(oi.outputs["Transform"], inv.inputs[0])
    pos = _new(nt, "GeometryNodeInputPosition", -700, -150)
    tp = _new(nt, "FunctionNodeTransformPoint", -500, 0)
    L(pos.outputs[0], tp.inputs["Vector"])
    L(inv.outputs[0], tp.inputs["Transform"])
    ab = _new(nt, "ShaderNodeVectorMath", -320, 0)
    ab.operation = 'ABSOLUTE'
    L(tp.outputs[0], ab.inputs[0])
    sep = _new(nt, "ShaderNodeSeparateXYZ", -150, 0)
    L(ab.outputs[0], sep.inputs[0])
    m1 = _math(nt, 'MAXIMUM', 0, 0)
    L(sep.outputs[0], m1.inputs[0])
    L(sep.outputs[1], m1.inputs[1])
    m2 = _math(nt, 'MAXIMUM', 150, 0)
    L(m1.outputs[0], m2.inputs[0])
    L(sep.outputs[2], m2.inputs[1])
    outside = _new(nt, "FunctionNodeCompare", 300, 0)
    outside.data_type, outside.operation = 'FLOAT', 'GREATER_THAN'
    L(m2.outputs[0], outside.inputs[0])
    outside.inputs[1].default_value = 1.0
    use_box = _new(nt, "FunctionNodeBooleanMath", 300, -150)
    use_box.operation = 'AND'
    L(outside.outputs[0], use_box.inputs[0])
    L(gi.outputs["Box nutzen"], use_box.inputs[1])

    sel = _new(nt, "FunctionNodeBooleanMath", 450, 200)
    sel.operation = 'OR'
    L(cmp_op.outputs[0], sel.inputs[0])
    L(use_box.outputs[0], sel.inputs[1])

    dele = _new(nt, "GeometryNodeDeleteGeometry", 250, 400)
    dele.domain = 'POINT'
    L(gi.outputs["Geometry"], dele.inputs["Geometry"])
    L(sel.outputs[0], dele.inputs["Selection"])

    # push splats back along -relight_N so they do not shadow themselves
    nN = _new(nt, "GeometryNodeInputNamedAttribute", 250, 600)
    nN.data_type = 'FLOAT_VECTOR'
    nN.inputs["Name"].default_value = "relight_N"
    neg = _math(nt, 'MULTIPLY', 250, 750, b=-1.0)
    L(gi.outputs["Shadow Bias"], neg.inputs[0])
    sc = _new(nt, "ShaderNodeVectorMath", 450, 650)
    sc.operation = 'SCALE'
    L(nN.outputs["Attribute"], sc.inputs[0])
    L(neg.outputs[0], sc.inputs["Scale"])
    sp = _new(nt, "GeometryNodeSetPosition", 500, 400)
    L(dele.outputs[0], sp.inputs["Geometry"])
    L(sc.outputs[0], sp.inputs["Offset"])
    L(sp.outputs[0], go.inputs["Geometry"])
    return ng


def socket_id(ng, name):
    for item in ng.interface.items_tree:
        if getattr(item, "in_out", None) == 'INPUT' and item.name == name:
            return item.identifier
    raise KeyError(name)


def input_owner(mod, name):
    """(struct, property name) for a modifier input; Blender 5.3 API with fallback to ID props."""
    ident = socket_id(mod.node_group, name)
    props = getattr(mod, "properties", None)
    if props is not None and hasattr(props, "inputs"):
        return getattr(props.inputs, ident), "value"
    return mod, f'["{ident}"]'


def set_input(mod, name, value):
    owner, prop = input_owner(mod, name)
    if prop == "value":
        owner.value = value
    else:
        mod[socket_id(mod.node_group, name)] = value


def proxy_modifier(proxy):
    if proxy is None:
        return None
    for m in proxy.modifiers:
        if m.type == 'NODES' and m.node_group and m.node_group.name.startswith(PROXY_GROUP):
            return m
    return None


def make_box(obj, lo, hi, margin=0.1):
    name = f"{obj.name} Schattenbereich"
    box = bpy.data.objects.get(name)
    if box is None:
        box = bpy.data.objects.new(name, None)
        box.empty_display_type = 'CUBE'
        _link_like(box, obj)
    lo, hi = Vector(lo), Vector(hi)
    ext = (hi - lo) * (0.5 + margin)
    ext = Vector([max(e, 1e-3) for e in ext])
    center = (lo + hi) * 0.5
    box.parent = obj
    box.matrix_parent_inverse = Matrix.Identity(4)
    box.matrix_basis = Matrix.Translation(center) @ Matrix.Diagonal((*ext, 1.0))
    box.hide_render = True
    return box


def make_proxy(obj, box, min_opacity, bias):
    name = f"{obj.name} Schattenproxy"
    proxy = bpy.data.objects.get(name)
    if proxy is None:
        proxy = bpy.data.objects.new(name, obj.data)
        _link_like(proxy, obj)
    proxy.data = obj.data
    proxy.parent = obj
    proxy.matrix_parent_inverse = Matrix.Identity(4)
    proxy.matrix_basis = Matrix.Identity(4)
    mod = proxy_modifier(proxy) or proxy.modifiers.new("Schattenproxy", 'NODES')
    ng = proxy_group()
    mod.node_group = ng
    set_input(mod, "Min Opazität", float(min_opacity))
    set_input(mod, "Shadow Bias", float(bias))
    set_input(mod, "Box", box)
    set_input(mod, "Box nutzen", box is not None)
    # only visible to shadow rays
    proxy.visible_camera = False
    proxy.visible_diffuse = False
    proxy.visible_glossy = False
    proxy.visible_transmission = False
    proxy.visible_volume_scatter = False
    proxy.visible_shadow = True
    proxy.display_type = 'BOUNDS'
    proxy.hide_select = False
    proxy["splat_relight_proxy_of"] = obj.name
    obj["splat_relight_proxy"] = proxy.name
    obj.visible_shadow = False
    return proxy


def _link_like(new, ref):
    cols = ref.users_collection or (bpy.context.scene.collection,)
    for c in cols:
        c.objects.link(new)


def splat_of(obj):
    """Resolve the splat object for a selected splat, proxy or box."""
    if obj is None:
        return None
    if obj.type == 'POINTCLOUD' and "splat_relight_proxy_of" not in obj:
        return obj
    src = obj.get("splat_relight_proxy_of")
    if src:
        return bpy.data.objects.get(src)
    if obj.parent is not None and obj.parent.type == 'POINTCLOUD':
        return obj.parent
    return None


def proxy_of(splat):
    if splat is None:
        return None
    name = splat.get("splat_relight_proxy")
    return bpy.data.objects.get(name) if name else None
