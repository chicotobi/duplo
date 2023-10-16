import numpy as np

l0 = 4
straight = [(0,0),(1,0),(1,l0),(0,l0)]

ang = 30/180*np.pi
angs = np.sin(ang)
angc = np.cos(ang)

c0 = l0 * 7 / 2 / 3 ** .5
curve_left  = [(c0-.5,0),(c0+.5,0),((c0+.5)*angc,(c0+.5)*angs),((c0-.5)*angc,(c0-.5)*angs),(0,0)]
x = [(-x,y) for (x,y) in curve_left]
curve_right = [x[1],x[0],x[3],x[2],x[4]]

def affine_trafo(p1,p2,p1n,p2n):
  p1 = np.array(p1)
  p2  = np.array(p2)
  p1n = np.array(p1n)
  p2n = np.array(p2n)
  
  v = p2 - p1
  vn = p2n - p1n
  
  ang = angle_between_vectors(vn,v)
  
  # Find rotational matrix  
  A = np.matrix([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
  
  def tmp(pt):
    return A.dot(np.array(pt)-p1) + p1n
  
  return tmp

def angle_between_vectors(v1,v2):
  a1 = np.arctan2(v1[0],v1[1])
  a2 = np.arctan2(v2[0],v2[1])
  return a2-a1

def angle_against_horizontal(v1):
  v2 = np.array((1,0))
  return angle_between_vectors(v1,v2)

def cv(curve, cur_pos):
  trafo = affine_trafo(curve[0],curve[1],cur_pos[0],cur_pos[1])
  cu0 = [trafo(p).tolist()[0] for p in curve]
  r_outer = np.linalg.norm(np.array(cu0[1])-np.array(cu0[4]))
  r_inner = np.linalg.norm(np.array(cu0[0])-np.array(cu0[4]))
  theta1 = angle_against_horizontal(np.array(cu0[0])-np.array(cu0[4])) 
  center = cu0[4]
  new_pos = (cu0[3],cu0[2])
  return center, r_outer, r_inner, theta1, new_pos

def shape_straight(st):
    path = f"M {st[0][0]},{st[0][1]}"
    for x,y in st[1:]:
        path += f" L{x},{y}"
    path += " Z" 
    return dict(type="path", path=path)

def shape_wedge(center, ri, ro, th0, th1, n=50):
    t = np.linspace(th0, th1, n)
    x0 = np.cos(t)
    y0 = np.sin(t)
    x1 = center[0] + ri * x0
    y1 = center[1] + ri * y0
    x2 = center[0] + ro * x0[::-1]
    y2 = center[1] + ro * y0[::-1]
    x = np.concatenate([x1,x2])
    y = np.concatenate([y1,y2])
    path = f"M {x[0]},{y[0]}"
    for xc, yc in zip(x[1:], y[1:]):
        path += f" L{xc},{yc}"
    path += " Z" 
    return dict(type="path", path=path)

def add_curve_left(cur_pos):
  center, r_outer, r_inner, theta1, new_pos = cv(curve_left, cur_pos)
  shape = shape_wedge(center, r_inner, r_outer, theta1, theta1 + np.pi/6)
  return shape, new_pos

def add_curve_right(cur_pos):
  center, r_outer, r_inner, theta1, new_pos = cv(curve_right, cur_pos)  
  shape = shape_wedge(center ,r_inner, r_outer, theta1 - np.pi/6, theta1)
  return shape, new_pos

def add_straight(cur_pos):  
  trafo = affine_trafo(straight[0],straight[1],cur_pos[0],cur_pos[1])  
  st0 = [trafo(p).tolist()[0] for p in straight]  
  shape = shape_straight(st0)
  new_pos = (st0[3],st0[2])
  return shape, new_pos

def get_front_arrow(pos0):
    p1, p2 = pos0
    x1, y1 = p1
    x2, y2 = p2
    x3 = (x1+x2)/2 + (y1-y2)
    y3 = (y1+y2)/2 - (x1-x2)
    path = f"M {x1},{y1} L{x2},{y2} L{x3},{y3} L{x1},{y1} Z"
    return dict(type="path", path=path)