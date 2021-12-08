import os
import sys
import argparse
parser = argparse.ArgumentParser(description="Utilities for Gluu CE")
parser.add_argument('-load-ldif', help="Loads ldif file to persistence")
argsp = parser.parse_args()

#first import paths and make changes if necassary
from setup_app import paths

#for example change log file location:
paths.LOG_FILE = os.path.join(paths.INSTALL_DIR, 'logs/setup-utils.log')

from setup_app import static

# second import module base, this makes some initial settings
from setup_app.utils import base

# we will access args via base module
base.argsp = argsp

from setup_app.utils.package_utils import packageUtils
packageUtils.check_and_install_packages()

from setup_app.messages import msg
from setup_app.config import Config
from setup_app.static import BackendTypes
from setup_app.utils.setup_utils import SetupUtils
from setup_app.utils.collect_properties import CollectProperties
from setup_app.installers.gluu import GluuInstaller
Config.init(paths.INSTALL_DIR)
Config.determine_version()

# we must initilize SetupUtils after initilizing Config
SetupUtils.init()

collectProperties = CollectProperties()

if os.path.exists(Config.gluu_properties_fn):
    collectProperties.collect()
    Config.installed_instance = True
else:
    print("Gluu Server installation was not found")
    sys.exit()

gluuInstaller = GluuInstaller()

class SetupUtilities:

    def __init__(self):
        pass

    def load_ldif(self, ldif_fn):
        if not os.path.exists(ldif_fn):
            print("Can't file", ldif_fn)
            return
        print("Loading ldif file", ldif_fn)
        gluuInstaller.dbUtils.import_ldif([ldif_fn])

setupUtilities = SetupUtilities()
if argsp.load_ldif:
    setupUtilities.load_ldif(argsp.load_ldif)
