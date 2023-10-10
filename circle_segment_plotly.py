import numpy as np
from numpy import pi, sin, cos
import plotly.graph_objects as go

import plotly.io as pio
pio.renderers.default='browser'

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

wedge0 = wedge([1, 0], 1, 1.4, pi/6, 2*pi/6)

fig = go.Figure()
fig.update_layout(width=700, height=500,
                  xaxis_range=[0,2], yaxis_range=[-2, 2],
                  shapes=[dict(type="path",
                               path=wedge0,
                               fillcolor="LightPink",
                               line_color="Crimson")
                         ])
fig.update_yaxes(scaleanchor = "x", #IMPORTANT These yaxis settings ensure that the circle is non-deformed
                 scaleratio = 1)
fig.show()