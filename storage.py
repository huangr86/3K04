import os
import json

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(BASE_DIR, "data")
USERS_JSON   = os.path.join(DATA_DIR, "users.json")
PARAMS_JSON  = os.path.join(DATA_DIR, "params.json")
USER_PARAMS_JSON = os.path.join(DATA_DIR, "user_params.json")


def ensure_files():
    """Create data/ and tiny JSON files if missing."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_JSON):
        with open(USERS_JSON, "w") as f:
            json.dump({"users": []}, f, indent=2)


def load_users():
    with open(USERS_JSON, "r") as f:
        return json.load(f)


def save_users(data):
    with open(USERS_JSON, "w") as f:
        json.dump(data, f, indent=2)


def load_user_params():
    if os.path.exists(USER_PARAMS_JSON):
        with open(USER_PARAMS_JSON, "r") as f:
            return json.load(f)
    return {}


def save_user_params(data):
    with open(USER_PARAMS_JSON, "w") as f:
        json.dump(data, f, indent=2)


def load_param_config():
    with open(PARAMS_JSON, "r") as f:
        cfg = json.load(f)

    schema_raw = cfg.get("schema", {})
    defaults   = cfg.get("defaults", {})
    modes      = cfg.get("modes", [])

    type_map = {"int": int, "float": float}

    schema = {}
    for key, meta in schema_raw.items():
        m = dict(meta)
        m["type"] = type_map.get(m.get("type", "int"), int)
        schema[key] = m

    return schema, defaults, modes
