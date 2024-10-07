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
import csv
import errno
import json
import sys
import os
from pathlib import Path
from io import StringIO
from zalfmas_common import common
from zalfmas_common.model import monica_io
import zalfmas_capnpschemas
sys.path.append(str(Path(os.path.dirname(zalfmas_capnpschemas.__file__))))
import common_capnp
import model_capnp
import soil_capnp
import climate_capnp

async def main():

    config = {
        "sim.json": os.path.join(os.path.dirname(__file__), "sim.json"),
        "crop.json": os.path.join(os.path.dirname(__file__), "crop.json"),
        "site.json": os.path.join(os.path.dirname(__file__), "site.json"),
        "climate.csv": os.path.join(os.path.dirname(__file__), "climate/Gera-Leumnitz_DS_REFERENZ_TW_2020_1612_1961-01-01_2020-12-31.csv"),
        #"monica_sr": "capnp://VPRTzs3dLITFlLjsB6RvUTn6BGoG26_9sgn2NLoDauQ@10.10.88.69:36199/b9c9cb56-f969-4a5c-9bf2-4eed26f67e27",
        "monica_sr": "capnp://T6SMqSvAVGo5uMnXV7j9lHHbr9vIF9J9lJFc2wSIlAM@10.10.25.19:9920/monica",
        "time_series_sr": "capnp://Zsk-czXFwF8hwu0wpsxf8N22L7uohKMf00WDL2H0_xw=@10.10.88.69:45722/5a19ce5a-dd3d-48b3-a23b-d3cb10f64310",
        "soil_sr": "capnp://localhost:9921/w_in",
        "out": os.path.join(os.path.dirname(__file__), "out"),
        "debugout": "debug_out",
        "writenv": True,
    }
    common.update_config(config, sys.argv, print_config=True, allow_new_keys=False)

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
    env_template["csvViaHeaderOptions"] = sim_json["climate.csv-options"]
    env_template["pathToClimateCSV"] = config["climate.csv"]

    if config["writenv"] :
        filename = os.path.join(os.path.dirname(__file__), config["debugout"], 'generated_env.json')
        WriteEnv(filename, env_template)

    conman = common.ConnectionManager()
    #soil_service = await conman.try_connect(config["soil_sr"], cast_as=soil_capnp.Service, retry_secs=1)
    monica_service = await conman.try_connect(config["monica_sr"], cast_as=model_capnp.EnvInstance, retry_secs=1)
    time_series = await conman.try_connect(config["time_series_sr"], cast_as=climate_capnp.TimeSeries, retry_secs=1)

    #soil_profiles = (await soil_service.closestProfilesAt(coord={"lat": 54, "lon": 12}, query={
    #    "mandatory": ["soilType", "sand", "clay", "organicCarbon",
    #                  "bulkDensity"],
    #    "optional": ["pH"]})).profiles

    #capnp_env = model_capnp.Env.new_message()
    #capnp_env.timeSeries = time_series
    #capnp_env.soilProfile = soil_profiles[0]
    #capnp_env.rest = common_capnp.StructuredText.new_message()
    #capnp_env.rest = common_capnp.StructuredText.new_message(value=json.dumps(env_template),
    #                                                         structure={"json": None})
    # res = (await monica_service.run(env=capnp_env)).result

    rr = monica_service.run_request()
    env = rr.init("env")
    env.timeSeries = time_series
    env.rest = common_capnp.StructuredText.new_message(value=json.dumps(env_template),
                                                       structure={"json": None})
    res = (await rr.send()).result
    stv = res.as_struct(common_capnp.StructuredText).value
    print(stv)
    res_json = json.loads(stv)
    csvs = create_csv(res_json)
    for section_name, csv_content in csvs:
        if not os.path.exists(config["out"]):
            os.makedirs(config["out"])
        with open(Path(config["out"]) / f"{section_name}.csv", "w", newline="") as _:
            _.write(csv_content)

    print("done")


def WriteEnv(filename, env) :
    if not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise
    with open(filename, 'w') as outfile:
        json.dump(env, outfile)


def create_csv(msg, delimiter=",", include_header_row=True, include_units_row=True, include_time_agg=False):
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
            for row in monica_io.write_output(output_ids, results):
                writer.writerow(row)

        out.append((orig_spec.replace("\"", ""), sio.getvalue()))
    return out


if __name__ == '__main__':
    asyncio.run(capnp.run(main()))
