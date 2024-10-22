#!/usr/bin/python
# -*- coding: UTF-8

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/. */

# Authors:
# Michael Berg-Mohnicke <michael.berg@zalf.de>
#
# Maintainers:
# Currently maintained by the authors.
#
# Copyright (C: Leibniz Centre for Agricultural Landscape Research (ZALF)

import asyncio
import capnp
from collections import defaultdict
import csv
import errno
from io import StringIO
import json
import math
import os
from pathlib import Path
import sys
import zmq
from zalfmas_common import common
from zalfmas_common.model import monica_io
import zalfmas_capnp_schemas
sys.path.append(os.path.dirname(zalfmas_capnp_schemas.__file__))
import common_capnp
import model_capnp
import soil_capnp
import climate_capnp


async def main():

    config = {
        "sim.json": os.path.join(os.path.dirname(__file__), "sim.json"),
        "crop.json": os.path.join(os.path.dirname(__file__), "crop.json"),
        "site.json": os.path.join(os.path.dirname(__file__), "site.json"),
        #"monica_sr": "capnp://VPRTzs3dLITFlLjsB6RvUTn6BGoG26_9sgn2NLoDauQ@10.10.88.69:36199/b9c9cb56-f969-4a5c-9bf2-4eed26f67e27",
        "monica_sr": "capnp://localhost:9920/monica",
        "time_series_sr": "capnp://Zsk-czXFwF8hwu0wpsxf8N22L7uohKMf00WDL2H0_xw=@10.10.88.69:45722/5a19ce5a-dd3d-48b3-a23b-d3cb10f64310",
        "soil_sr": "capnp://localhost:9981/buek200",
        "out": os.path.join(os.path.dirname(__file__), "out"),
    }
    common.update_config(config, sys.argv, print_config=True, allow_new_keys=False)

    ws_data = [
        {"name": "dd-klotzsche", "sr": "capnp://localhost:9991/klotzsche", "cap": None, "lat_lon": (51.1348, 13.8303)},
        {"name": "gera", "sr": "capnp://localhost:9992/gera", "cap": None, "lat_lon": (50.8766, 12.1460)},
        {"name": "laucha-unstrut", "sr": "capnp://localhost:9993/laucha", "cap": None, "lat_lon": (51.2481, 11.7179)},
        {"name": "naumburg", "sr": "capnp://localhost:9994/naumburg", "cap": None, "lat_lon": (51.1239, 11.8225)},
        {"name": "plauen", "sr": "capnp://localhost:9995/plauen", "cap": None, "lat_lon": (50.59526, 12.19376)},
        {"name": "zeitz", "sr": "capnp://localhost:9996/zeitz", "cap": None, "lat_lon": (51.0229, 12.1590)},
    ]

    use_exact_co2_measurements = False
    co2_measurements = {
        1997: 376.16,
        1998: 377.30,
        1999: 382.13,
        2000: 382.09,
        2001: 383.77,
        2002: 380.62,
        2003: 382.35,
        2004: 382.63,
        2005: 382.27,
        2006: 388.52,
        2007: 391.67,
        2008: 394.00,
        2009: 394.00,
        2010: 400.58,
        2011: 401.55,
        2012: 405.27,
        2013: 403.91,
        2014: 406.88,
        2015: 411.04,
        2016: 416.83,
        2017: 418.96,
        2018: 419.58,
        2019: 420.69,
        2020: 423.10,
        2021: 427.66,
        2022: 429.34,
        2023: 430.28,
    }

    with open(config["sim.json"]) as _:
        sim_json = json.load(_)
    sim_json["include-file-base-path"] = os.path.join(os.path.dirname(__file__), "monica_parameters")

    with open(config["site.json"]) as _:
        site_json = json.load(_)

    with open(config["crop.json"]) as _:
        crop_json = json.load(_)

    env_template = monica_io.create_env_json_from_json_config({
        "crop": crop_json,
        "site": site_json,
        "sim": sim_json,
        "climate": "" #climate_csv
    })
    crops = env_template["cropRotations"]
    env_template["cropRotations"] = []
    #env_template["csvViaHeaderOptions"] = sim_json["climate.csv-options"]
    #env_template["pathToClimateCSV"] = config["climate.csv"]

    conman = common.ConnectionManager()
    soil_service = await conman.try_connect(config["soil_sr"], cast_as=soil_capnp.Service, retry_secs=1)
    #monica_service = await conman.try_connect(config["monica_sr"], cast_as=model_capnp.EnvInstance, retry_secs=1)
    #time_series = await conman.try_connect(config["time_series_sr"], cast_as=climate_capnp.TimeSeries, retry_secs=1)

    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect("tcp://localhost:6666")

    #capnp_env = model_capnp.Env.new_message()
    #capnp_env.timeSeries = time_series
    #capnp_env.soilProfile = soil_profiles[0]
    #capnp_env.rest = common_capnp.StructuredText.new_message()
    #capnp_env.rest = common_capnp.StructuredText.new_message(value=json.dumps(env_template),
    #                                                         structure={"json": None})
    # res = (await monica_service.run(env=capnp_env)).result

    year_to_co2 = {}
    def co2_f(year):
        return 0.0062*math.exp(0.0055*year)
    for year in range(1961, 2021):
        if year in co2_measurements and use_exact_co2_measurements:
            year_to_co2[year] = co2_measurements[year]
        else:
            year_to_co2[year] = co2_f(year)

    fetch_data = True
    wst_sr_to_caps = defaultdict(lambda: {"time_series": None, "ts_data": None,
                                          "soil_profile": None, "sp_data": None})
    for data in ws_data:
        if data["cap"] is None:
            ts_cap = await conman.try_connect(data["sr"], cast_as=climate_capnp.TimeSeries, retry_secs=1)
            if ts_cap is not None and fetch_data:
                ts_header = (await ts_cap.header()).header
                ts_range = await ts_cap.range()
                ts_data = (await ts_cap.dataT()).data
                data_ = {
                    "startDate": f"{ts_range.startDate.year:04d}-{ts_range.startDate.month:02d}-{ts_range.startDate.day:02d}",
                    "endDate": f"{ts_range.endDate.year:04d}-{ts_range.endDate.month:02d}-{ts_range.endDate.day:02d}",
                    "data": defaultdict(list),
                }
                for i, h in enumerate(ts_header):
                    if h == "tmin":
                        data_["data"]["3"] = list(ts_data[i])
                    elif h == "tavg":
                        data_["data"]["4"] = list(ts_data[i])
                    elif h == "tmax":
                        data_["data"]["5"] = list(ts_data[i])
                    elif h == "precip":
                        data_["data"]["6"] = list(ts_data[i])
                    elif h == "relhumid":
                        data_["data"]["12"] = list(ts_data[i])
                    elif h == "wind":
                        data_["data"]["9"] = list(ts_data[i])
                    elif h == "globrad":
                        data_["data"]["8"] = list(ts_data[i])
                wst_sr_to_caps[data["sr"]]["ts_data"] = data_
            wst_sr_to_caps[data["sr"]]["time_series"] = ts_cap

            if wst_sr_to_caps[data["sr"]]["time_series"] is None:
                print("Could not connect to time series service via sr:", data["sr"])
            lat, lon = data["lat_lon"]
            soil_profiles = (await soil_service.closestProfilesAt(coord={"lat": lat, "lon": lon}, query={
                "mandatory": ["soilType", "sand", "clay", "organicCarbon",
                              "bulkDensity"],
                "optional": ["pH"]})).profiles
            sp_cap = soil_profiles[0]
            if sp_cap is not None and fetch_data:
                sp_layers = (await sp_cap.data()).layers
                sp_data = []
                for layer in sp_layers:
                    layer_desc = {"Thickness": [layer.size, "m"]}
                    for prop in layer.properties:
                        if prop.name == "soilType" and prop.which == "type":
                            layer_desc["KA5TextureClass"] = prop.type
                        elif prop.name == "sand" and prop.which == "f32Value":
                            layer_desc["Sand"] = prop.f32Value / 100.0
                        elif prop.name == "clay" and prop.which == "f32Value":
                            layer_desc["Clay"] = prop.f32Value / 100.0
                        elif prop.name == "organicCarbon" and prop.which == "f32Value":
                            layer_desc["SoilOrganicCarbon"] = [prop.f32Value, "%"]
                        elif prop.name == "bulkDensity" and prop.which == "f32Value":
                            layer_desc["SoilBulkDensity"] = [prop.f32Value, "kg/m^3"]
                        elif prop.name == "pH" and prop.which == "f32Value":
                            layer_desc["pH"] = [prop.f32Value, "pH"]
                    sp_data.append(layer_desc)
                wst_sr_to_caps[data["sr"]]["sp_data"] = sp_data
            wst_sr_to_caps[data["sr"]]["soil_profile"] = sp_cap

    variants = []
    for data in ws_data:
        var = {
            "name": data["name"],
            "lat": data["lat_lon"][0],
            "sr": data["sr"],
        }
        for crop_id in ["WW", "SM"]:
            var2 = var.copy()
            var2["crop_id"] = crop_id

            for co2 in ["measured", 500, 1000]:
                var3 = var2.copy()
                var3["co2"] = co2

                for irrig in [True, False]:
                    var4 = var3.copy()
                    var4["irrig"] = irrig
                    variants.append(var4)

    for v, var in enumerate(variants):
        # set irrigations
        env_template["params"]["simulationParameters"]["UseAutomaticIrrigation"] = var["irrig"]

        # set latitude
        env_template["params"]["siteParameters"]["Latitude"] = var["lat"]

        # set CO2
        if var["co2"] == "measured":
            env_template["params"]["userEnvironmentParameters"]["AtmosphericCO2s"] = year_to_co2
        else:
            env_template["params"]["userEnvironmentParameters"]["AtmosphericCO2"] = var["co2"]

        env_template["customId"] = f"{v:02d}_{var['name']}_crop-{var['crop_id']}_co2-{var['co2']}_irr-{var['irrig']}"

        # set time series
        time_series_cap = wst_sr_to_caps[var["sr"]]["time_series"]
        if time_series_cap is None:
            continue
        if fetch_data:
            env_template["climateData"] = wst_sr_to_caps[var["sr"]]["ts_data"]

        # set soil profile
        soil_profile_cap = wst_sr_to_caps[var["sr"]]["soil_profile"]
        if soil_profile_cap is None:
            continue
        if fetch_data:
            env_template["params"]["siteParameters"]["SoilProfileParameters"] = wst_sr_to_caps[var["sr"]]["sp_data"]

        # set crop
        env_template["cropRotation"][0]["worksteps"][0]["crop"] = crops[var["crop_id"]]
        if var["crop_id"] == "SM":
            env_template["cropRotation"][0]["worksteps"][0]["earliest-date"] = "0000-04-01"
            env_template["cropRotation"][0]["worksteps"][0]["latest-date"] = "0000-06-01"
            env_template["cropRotation"][0]["worksteps"][1]["latest-date"] = "0000-10-31"
        elif var["crop_id"] == "WW":
            env_template["cropRotation"][0]["worksteps"][0]["earliest-date"] = "0000-09-16"
            env_template["cropRotation"][0]["worksteps"][0]["latest-date"] = "0000-11-08"
            env_template["cropRotation"][0]["worksteps"][1]["latest-date"] = "0001-09-15"

        # run MONICA
        if fetch_data:
            socket.send_json(env_template)
            res_json = socket.recv_json()
        else:
            rr = monica_service.run_request()
            env = rr.init("env")
            env.timeSeries = time_series_cap
            env.soilProfile = wst_sr_to_caps[var["sr"]]["soil_profile"]
            env.rest = common_capnp.StructuredText.new_message(value=json.dumps(env_template),
                                                               structure={"json": None})
            res = (await rr.send()).result
            st = res.as_struct(common_capnp.StructuredText)
            stv = res.as_struct(common_capnp.StructuredText).value
            print(stv)
            print("len(stv):", len(stv))
            res_json = json.loads(stv)

        csvs = create_csv(res_json, delimiter=";", round_ids={
            "Act_ET": 2,
            "ActTransp_mm": 2,
            "ActEvap_mm": 2,
            "Pot_ET": 2,
            "Evap_mm": 2,
            "ET_mm": 2,
            "Transp_mm": 2,
            "GWR_mm": 2,
            "ST_10cm": 2,
            "SM_0-20cm": 3,
            "NPP": 3,
            "GPP": 3,
            "Recharge": 2,
            "SoilTemp_10cm": 2
        })

        for section_name, csv_content in csvs:
            out_folder_path = config["out"] + "/" + env_template["customId"]
            if not os.path.exists(out_folder_path):
                os.makedirs(out_folder_path)
            with open(Path(out_folder_path) / f"{section_name}.csv", "w", newline="") as _:
                _.write(csv_content)
        print("Variant:", v, "->", env_template["customId"], "done")

    print("done")

def create_csv(msg, delimiter=",", include_header_row=True, include_units_row=True, include_time_agg=False,
               round_ids=None):
    out = []

    for section in msg.get("data", []):
        results = section.get("results", [])
        orig_spec = section.get("origSpec", "")
        output_ids = section.get("outputIds", [])

        sio = StringIO()
        writer = csv.writer(sio, delimiter=delimiter)

        if len(results) > 0:
            for row in monica_io.write_output_header_rows(output_ids,
                                                          include_header_row=include_header_row,
                                                          include_units_row=include_units_row,
                                                          include_time_agg=include_time_agg):
                writer.writerow(row)
            for row in monica_io.write_output(output_ids, results, round_ids=round_ids):
                writer.writerow(row)

        out.append((orig_spec.replace("\"", ""), sio.getvalue()))
    return out


if __name__ == '__main__':
    asyncio.run(capnp.run(main()))
