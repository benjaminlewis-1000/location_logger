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

visited = df[df.visited]
visit_states = visited.state.tolist()
visit_year = visited.year.tolist()


fig = px.choropleth(locations=visit_states, locationmode="USA-states", color=visit_year, scope="usa")

fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})

fig.show()
# fig = go.Figure(data=go.Scattergeo(
#     lon=df['Lon_84'],
#     lat=df['Lat_84'],
#     text=df['text'],
#     mode='markers',
#     marker_color=df['year']
# ))

# df = pd.read_csv('Geothermals.csv')
# df['text'] = df['Name'] + ', ' + df['State']
