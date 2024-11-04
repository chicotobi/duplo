import numpy as np

from track_types import straight, curve, switch, crossing

points = {}
endings = {}
points['straight'], endings['straight'] = straight()
points['curve'   ], endings['curve'   ] = curve()
points['switch'  ], endings['switch'  ] = switch()
points['crossing'], endings['crossing'] = crossing()

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
  
  return to_path(trafo_points), trafo_endings

def get_path_cursor(cursor):
  (x1, y1), (x2, y2) = cursor
  x3 = (x1+x2)/2 + (y1-y2)
  y3 = (y1+y2)/2 - (x1-x2)
  return [{'x': x1, 'y': y1},
          {'x': x2, 'y': y2},
          {'x': x3, 'y': y3}]
