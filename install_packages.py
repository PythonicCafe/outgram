"""Read setup.cfg and run `pip` to install requirements (default and development)"""

import subprocess
from configparser import ConfigParser

config = ConfigParser()
config.read("setup.cfg")

requirements = []
requirements.extend(config.get("options", "install_requires", fallback="").strip().splitlines())
requirements.extend(config.get("options.extras_require", "dev", fallback="").strip().splitlines())
requirements.extend(config.get("options.extras_require", "img", fallback="").strip().splitlines())
if requirements:
    subprocess.call(["pip", "install", "--no-cache-dir"] + requirements)
