"""Validate packaged YAML, Python source loading, and SDK tool registration."""
from pathlib import Path
import os
import sys

root = Path(__file__).resolve().parents[1]
os.chdir(root / 'plugin')
sys.path.insert(0, str(root / 'plugin'))
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration

registration = PluginRegistration(DifyPluginEnv())
assert registration.configuration.name == 'dmn_decision'
assert list(registration.tools_mapping) == ['dmn']
assert list(registration.tools_mapping['dmn'][2]) == ['evaluate']
print('SDK manifest, provider and Tool classes loaded successfully')
