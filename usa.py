# -*- coding: utf-8 -*-

# Run this app with `python app.py` and
# visit http://127.0.0.1:8050/ in your web browser.

import dash
import dash_core_components as dcc
import dash_html_components as html
import location_db
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import json
import config


app = dash.Dash(__name__)

with open(config.basic_county_json, 'rb') as geodata:
    counties = json.load(geodata)

database = location_db.locationDB(db_name=config.database_location, fips_file = config.county_fips_file)
df = database.get_state_visits_dataframe()


county_df = database.get_county_visits_dataframe()
# print(county_df)


fig = px.choropleth(county_df, geojson=counties, locations="FIPS", color='year',
                           color_continuous_scale='Viridis',
                           # range_color=(dmin, dmax),
                           scope="usa"
                          )
fig.update_layout(margin=dict(l=60, r=60, t=50, b=50))
fig.update_layout(
        autosize=True,
        coloraxis_colorbar_len=0.5,
        margin = dict(
                l=0,
                r=0,
                b=0,
                t=0,
                pad=4,
                autoexpand=True
            ),
            width=1600,
            height=900,
    )

app.layout = html.Div(children=[
    # html.H1(children='Identified Geothermal Systems of the Western USA'),
    # html.Div(children='''
    #     This data was provided by the USGS.
    # '''),

    dcc.Graph(
        id='example-map',
        figure=fig
    )
])

if __name__ == '__main__':
    app.run_server(debug=True, port=8080, host='0.0.0.0')
# fig = go.Figure(data=go.Scattergeo(
#     lon=df['Lon_84'],
#     lat=df['Lat_84'],
#     text=df['text'],
#     mode='markers',
#     marker_color=df['year']
# ))

# df = pd.read_csv('Geothermals.csv')
# df['text'] = df['Name'] + ', ' + df['State']
