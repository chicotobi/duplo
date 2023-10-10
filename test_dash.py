import dash_bootstrap_components as dbc
from dash import Dash, html

row = dbc.Row(
            [
                dbc.Col(html.Button('\U000021B0')),
                dbc.Col(html.Button('\U00002191')),
                dbc.Col(html.Button('\U000021B1')),
                dbc.Col(html.Button('\U0000274C'))
            ]
        )

app = Dash(external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = dbc.Container(row,
    className="p-5",
)

app_for_wsgi = app.server

if __name__ == "__main__":
    app.run_server()