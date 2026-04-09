import numpy as np

INPUT_CSV = "data/observations.csv"
OUTPUT_DIR = "data"

RNG = np.random.default_rng(42)

BASE_SIGNAL_COLUMNS = [
    "mycityair_aqi_mean",
    "mycityair_aqi_max",
    "mycityair_aqi_min",
    "mycityair_station_count",
    "mycityair_obs_count",
    "plume_index",
    "plume_pm25",
    "plume_pm10",
    "plume_no2",
    "plume_so2",
    "plume_o3",
    "plume_co",
]

COUNT_COLUMNS = [
    "mycityair_station_count",
    "mycityair_obs_count",
]

DEFAULT_FEATURE_COLUMNS = [
    "mycityair_aqi_mean",
    "mycityair_aqi_max",
    "mycityair_aqi_min",
    "mycityair_station_count",
    "mycityair_obs_count",
    "plume_index",
    "plume_pm25",
    "plume_pm10",
    "plume_no2",
    "plume_so2",
    "plume_o3",
    "plume_co",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
    "month_sin",
    "month_cos",
    "day_of_year_sin",
    "day_of_year_cos",
    "is_weekend",
    "missing_count_total",
    "missing_ratio_total",
    "mycityair_aqi_mean_missing",
    "mycityair_aqi_max_missing",
    "mycityair_aqi_min_missing",
    "plume_index_missing",
    "plume_pm25_missing",
    "plume_pm10_missing",
    "plume_no2_missing",
    "plume_so2_missing",
    "plume_o3_missing",
    "plume_co_missing",
]

DEFAULT_TARGET_COLUMNS = [
    "mycityair_aqi_mean",
    "plume_pm25",
    "plume_pm10",
    "plume_no2",
    "plume_so2",
    "plume_o3",
    "plume_co",
    "plume_index",
]
