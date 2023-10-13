from geometry import add_curve_left, add_curve_right, add_straight, get_front_arrow
from dash import Dash, html, ctx, callback, Input, Output, dcc

from dash_bootstrap_components import Row, Col, Container, themes
import plotly.graph_objects as go

pos0 = [[(19.5,20),(20.5,20)]]

app = Dash(external_stylesheets=[themes.BOOTSTRAP],
                meta_tags=[ {"name": "viewport", "content": "width=device-width, initial-scale=1"} ]
    )

title = html.H1("Duplo Schienen Designer")

controls = Row([
                Col(html.Button('\U000021B0',id="add_left")),
                Col(html.Button('\U00002191',id="add_straight")),
                Col(html.Button('\U000021B1',id="add_right")),
                Col(html.Button('\U0000274C',id="remove")),
                Col(html.Button('\U0001F4A3',id="reset"))
                
            ])

track_shapes = []

def create_figure(shapes=[]):
    axis_dict = dict(showgrid=False, showticklabels=False, visible = False, ticks="")
    fig0 = go.Figure()
    fig0.update_layout(template="none",
                        xaxis=axis_dict,
                        yaxis=axis_dict,
                        xaxis_range=[0,40], yaxis_range=[0,40],
                        margin = go.layout.Margin(l = 0, r = 0, b = 0, t = 0),
                        shapes = shapes)    
    fig0.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig0
    
@callback(
    Output('mygraph', 'figure'),
    Input('add_left', 'n_clicks'),
    Input('add_right', 'n_clicks'),
    Input('add_straight', 'n_clicks'),
    Input('remove', 'n_clicks'),
    Input('reset', 'n_clicks'),
    prevent_initial_call=True
)
def update(b1, b2, b3, b4, b5): 
    global track_shapes, pos0
    
    if ctx.triggered_id == 'remove':
        track_shapes.pop()
        pos0.pop()
    elif ctx.triggered_id == 'reset':
        track_shapes = []
        pos0 = [pos0[0]]
    else:
        cur_pos = pos0[-1]
        if ctx.triggered_id == 'add_left':
            new_shape, new_pos = add_curve_left(cur_pos)        
        elif ctx.triggered_id == 'add_right':
            new_shape, new_pos = add_curve_right(cur_pos)     
        elif ctx.triggered_id == 'add_straight':
            new_shape, new_pos = add_straight(cur_pos)  
        pos0 += [new_pos]
        track_shapes += [new_shape]          
    
    front_arrow = get_front_arrow(pos0[-1])
    
    return create_figure(track_shapes + [front_arrow])


fig0 = create_figure()

plot = dcc.Graph(id='mygraph', figure = fig0, style={'width': '90vw', 'height': '90vh'})
plot_with_border = html.Div(plot, style={"border":"2px black solid"})

app.layout = Container([title, controls, plot_with_border], fluid=True,
                           style={"touch-action": "manipulation"})

app_for_wsgi = app.server

if __name__ == "__main__":
    app.run_server()