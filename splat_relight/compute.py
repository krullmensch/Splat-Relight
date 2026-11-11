"""Per-splat attributes for relighting, computed with NumPy.

Writes (original splat data stays untouched):
  relight_N    FLOAT_VECTOR  normal from local PCA, oriented toward a reference point (object space)
  albedo_srgb  FLOAT_COLOR   DC colour without spherical harmonics (sRGB, 0..1)
  baked_light  FLOAT         low-frequency brightness of the capture, normalised to mean 1
  opacity      FLOAT         splat opacity (alpha of radiance:base)
"""

import time
import numpy as np
from mathutils import Vector

SH_C0 = 0.28209479177387814
_BITS = 21
_HALF = 1 << (_BITS - 1)
_MASK = (1 << _BITS) - 1


def _read(attrs, name, prop, width, n):
    arr = np.empty(n * width, dtype=np.float32)
    attrs[name].data.foreach_get(prop, arr)
    return arr.reshape(n, width) if width > 1 else arr


def _write(attrs, name, dtype, prop, values):
    if name in attrs:
        attrs.remove(attrs[name])
    attr = attrs.new(name, dtype, 'POINT')
    attr.data.foreach_set(prop, np.ascontiguousarray(values, dtype=np.float32).ravel())


def _encode(k):
    k = np.clip(k, -_HALF + 1, _HALF - 2) + _HALF
    return (k[:, 0] << (2 * _BITS)) | (k[:, 1] << _BITS) | k[:, 2]


def _decode(code):
    return np.stack(((code >> (2 * _BITS)) & _MASK,
                     (code >> _BITS) & _MASK,
                     code & _MASK), axis=1).astype(np.int64) - _HALF


def _voxelize(p, origin, size):
    k = np.floor((p - origin) / size).astype(np.int64)
    code = _encode(k)
    uniq, inv = np.unique(code, return_inverse=True)
    return uniq, inv.ravel()


def _neighbour_sum(uniq, sums):
    """Sum per-voxel quantities over the 3x3x3 neighbourhood of every voxel."""
    keys = _decode(uniq)
    total = np.zeros_like(sums)
    n = len(uniq)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                nc = _encode(keys + np.array([dx, dy, dz], dtype=np.int64))
                idx = np.searchsorted(uniq, nc)
                idx_c = np.minimum(idx, n - 1)
                ok = (idx < n) & (uniq[idx_c] == nc)
                total[ok] += sums[idx_c[ok]]
    return total


def pca_normals(p, w, voxel, ref_dirs):
    """p: (n,3) float64, w: (n,) weights, ref_dirs: (n,3) vectors from point toward reference."""
    origin = np.median(p, axis=0)
    uniq, inv = _voxelize(p, origin, voxel)
    x, y, z = p[:, 0] - origin[0], p[:, 1] - origin[1], p[:, 2] - origin[2]
    cols = (w, w * x, w * y, w * z, w * x * x, w * x * y, w * x * z, w * y * y, w * y * z, w * z * z)
    sums = np.stack([np.bincount(inv, weights=c, minlength=len(uniq)) for c in cols], axis=1)
    s = _neighbour_sum(uniq, sums)

    W = np.maximum(s[:, 0], 1e-12)
    mu = s[:, 1:4] / W[:, None]
    cov = np.empty((len(uniq), 3, 3))
    cov[:, 0, 0] = s[:, 4] / W - mu[:, 0] * mu[:, 0]
    cov[:, 0, 1] = cov[:, 1, 0] = s[:, 5] / W - mu[:, 0] * mu[:, 1]
    cov[:, 0, 2] = cov[:, 2, 0] = s[:, 6] / W - mu[:, 0] * mu[:, 2]
    cov[:, 1, 1] = s[:, 7] / W - mu[:, 1] * mu[:, 1]
    cov[:, 1, 2] = cov[:, 2, 1] = s[:, 8] / W - mu[:, 1] * mu[:, 2]
    cov[:, 2, 2] = s[:, 9] / W - mu[:, 2] * mu[:, 2]
    _, vecs = np.linalg.eigh(cov)
    vn = vecs[:, :, 0]                       # eigenvector of smallest eigenvalue

    # too few neighbours -> no reliable plane, fall back to reference direction
    count = np.bincount(inv, minlength=len(uniq)).astype(np.float64)
    count = _neighbour_sum(uniq, count[:, None])[:, 0]
    weak = count < 4

    n = vn[inv]
    rd = ref_dirs / np.maximum(np.linalg.norm(ref_dirs, axis=1, keepdims=True), 1e-12)
    n[weak[inv]] = rd[weak[inv]]
    flip = np.einsum('ij,ij->i', n, rd) < 0
    n[flip] *= -1
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return n.astype(np.float32), len(uniq)


def baked_light(p, w, lum, size):
    origin = np.median(p, axis=0)
    uniq, inv = _voxelize(p, origin, size)
    sums = np.stack([np.bincount(inv, weights=w, minlength=len(uniq)),
                     np.bincount(inv, weights=w * lum, minlength=len(uniq))], axis=1)
    s = _neighbour_sum(uniq, sums)
    blur = (s[:, 1] / np.maximum(s[:, 0], 1e-12))[inv]
    mean = np.sum(blur * w) / max(np.sum(w), 1e-12)
    return np.maximum(blur / max(mean, 1e-6), 0.02).astype(np.float32)


def compute(obj, voxel, blur, ref_mode, ref_obj=None, report=print):
    t0 = time.time()
    pc = obj.data
    attrs = pc.attributes
    n = len(pc.points)
    if n == 0:
        raise ValueError("Point Cloud ist leer")
    if "radiance:base" not in attrs:
        raise ValueError("Attribut 'radiance:base' fehlt, ist das ein Gaussian Splat?")

    p = _read(attrs, "position", "vector", 3, n).astype(np.float64)
    base = _read(attrs, "radiance:base", "vector", 4, n)
    opacity = np.clip(base[:, 3], 0.0, 1.0)
    albedo = np.clip(0.5 + SH_C0 * base[:, :3], 0.0, 1.0)

    # reference direction in object space
    mw = obj.matrix_world
    if ref_mode in {'CAMERA', 'OBJECT'} and ref_obj is not None:
        ref = np.array(mw.inverted() @ ref_obj.matrix_world.translation, dtype=np.float64)
        ref_dirs = ref[None, :] - p
    else:  # world up, expressed in object space
        up = mw.inverted().to_3x3() @ Vector((0, 0, 1))
        ref_dirs = np.broadcast_to(np.array(up, dtype=np.float64), p.shape)

    w = opacity.astype(np.float64) + 1e-4
    normals, nvox = pca_normals(p, w, voxel, ref_dirs)
    t1 = time.time()

    lin = albedo.astype(np.float64) ** 2.2
    lum = lin @ np.array([0.2126, 0.7152, 0.0722])
    bl = baked_light(p, w, lum, blur)
    t2 = time.time()

    rgba = np.concatenate([albedo, np.ones((n, 1), np.float32)], axis=1)
    _write(attrs, "relight_N", 'FLOAT_VECTOR', "vector", normals)
    _write(attrs, "albedo_srgb", 'FLOAT_COLOR', "color", rgba)
    _write(attrs, "baked_light", 'FLOAT', "value", bl)
    _write(attrs, "opacity", 'FLOAT', "value", opacity)
    pc.update_tag()

    report(f"Splat Relight: {n:,} Splats, {nvox:,} Voxel, Normalen {t1 - t0:.1f}s, "
           f"Delighting {t2 - t1:.1f}s, gesamt {time.time() - t0:.1f}s")
    return dict(points=n, voxels=nvox, seconds=time.time() - t0)


def robust_bounds(obj, lo=1.0, hi=99.0, min_opacity=0.35):
    """Object-space bounds of the dense part of the splat (ignores floaters)."""
    pc = obj.data
    n = len(pc.points)
    p = _read(pc.attributes, "position", "vector", 3, n)
    if "opacity" in pc.attributes:
        op = _read(pc.attributes, "opacity", "value", 1, n)
        sel = op > min_opacity
        if sel.sum() > 100:
            p = p[sel]
    a = np.percentile(p, lo, axis=0)
    b = np.percentile(p, hi, axis=0)
    return a, b
