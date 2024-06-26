from geometry import add_curve_left, add_curve_right, add_straight, get_front_arrow, ending0
from dash import Dash, html, ctx, callback, Input, Output, dcc

from dash_bootstrap_components import Row, Col, Container, themes
import plotly.graph_objects as go

# State variables
tracks = []

def get_label_arrow_left(tracks):
  n_curve = sum(1 for i in tracks if i.ttype == 'curve')
  return "\N{upwards arrow with tip leftwards} x" + str(n_curve)

def get_label_arrow_right(tracks):
  n_curve = sum(1 for i in tracks if i.ttype == 'curve')
  return "\N{upwards arrow with tip rightwards} x" + str(n_curve)

def get_label_arrow_straight(tracks):
  n_straight = sum(1 for i in tracks if i.ttype == 'straight')
  return "\N{upwards arrow} x" + str(n_straight)

def get_label_remove():
  return "\N{cross mark}"

def get_label_reset():
  return "\N{bomb}"

def get_label_next_ending():
  return "\N{black right-pointing double triangle with vertical bar}"

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
  global tracks ending_idx

  # Collect endings
  endings = [a for tr in tracks for (a,b) in zip(tr.ending,tr.ending_taken) if not b ]

  if len(tracks) > 0:
    cur_pos = endings[-1]
  else:
    cur_pos = ending0

  if ctx.triggered_id == 'remove':
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

  if len(tracks) == 1:
    tracks[0].ending_taken[0] = False

  # Collect endings
  endings = [a for tr in tracks for (a,b) in zip(tr.ending,tr.ending_taken) if not b ]

  if len(endings) > 0:
    cur_pos = endings[-1]
  else:
    cur_pos = ending0

  front_arrow = get_front_arrow(cur_pos)

  track_shapes = [front_arrow] + [i.shape for i in tracks]

  fig = create_figure(track_shapes )
  label_arrow_left     = get_label_arrow_left(tracks)
  label_arrow_straight = get_label_arrow_straight(tracks)
  label_arrow_right    = get_label_arrow_right(tracks)

  return fig, label_arrow_left, label_arrow_straight, label_arrow_right

def get_app():
  app = Dash(external_stylesheets=[themes.BOOTSTRAP],
             meta_tags=[ {"name": "viewport", "content": "width=device-width, initial-scale=1"} ]
             )

  title = html.H1("Duplo Schienen Designer")

  fig0 = create_figure([get_front_arrow(ending0)])

  controls = Row([
    Col(html.Button(get_label_arrow_left(tracks),id="add_left")),
    Col(html.Button(get_label_arrow_straight(tracks),id="add_straight")),
    Col(html.Button(get_label_arrow_right(tracks),id="add_right")),
    Col(html.Button(get_label_remove(),id="remove")),
    Col(html.Button(get_label_reset(),id="reset"))
    ],className="g-0")

  plot = dcc.Graph(id='mygraph', figure = fig0, style={'width': '90vw', 'height': '90vh'})
  plot_with_border = html.Div(plot, style={"border":"2px black solid"})

  app.layout = Container([title, controls, plot_with_border],
                         fluid=True,
                         style={"touch-action": "manipulation"})
  return app

app = get_app()
app_for_wsgi = app.server

if __name__ == "__main__":
    app.run_server()
