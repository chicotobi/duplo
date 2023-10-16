from geometry import add_curve_left, add_curve_right, add_straight, get_front_arrow
from dash import Dash, html, ctx, callback, Input, Output, dcc

from dash_bootstrap_components import Row, Col, Container, themes
import plotly.graph_objects as go

from track import Track

# State variables
pos0 = [(-0.5,0),(0.5,0)]
tracks = []

app = Dash(external_stylesheets=[themes.BOOTSTRAP],
                meta_tags=[ {"name": "viewport", "content": "width=device-width, initial-scale=1"} ]
    )

title = html.H1("Duplo Schienen Designer")

Output('refresh_button', 'children')

arrow_left     = "\U000021B0"
arrow_straight = "\U00002191"
arrow_right    = "\U000021B1"
cross_remove   = "\U0000274C"
bomb_reset     = "\U0001F4A3"

def get_label_arrow_left(tracks):
  return arrow_left + "x" + str(sum(1 for i in tracks if i.ttype == 'curve'))
  
def get_label_arrow_right(tracks):
  return arrow_right + "x" + str(sum(1 for i in tracks if i.ttype == 'curve'))
  
def get_label_arrow_straight(tracks):
  return arrow_straight + "x" + str(sum(1 for i in tracks if i.ttype == 'straight'))

controls = Row([
                Col(html.Button(get_label_arrow_left(tracks),id="add_left")),
                Col(html.Button(get_label_arrow_straight(tracks),id="add_straight")),
                Col(html.Button(get_label_arrow_right(tracks),id="add_right")),
                Col(html.Button(cross_remove,id="remove")),
                Col(html.Button(bomb_reset,id="reset"))                
            ],className="g-0")

def create_figure(shapes=[]):
    axis_dict = dict(showgrid=False, showticklabels=False, visible = False, ticks="")
    fig0 = go.Figure()
    fig0.update_layout(template="none",
                        xaxis=axis_dict,
                        yaxis=axis_dict,
                        xaxis_range=[-20,20], yaxis_range=[-20,20],
                        margin = go.layout.Margin(l = 0, r = 0, b = 0, t = 0),
                        shapes = shapes)    
    fig0.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig0
    
@callback(
    Output('mygraph', 'figure'),
    Output('add_left', 'children'),
    Output('add_straight', 'children'),
    Output('add_right', 'children'),
    Input('add_left', 'n_clicks'),
    Input('add_right', 'n_clicks'),
    Input('add_straight', 'n_clicks'),
    Input('remove', 'n_clicks'),
    Input('reset', 'n_clicks'),
    prevent_initial_call=True
)
def update(b1, b2, b3, b4, b5): 
    global tracks
    
    if len(tracks) > 0:
        cur_pos = tracks[-1].ending
    else:
        cur_pos = pos0
        
    if ctx.triggered_id == 'remove' and len(tracks):
        if len(tracks) > 0:
            tracks.pop()
    elif ctx.triggered_id == 'reset':
        tracks = []
    else:
        if ctx.triggered_id == 'add_left':
            new_shape, new_pos = add_curve_left(cur_pos)
            tracks += [Track(ttype = "curve", ending = new_pos, shape = new_shape)]
        elif ctx.triggered_id == 'add_right':
            new_shape, new_pos = add_curve_right(cur_pos)    
            tracks += [Track(ttype = "curve", ending = new_pos, shape = new_shape)]
        elif ctx.triggered_id == 'add_straight':
            new_shape, new_pos = add_straight(cur_pos)  
            tracks += [Track(ttype = "straight", ending = new_pos, shape = new_shape)]
    
    if len(tracks) > 0:
        cur_pos = tracks[-1].ending
    else:
        cur_pos = pos0
        
    front_arrow = get_front_arrow(cur_pos)
        
    track_shapes = [i.shape for i in tracks]
    
    fig = create_figure(track_shapes + [front_arrow])
    label_arrow_left     = get_label_arrow_left(tracks)
    label_arrow_straight = get_label_arrow_straight(tracks)
    label_arrow_right    = get_label_arrow_right(tracks)
    
    return fig, label_arrow_left, label_arrow_straight, label_arrow_right

fig0 = create_figure()

plot = dcc.Graph(id='mygraph', figure = fig0, style={'width': '90vw', 'height': '90vh'})
plot_with_border = html.Div(plot, style={"border":"2px black solid"})

app.layout = Container([title, controls, plot_with_border], fluid=True,
                           style={"touch-action": "manipulation"})

app_for_wsgi = app.server

if __name__ == "__main__":
    app.run_server()