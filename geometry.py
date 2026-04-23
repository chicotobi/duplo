import numpy as np
from math import pi, cos, sin

from track_types import straight, curve, switch, crossing, w0, l0, c0

points = {}
endings = {}

PIECE_TYPES = ['straight','curve','switch','crossing']

points['straight'], endings['straight'] = straight()
points['curve'   ], endings['curve'   ] = curve()
points['switch'  ], endings['switch'  ] = switch()
points['crossing'], endings['crossing'] = crossing()

# Centerlines: list of polylines (each a list of (x,y) tuples) that the
# train follows for each piece type, in piece-local coordinates.
_n_cl = 12
_cl_curve = [(c0 * cos(i * pi / 6 / (_n_cl - 1)), c0 * sin(i * pi / 6 / (_n_cl - 1))) for i in range(_n_cl)]
_cl_curve_mirrored = [(2 * c0 - p[0], p[1]) for p in _cl_curve]

centerlines = {
    'straight': [[(w0 / 2, i * l0 / (_n_cl - 1)) for i in range(_n_cl)]],
    'curve':    [_cl_curve],
    'switch':   [_cl_curve, _cl_curve_mirrored],
    'crossing': [
        [(0, -l0), (0, l0)],
        [(-l0 * sin(pi / 3), -l0 * cos(pi / 3)), (l0 * sin(pi / 3), l0 * cos(pi / 3))],
    ],
}

# Helper functions
def affine_trafo(original, transform):
  (x1, y1), (x2, y2) = original
  (x1p, y1p), (x2p, y2p) = transform

  x3 = x1 + y1 - y2
  y3 = y1 + x2 - x1
  x3p = x1p + y1p - y2p
  y3p = y1p + x2p - x1p

  b = np.array(
    [
    [x1p, y1p],
    [x2p, y2p],
    [x3p, y3p],
    ]
    )

  A = np.array(
    [
    [x1, y1, 1],
    [x2, y2, 1],
    [x3, y3, 1]
    ]
    )
  
  out = np.transpose(np.linalg.solve(A,b))

  def tmp(pt):
    return out.dot(np.array([pt[0],pt[1],1]))

  return tmp

def to_path(xy):
  return [{'x':x, 'y':y} for x,y in xy]

def add_piece(type, cur_pos, ending_idx):
  # Flip the cursor_position
  cur_pos = cur_pos[::-1]

  # Which ending of the piece added is used
  original = endings[type][ending_idx]

  # Get the affine trafo function
  trafo = affine_trafo(original, cur_pos)

  # Transform the points of the piece
  trafo_points = [trafo(p) for p in points[type]]
  
  # Now transform the endings
  trafo_endings = [[trafo(p) for p in e] for e in endings[type]]

  # Now transform the centerlines for rendering / train animation
  trafo_centerlines = [to_path([trafo(p) for p in cl]) for cl in centerlines[type]]
  
  return to_path(trafo_points), trafo_endings, trafo_centerlines

def get_path_cursor(cursor):
  (x1, y1), (x2, y2) = cursor
  x3 = (x1+x2)/2 + (y1-y2)
  y3 = (y1+y2)/2 - (x1-x2)
  return [{'x': x1, 'y': y1},
          {'x': x2, 'y': y2},
          {'x': x3, 'y': y3}]
