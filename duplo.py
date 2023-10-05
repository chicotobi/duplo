import streamlit as st
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Polygon
import numpy as np
from copy import copy

st.set_page_config(layout="wide")
st.title("Duplo Eisenbahn Designer")

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
  r_inner = r_outer - np.linalg.norm(np.array(cu0[0])-np.array(cu0[4]))
  theta1 = angle_against_horizontal(np.array(cu0[0])-np.array(cu0[4])) * 180 / np.pi
  theta2 = angle_against_horizontal(np.array(cu0[2])-np.array(cu0[4])) * 180 / np.pi
  center = cu0[4]
  new_pos = (cu0[3],cu0[2])
  return center, r_outer, r_inner, theta1, theta2, new_pos

def add_curve_left(cur_pos):
  center, r_outer, r_inner, theta1, theta2, new_pos = cv(curve_left, cur_pos)
  patch = Wedge(center,r_outer,theta1,theta2,r_inner,edgecolor='k',fill=False)
  return patch, new_pos

def add_curve_right(cur_pos):
  center, r_outer, r_inner, theta1, theta2, new_pos = cv(curve_right, cur_pos)  
  patch = Wedge(center,r_outer,theta2,theta1,r_inner,edgecolor='k',fill=False)
  return patch, new_pos

def add_straight(cur_pos):  
  trafo = affine_trafo(straight[0],straight[1],cur_pos[0],cur_pos[1])  
  st0 = [trafo(p).tolist()[0] for p in straight]  
  patch = Polygon(st0,edgecolor='k',fill=False)
  new_pos = (st0[3],st0[2])
  return patch, new_pos

if 'patches' not in st.session_state:
  st.session_state.patches = []
  st.session_state.pos0 = [[(0,.5),(0,-.5)]]

with st.container():
  col1, col2, col3, col4 = st.columns(4)
  with col1:
    if st.button('Straight'):
      pos0 = st.session_state.pos0[-1]
      patch, pos0 = add_straight(pos0)
      st.session_state.pos0.append(pos0)
      st.session_state.patches.append(patch)
    
  with col2:
    if st.button('Left'):
      pos0 = st.session_state.pos0[-1]
      patch, pos0 = add_curve_left(pos0)
      st.session_state.pos0.append(pos0)
      st.session_state.patches.append(patch)
      
  with col3:
    if st.button('Right'):
      pos0 = st.session_state.pos0[-1]
      patch, pos0 = add_curve_right(pos0)
      st.session_state.pos0.append(pos0)
      st.session_state.patches.append(patch)
  
  with col4:
    if st.button('Remove'):
      st.session_state.pos0.pop()
      st.session_state.patches.pop()
    
plt.cla()
fig, ax = plt.subplots()
for p in st.session_state.patches:
  p2 = copy(p)
  ax.add_patch(p2)

pos0 = st.session_state.pos0[-1]
p1, p2 = pos0
x1, y1 = p1
x2, y2 = p2
x3 = (x1+x2)/2 + (y1-y2)
y3 = (y1+y2)/2 - (x1-x2)
ax.plot([x1,x2,x3,x1],[y1,y2,y3,y1],'-g',linewidth=1)

ax.set_xlim((-20,60))
ax.set_ylim((-20,20))
plt.gca().set_aspect('equal')
plt.tick_params(left = False, right = False , labelleft = False , labelbottom = False, bottom = False) 
st.pyplot(fig)