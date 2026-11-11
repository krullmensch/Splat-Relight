"""Synthetic 3DGS PLY: ground + box in 3DGS-style coords (Y down), round splats, few floaters.
Run with Blender's python:  <blender python> -I make_test_ply.py out.ply
"""
import sys
import numpy as np

rng = np.random.default_rng(1)
C0 = 0.28209479177387814
pts, cols = [], []

def surf(n, f, col):
    P = f(n)
    pts.append(P)
    c = np.array(col) * rng.uniform(0.85, 1.15, (n, 1))
    cols.append(c)

# Blender-world layout first (Z up), converted to Y-down at the end
surf(40000, lambda n: np.c_[rng.uniform(-3, 3, n), rng.uniform(-3, 3, n), rng.normal(0, .004, n)], (0.55, 0.55, 0.5))
for axis, sgn in ((0, 1), (0, -1), (1, 1), (1, -1)):
    def side(n, axis=axis, sgn=sgn):
        P = np.c_[rng.uniform(-.5, .5, n), rng.uniform(-.5, .5, n), rng.uniform(0, 1, n)]
        P[:, axis] = .5 * sgn + rng.normal(0, .004, n)
        return P
    surf(6000, side, (0.7, 0.3, 0.2))
surf(6000, lambda n: np.c_[rng.uniform(-.5, .5, n), rng.uniform(-.5, .5, n), 1 + rng.normal(0, .004, n)], (0.7, 0.3, 0.2))
surf(300, lambda n: rng.uniform(-4, 4, (n, 3)) + [0, 0, 2], (0.5, 0.5, 0.5))

P = np.concatenate(pts)
col = np.clip(np.concatenate(cols), 0, 1)
P = np.c_[P[:, 0], -P[:, 2], P[:, 1]]          # Z-up -> Y-down (COLMAP-like)
n = len(P)
dc = (col - 0.5) / C0
op = np.full(n, 3.0)
if '--iso' in sys.argv:
    sc = np.log(np.full((n, 3), 0.025))
    rot = np.tile([1.0, 0, 0, 0], (n, 1))
else:  # realistic: anisotropic, random orientation (like ordinary 3DGS training)
    sc = np.log(rng.uniform(0.008, 0.04, (n, 3)))
    rot = rng.normal(size=(n, 4)); rot /= np.linalg.norm(rot, axis=1, keepdims=True)
data = np.c_[P, dc, op, sc, rot].astype('<f4')
props = ['x', 'y', 'z', 'f_dc_0', 'f_dc_1', 'f_dc_2', 'opacity', 'scale_0', 'scale_1', 'scale_2',
         'rot_0', 'rot_1', 'rot_2', 'rot_3']
hdr = f"ply\nformat binary_little_endian 1.0\nelement vertex {n}\n" + "".join(f"property float {p}\n" for p in props) + "end_header\n"
open(sys.argv[1], 'wb').write(hdr.encode() + data.tobytes())
print("wrote", n)
