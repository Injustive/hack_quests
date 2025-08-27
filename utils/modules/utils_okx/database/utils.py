from sqlalchemy import Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .models import OkxConfigAbstractModel

_create_model_cache = {}

def create_okx_models(model, model_tablename, okx_account):
    main_table_name = f"okx_{model_tablename}_{okx_account}"
    config_table_name = f"okx_{model_tablename}_config_{okx_account}"
    cache_key = (main_table_name, config_table_name)
    if cache_key in _create_model_cache:
        return _create_model_cache[cache_key]
    main_class_name = f"DynamicOkxModel_{okx_account}"
    config_class_name = f"DynamicOkxConfigModel_{okx_account}"
    main_type_dict = {
        "__tablename__": main_table_name,
        "__table_args__": {"extend_existing": True}
    }
    DynamicOkxModel = type(main_class_name, (model,), main_type_dict)
    config_type_dict = {
        "__tablename__": config_table_name,
        "__table_args__": {"extend_existing": True}
    }
    DynamicOkxConfigModel = type(config_class_name, (OkxConfigAbstractModel,), config_type_dict)
    _create_model_cache[cache_key] = (DynamicOkxModel, DynamicOkxConfigModel)
    return DynamicOkxModel, DynamicOkxConfigModel


_get_model_cache = {}

def get_okx_models(model, main_table_name, config_table_name, subaccount):
    cache_key = (main_table_name, config_table_name)
    if cache_key in _get_model_cache:
        return _get_model_cache[cache_key]
    main_class_name = f"MainModel_{subaccount}"
    config_class_name = f"ConfigModel_{subaccount}"
    main_type_dict = {
        "__tablename__": main_table_name,
        "__table_args__": {"extend_existing": True},
    }
    MainModel = type(main_class_name, (model,), main_type_dict)
    config_type_dict = {
        "__tablename__": config_table_name,
        "__table_args__": {"extend_existing": True},
    }
    ConfigModel = type(config_class_name, (OkxConfigAbstractModel,), config_type_dict)
    _get_model_cache[cache_key] = (MainModel, ConfigModel)
    return MainModel, ConfigModel

def pair_okx_tables(tables, prefix):
    grouped = {}
    for table in tables:
        if not table.startswith(prefix):
            continue
        suffix = table[len(prefix):]
        if suffix.startswith("config_"):
            subaccount = suffix[len("config_"):]
            table_type = "config"
        else:
            subaccount = suffix
            table_type = "main"
        if subaccount not in grouped:
            grouped[subaccount] = {"main": None, "config": None}
        grouped[subaccount][table_type] = table
    pairs = []
    for subaccount, tables in grouped.items():
        if tables["main"] and tables["config"]:
            pairs.append((tables["main"], tables["config"], subaccount))
    return pairs