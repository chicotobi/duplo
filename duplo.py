from geometry import add_curve_left, add_curve_right, add_straight, get_front_arrow
from dash import Dash, html, ctx, callback, Input, Output, dcc

from dash_bootstrap_components import Row, Col, Container, themes
import plotly.graph_objects as go

# State variables
pos0 = [[(-0.5,0),(0.5,0)]]
track_shapes = []
n_curves = 0
n_straight = 0

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

label_arrow_left     = arrow_left     + "x" + str(n_curves)
label_arrow_straight = arrow_straight + "x" + str(n_straight)
label_arrow_right    = arrow_right    + "x" + str(n_curves)

controls = Row([
                Col(html.Button(label_arrow_left,id="add_left")),
                Col(html.Button(label_arrow_straight,id="add_straight")),
                Col(html.Button(label_arrow_right,id="add_right")),
                Col(html.Button(cross_remove,id="remove")),
                Col(html.Button(bomb_reset,id="reset"))                
            ])

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
    global track_shapes, pos0, n_straight, n_curves
    
    if ctx.triggered_id == 'remove':
        track_shapes.pop()
        pos0.pop()
    elif ctx.triggered_id == 'reset':
        track_shapes = []
        pos0 = [pos0[0]]
    else:
        cur_pos = pos0[-1]
        if ctx.triggered_id == 'add_left':
            n_curves += 1
            new_shape, new_pos = add_curve_left(cur_pos)        
        elif ctx.triggered_id == 'add_right':
            n_curves += 1
            new_shape, new_pos = add_curve_right(cur_pos)     
        elif ctx.triggered_id == 'add_straight':
            n_straight += 1
            new_shape, new_pos = add_straight(cur_pos)  
        pos0 += [new_pos]
        track_shapes += [new_shape]          
    
    front_arrow = get_front_arrow(pos0[-1])
        
    fig = create_figure(track_shapes + [front_arrow])
    label_arrow_left     = arrow_left     + "x" + str(n_curves)
    label_arrow_straight = arrow_straight + "x" + str(n_straight)
    label_arrow_right    = arrow_right    + "x" + str(n_curves)
    
    return fig, label_arrow_left, label_arrow_straight, label_arrow_right

fig0 = create_figure()

plot = dcc.Graph(id='mygraph', figure = fig0, style={'width': '90vw', 'height': '90vh'})
plot_with_border = html.Div(plot, style={"border":"2px black solid"})

app.layout = Container([title, controls, plot_with_border], fluid=True,
                           style={"touch-action": "manipulation"})

app_for_wsgi = app.server

if __name__ == "__main__":
    app.run_server()