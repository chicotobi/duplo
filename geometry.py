import numpy as np
from math import pi, sin, cos

# https://www.duplo-schienen.de/lego-duplo-schienen-geometrische-regeln.html
# length of seven straight = length of rrllllrr (eight curves)

w0 = 1 * 10
l0 = 4 * 10

angs = np.sin(np.pi / 6)
angc = np.cos(np.pi / 6)

# length of seven straight = length of rrllllrr (eight curves)
# This gives the mean curve radius?
c0 = l0 * 7 / 2 / 3 ** .5

points = {}
endings = {}

# Straight
points['straight'] = [(0,0),(w0,0),(w0,l0),(0,l0)]
endings['straight'] = [
                    [(w0,0),(0,0)],
                    [(0,l0),(w0,l0)]
                  ]

# Left curve
# Endings are bottom (0) and top left (1)
def curve():
  n = 5
  t = [i / (n-1) * pi / 6 for i in range(n)]
  x0 = [cos(i) for i in t]
  y0 = [sin(i) for i in t]
  ri = c0 - w0/2
  ro = c0 + w0/2
  x = [ri * i for i in x0] + [ro * i for i in x0[::-1]]
  y = [ri * i for i in y0] + [ro * i for i in y0[::-1]]
  points = list(zip(x,y))

  cos0 = cos(0)
  sin0 = sin(0)
  cos1 = cos(pi/6)
  sin1 = sin(pi/6)

  endings = [
      [(ro * cos0, ro * sin0), (ri * cos0, ri * sin0)],
      [(ri * cos1, ri * sin1), (ro * cos1, ro * sin1)]
  ]
  return points, endings
points['curve'], endings['curve'] = curve()

# Switch with input at the bottom and two output at top left and top right
# Endings are bottom (0) and top left (1) and top right (2)
def switch():
  n = 10
  m = round(n * 0.6)
  t = [i / (n-1) * pi / 6 for i in range(n)]
  x0 = [cos(i) for i in t]
  y0 = [sin(i) for i in t]
  ri = c0 - w0/2
  ro = c0 + w0/2
  x = [ri * i for i in x0] + [ro * i for i in x0[:m:-1]] + [2*c0 - ro * i for i in x0[m:]] + [2*c0 - ri * i for i in x0[::-1]]
  y = [ri * i for i in y0] + [ro * i for i in y0[:m:-1]] + [       ro * i for i in y0[m:]] + [       ri * i for i in y0[::-1]]
  points = list(zip(x,y))

  cos0 = cos(0)
  sin0 = sin(0)
  cos1 = cos(pi/6)
  sin1 = sin(pi/6)

  endings = [
      [(ro * cos0, ro * sin0), (ri * cos0, ri * sin0)],
      [(ri * cos1, ri * sin1), (ro * cos1, ro * sin1)],
      [(2*c0 - ro * cos1, ro * sin1), (2*c0 - ri * cos1, ri * sin1)],
  ]
  return points, endings
points['switch'], endings['switch'] = switch()

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

  # Remove the taken ending
  #trafo_endings.pop(ending_idx)

  # Currently, just return the first available ending
  #new_ending = trafo_endings[0]

  # Arrow has to point the "other way", so switch the two points around
  #new_ending = new_ending[::-1]
  
  return to_path(trafo_points), trafo_endings

def get_path_cursor(cursor):
  (x1, y1), (x2, y2) = cursor
  x3 = (x1+x2)/2 + (y1-y2)
  y3 = (y1+y2)/2 - (x1-x2)
  return [{'x': x1, 'y': y1},
          {'x': x2, 'y': y2},
          {'x': x3, 'y': y3},
          {'x': x1, 'y': y1}]
