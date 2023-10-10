import dash_bootstrap_components as dbc
import dash

import numpy as np
from numpy import pi, sin, cos
import plotly.graph_objects as go


pos0 = [[(9.5,10),(10.5,10)]]

l0 = 4
straight = [(0,0),(1,0),(1,l0),(0,l0)]

ang = 30/180*np.pi
angs = np.sin(ang)
angc = np.cos(ang)

c0 = l0 * 7 / 2 / 3 ** .5
curve_left  = [(c0-.5,0),(c0+.5,0),((c0+.5)*angc,(c0+.5)*angs),((c0-.5)*angc,(c0-.5)*angs),(0,0)]
x = [(-x,y) for (x,y) in curve_left]
curve_right = [x[1],x[0],x[3],x[2],x[4]]

def straight(st):
    path = f"M {st[0]},{st[0]}"
    for x,y in st:
        path += f" L{x},{y}"
    return path + " Z" 

def wedge(center, ri, ro, th0, th1, n=50):
    t = np.linspace(th0, th1, n)
    x0 = cos(t)
    y0 = sin(t)
    x1 = center[0] + ri * x0
    y1 = center[1] + ri * y0
    x2 = center[0] + ro * x0[::-1]
    y2 = center[1] + ro * y0[::-1]
    x = np.concatenate([x1,x2])
    y = np.concatenate([y1,y2])
    path = f"M {x[0]},{y[0]}"
    for xc, yc in zip(x[1:], y[1:]):
        path += f" L{xc},{yc}"
    return path + " Z" 

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
  theta1 = angle_against_horizontal(np.array(cu0[0])-np.array(cu0[4])) * 180 / np.pi
  theta2 = angle_against_horizontal(np.array(cu0[2])-np.array(cu0[4])) * 180 / np.pi
  center = cu0[4]
  new_pos = (cu0[3],cu0[2])
  return center, r_outer, r_inner, theta1, theta2, new_pos

def add_curve_left(cur_pos):
  center, r_outer, r_inner, theta1, theta2, new_pos = cv(curve_left, cur_pos)
  patch = wedge(center,r_inner, r_outer,theta1/180*pi,theta2/180*pi)
  return patch, new_pos

def add_curve_right(cur_pos):
  center, r_outer, r_inner, theta1, theta2, new_pos = cv(curve_right, cur_pos)  
  patch = wedge(center,r_inner, r_outer,theta2/180*pi,theta1/180*pi)
  return patch, new_pos

def add_straight(cur_pos):  
  trafo = affine_trafo(straight[0],straight[1],cur_pos[0],cur_pos[1])  
  st0 = [trafo(p).tolist()[0] for p in straight]  
  patch = straight(st0)
  new_pos = (st0[3],st0[2])
  return patch, new_pos












app = dash.Dash(external_stylesheets=[dbc.themes.BOOTSTRAP]#,
    #            meta_tags=[
    #    {"name": "viewport", "content": "width=device-width, initial-scale=1"}
    #]
    )

title = dash.html.H1("Duplo Schienen Designer")

controls = dbc.Row(
            [
                dbc.Col(dash.html.Button('\U000021B0',id="add_left")),
                dbc.Col(dash.html.Button('\U00002191',id="add_straight")),
                dbc.Col(dash.html.Button('\U000021B1',id="add_right")),
                dbc.Col(dash.html.Button('\U0000274C',id="remove"))
            ]
        )

shapes0 = []


print("hi")
    
@dash.callback(
    dash.Output('mygraph', 'figure'),
    dash.Input('add_left', 'n_clicks')
)
def update(input_value): 
    global shapes0, pos0
    
    print("hi")
    
#    if input_value > 0:
    wedge0, new_pos = add_curve_left(pos0[-1])
    
    pos0 += [new_pos]
    
    new_shape = dict(type="path", path=wedge0, line={"color":"black"})
    
    shapes0 += [new_shape]
    
    fig0 = go.Figure()
    fig0.update_layout(template="none",
                       xaxis=axis_dict,
                       yaxis=axis_dict,
                       xaxis_range=[-20,20], yaxis_range=[-20,20],
                       shapes = shapes0)
    
  #  fig0.layout._config= config

    return fig0


# @dash.callback(
#     dash.Output('mygraph', 'figure'),
#     dash.Input('add_straight', 'n_clicks')
# )
# def update2(input_value): 
#     global shapes0, pos0
    
#     if input_value > 0:
#         wedge0, new_pos = add_straight(pos0[-1])
        
#         pos0 += [new_pos]
        
#         new_shape = dict(type="path", path=wedge0)
        
#         shapes0 += [new_shape]
    
#     fig0 = go.Figure()
#     fig0.update_layout(template="none",
#                        xaxis=axis_dict,
#                        yaxis=axis_dict,
#                        xaxis_range=[0,20], yaxis_range=[0,20],
#                        shapes = shapes0)
    
# #    fig0.layout._config= config

#     return fig0

#config = {'responsive': True}

axis_dict =dict(
    #visible = False,
                showgrid=False,
                showticklabels=False,
                mirror=True,
                ticks="",
         linewidth=1,
         linecolor='black',
                showline=True
                )

axis_dict = dict()

fig0 = go.Figure()
fig0.update_layout(template="none",
                   xaxis=axis_dict,
                   yaxis=axis_dict,
                   xaxis_range=[-20,20], yaxis_range=[-20,20],
                   shapes = shapes0)
    
#fig0.layout._config= config

plot = dash.dcc.Graph(
      id='mygraph',
      figure = fig0#,
      #responsive  = True,
      #style={'width': '90vw', 'height': '90vh'}
  )

app.layout = dbc.Container(
    [
     title,
     controls,
    plot
     ]
    )

app_for_wsgi = app.server

if __name__ == "__main__":
    app.run_server()