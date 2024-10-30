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

# Straight
straight_points = [(0,0),(w0,0),(w0,l0),(0,l0)]
straight_endings = [
                    [(0,0),(w0,0)],
                    [(w0,l0),(0,l0)]
                  ]

# Curve
def curve():
  n = 5
  t = [i / (n-1) * pi / 6 for i in range(n)]
  x0 = [cos(i) for i in t]
  y0 = [sin(i) for i in t]
  ri = c0 - w0/2
  ro = c0 + w0/2
  x = [ri * i for i in x0] + [ro * i for i in x0[::-1]]
  y = [ri * i for i in y0] + [ro * i for i in y0[::-1]]
  curve_points = list(zip(x,y))

  cos0 = cos(0)
  sin0 = sin(0)
  cos1 = cos(pi/6)
  sin1 = sin(pi/6)

  curve_endings = [
      [(ri * cos0, ri * sin0), (ro * cos0, ro * sin0)],
      [(ro * cos1, ro * sin1), (ri * cos1, ri * sin1)]
  ]
  return curve_points, curve_endings
curve_points, curve_endings = curve()

# Helper functions
def affine_trafo(p1,p2,p1n,p2n):
  x1, y1 = p1
  x2, y2 = p2

  x1p, y1p = p1n
  x2p, y2p = p2n

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

def add_curve_right(cur_pos, ending_idx = 1):
  pt0 = curve_endings[ending_idx][0]
  pt1 = curve_endings[ending_idx][1]
  trafo = affine_trafo(pt0, pt1, cur_pos[0],cur_pos[1])
  
  print(curve_endings[1])
  pts = [trafo(p) for p in curve_points]
  endings = [[trafo(p) for p in curve_endings[0]][::-1]]
  
  return to_path(pts), endings

def add_curve_left(cur_pos, ending_idx = 0):
  pt0 = curve_endings[ending_idx][0]
  pt1 = curve_endings[ending_idx][1]
  trafo = affine_trafo(pt0, pt1, cur_pos[0],cur_pos[1])

  print(curve_endings[1])
  pts = [trafo(p) for p in curve_points]
  endings = [[trafo(p) for p in curve_endings[1]][::-1]]

  return to_path(pts), endings

def add_straight(cur_pos, ending_idx = 0):
  pt0 = straight_endings[ending_idx][0]
  pt1 = straight_endings[ending_idx][1]
  trafo = affine_trafo(pt0, pt1,cur_pos[0],cur_pos[1])
  st0 = [trafo(p) for p in straight_points]
  ending0 = (st0[1],st0[0])
  ending1 = (st0[3],st0[2])
  endings = [ending1]
  return to_path(st0), endings

def get_front_arrow(pos):
  p1, p2 = pos
  x1, y1 = p1
  x2, y2 = p2
  x3 = (x1+x2)/2 + (y1-y2)
  y3 = (y1+y2)/2 - (x1-x2)
  return [{'x': x1, 'y': y1},
          {'x': x2, 'y': y2},
          {'x': x3, 'y': y3},
          {'x': x1, 'y': y1}]
