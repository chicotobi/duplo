import streamlit as st
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Polygon
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

patches = []

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
  
def add_straight(ax,cur_pos):
  
  trafo = affine_trafo(straight[0],straight[1],cur_pos[0],cur_pos[1])
  
  st0 = [trafo(p).tolist()[0] for p in straight]
  
  ax.add_patch(Polygon(st0,edgecolor='k',fill=False)) 
  new_pos = (st0[3],st0[2])
  return ax, new_pos

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

def add_curve_left(ax,cur_pos):
  center, r_outer, r_inner, theta1, theta2, new_pos = cv(curve_left, cur_pos)
  ax.add_patch(Wedge(center,r_outer,theta1,theta2,r_inner,edgecolor='k',fill=False))
  return ax, new_pos

def add_curve_right(ax,cur_pos):
  center, r_outer, r_inner, theta1, theta2, new_pos = cv(curve_right, cur_pos)  
  ax.add_patch(Wedge(center,r_outer,theta2,theta1,r_inner,edgecolor='k',fill=False)) 
  return ax, new_pos

if 'ax' not in st.session_state:
    fig, ax = plt.subplots()
    st.session_state.ax = ax
    st.session_state.fig = fig
    st.session_state.pos0 = [(0,0),(1,0)]

if st.button('Straight'):
  ax = st.session_state.ax
  pos0 = st.session_state.pos0 
  ax, pos0  = add_straight(ax, pos0)
  st.session_state.ax = ax
  st.session_state.pos0 = pos0
  
if st.button('Left'):
  ax = st.session_state.ax
  pos0 = st.session_state.pos0 
  ax, pos0  = add_curve_left(ax, pos0)
  st.session_state.ax = ax
  st.session_state.pos0 = pos0
  
if st.button('Right'):
  ax = st.session_state.ax
  pos0 = st.session_state.pos0 
  ax, pos0  = add_curve_right(ax, pos0)
  st.session_state.ax = ax
  st.session_state.pos0 = pos0

st.session_state.ax.set_xlim((-60,60))
st.session_state.ax.set_ylim((-60,60))
plt.axis('off')
st.session_state.fig