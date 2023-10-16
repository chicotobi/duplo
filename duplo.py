from geometry import add_curve_left, add_curve_right, add_straight, get_front_arrow, pos0
from dash import Dash, html, ctx, callback, Input, Output, dcc

from dash_bootstrap_components import Row, Col, Container, themes
import plotly.graph_objects as go

# State variables
tracks = []

def get_label_arrow_left(tracks):
  arrow_left = "\U000021B0"
  return arrow_left + "x" + str(sum(1 for i in tracks if i.ttype == 'curve'))

def get_label_arrow_right(tracks):
  arrow_right = "\U000021B1"
  return arrow_right + "x" + str(sum(1 for i in tracks if i.ttype == 'curve'))

def get_label_arrow_straight(tracks):
  arrow_straight = "\U00002191"
  return arrow_straight + "x" + str(sum(1 for i in tracks if i.ttype == 'straight'))

def get_label_remove():
  cross_remove = "\U0000274C"
  return cross_remove

def get_label_reset():
  bomb_reset = "\U0001F4A3"
  return bomb_reset

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
            new_track = add_curve_left(cur_pos)
        elif ctx.triggered_id == 'add_right':
            new_track = add_curve_right(cur_pos)
        elif ctx.triggered_id == 'add_straight':
            new_track = add_straight(cur_pos)
        tracks.append(new_track)

    if len(tracks) > 0:
        cur_pos = tracks[-1].ending
    else:
        cur_pos = pos0

    front_arrow = get_front_arrow(cur_pos)

    track_shapes = [i.shape for i in tracks] + [front_arrow]

    fig = create_figure(track_shapes )
    label_arrow_left     = get_label_arrow_left(tracks)
    label_arrow_straight = get_label_arrow_straight(tracks)
    label_arrow_right    = get_label_arrow_right(tracks)

    return fig, label_arrow_left, label_arrow_straight, label_arrow_right


app = Dash(external_stylesheets=[themes.BOOTSTRAP],
                meta_tags=[ {"name": "viewport", "content": "width=device-width, initial-scale=1"} ]
    )

title = html.H1("Duplo Schienen Designer")

fig0 = create_figure()

controls = Row([
                Col(html.Button(get_label_arrow_left(tracks),id="add_left")),
                Col(html.Button(get_label_arrow_straight(tracks),id="add_straight")),
                Col(html.Button(get_label_arrow_right(tracks),id="add_right")),
                Col(html.Button(get_label_remove(),id="remove")),
                Col(html.Button(get_label_reset(),id="reset"))
            ],className="g-0")

plot = dcc.Graph(id='mygraph', figure = fig0, style={'width': '90vw', 'height': '90vh'})
plot_with_border = html.Div(plot, style={"border":"2px black solid"})

app.layout = Container([title, controls, plot_with_border], fluid=True,
                           style={"touch-action": "manipulation"})

app_for_wsgi = app.server

if __name__ == "__main__":
    app.run_server()
