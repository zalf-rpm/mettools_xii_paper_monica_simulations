#!/bin/bash

# time series
poetry run python -m zalfmas_services.climate.csv_time_series_service srt=klotzsche port=9991 \
path_to_csv_file=climate/DD-Klotzsche_DS_REFERENZ_TW_2020_1048_1961-01-01_2020-12-31.csv &

poetry run python -m zalfmas_services.climate.csv_time_series_service srt=gera port=9992 \
path_to_csv_file=climate/Gera-Leumnitz_DS_REFERENZ_TW_2020_1612_1961-01-01_2020-12-31.csv &

poetry run python -m zalfmas_services.climate.csv_time_series_service srt=laucha port=9993 \
path_to_csv_file=climate/Laucha-Unstrut_DS_REFERENZ_TW_2020_5424_1961-01-01_2020-12-31.csv &

poetry run python -m zalfmas_services.climate.csv_time_series_service srt=naumburg port=9994 \
path_to_csv_file=climate/Naumburg-Saale-Kreipitzsch_DS_REFERENZ_TW_2020_7420_1961-01-01_2020-12-31.csv &

poetry run python -m zalfmas_services.climate.csv_time_series_service srt=plauen port=9995 \
path_to_csv_file=climate/Plauen_DS_REFERENZ_TW_2020_3946_1961-01-01_2020-12-31.csv &

poetry run python -m zalfmas_services.climate.csv_time_series_service srt=zeitz port=9996 \
path_to_csv_file=climate/Zeitz_DS_REFERENZ_TW_2020_5750_1961-01-01_2020-12-31.csv &

#soil service
poetry run python -m zalfmas_services.soil.sqlite_soil_data_service \
srt=buek200 port=9981 path_to_sqlite_db=soil/buek200.sqlite \
path_to_ascii_soil_grid=soil/buek200_1000_25832_etrs89-utm32n.asc &