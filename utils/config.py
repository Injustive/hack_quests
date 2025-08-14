import yaml
from .paths import CONFIG_PATH
from types import SimpleNamespace


def dict_to_namespace(d):
    if isinstance(d, dict):
        return SimpleNamespace(**{k: dict_to_namespace(v) for k, v in d.items()})
    return d

def load_config():
    with open(CONFIG_PATH, "r") as file:
        config_dict = yaml.safe_load(file)
    return dict_to_namespace(config_dict)

CONFIG = load_config()
