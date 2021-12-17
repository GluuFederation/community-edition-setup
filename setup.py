#!/usr/bin/python3
import warnings
warnings.filterwarnings("ignore")

import readline
import os
import sys
import time
import glob
import inspect
import zipfile
import shutil
import traceback
import code

from queue import Queue

os.environ['LC_ALL'] = 'C'
from setup_app.utils.arg_parser import arg_parser

argsp = arg_parser()

#first import paths and make changes if necassary
from setup_app import paths

#for example change log file location:
#paths.LOG_FILE = '/tmp/my.log'

from setup_app import static

# second import module base, this makes some initial settings
from setup_app.utils import base

# we will access args via base module
base.argsp = argsp

from setup_app.utils.package_utils import packageUtils
packageUtils.check_and_install_packages()

from setup_app.messages import msg
from setup_app.config import Config
from setup_app.utils.progress import gluuProgress


from setup_app.setup_options import get_setup_options
from setup_app.utils import printVersion

from setup_app.test_data_loader import TestDataLoader
from setup_app.utils.properties_utils import propertiesUtils
from setup_app.utils.setup_utils import SetupUtils
from setup_app.utils.collect_properties import CollectProperties

from setup_app.installers.gluu import GluuInstaller
from setup_app.installers.httpd import HttpdInstaller
from setup_app.installers.opendj import OpenDjInstaller
from setup_app.installers.couchbase import CouchbaseInstaller
from setup_app.installers.jre import JreInstaller
from setup_app.installers.jetty import JettyInstaller
from setup_app.installers.jython import JythonInstaller
from setup_app.installers.node import NodeInstaller
from setup_app.installers.oxauth import OxauthInstaller
from setup_app.installers.oxtrust import OxtrustInstaller
from setup_app.installers.scim import ScimInstaller
from setup_app.installers.passport import PassportInstaller
from setup_app.installers.fido import FidoInstaller
from setup_app.installers.saml import SamlInstaller
from setup_app.installers.radius import RadiusInstaller
from setup_app.installers.oxd import OxdInstaller
from setup_app.installers.casa import CasaInstaller
from setup_app.installers.rdbm import RDBMInstaller


if base.snap:
    try:
        open('/proc/mounts').close()
    except:
        print("Please execute the following command\n  sudo snap connect gluu-server:mount-observe :mount-observe\nbefore running setup. Exiting ...")
        sys.exit()

# initialize config object
Config.init(paths.INSTALL_DIR)
Config.determine_version()

# we must initilize SetupUtils after initilizing Config
SetupUtils.init()

# get setup options from args
setupOptions = get_setup_options()

terminal_size = shutil.get_terminal_size()
tty_rows=terminal_size.lines 
tty_columns = terminal_size.columns

# check if we are running in terminal
try:
    os.get_terminal_size()
except:
    argsp.no_progress = True


queue = Queue()
GSA = None

if (not argsp.c) and sys.stdout.isatty() and (int(tty_rows) > 24) and (int(tty_columns) > 79):
    try:
        import npyscreen
    except:
        print("Can't start TUI, continuing command line")
    else:
        from setup_app.utils.tui import GSA
        on_tui = True

if not argsp.n and not GSA:
    base.check_resources()


# pass progress indicator to Config object
Config.pbar = gluuProgress


for key in setupOptions:
    setattr(Config, key, setupOptions[key])


gluuInstaller = GluuInstaller()
gluuInstaller.initialize()


if not GSA and not os.path.exists(Config.gluu_properties_fn):
    print()
    print("Installing Gluu Server...\n\nFor more info see:\n  {}  \n  {}\n".format(paths.LOG_FILE, paths.LOG_ERROR_FILE))
    print("Detected OS     :  {} {} {}".format('snap' if base.snap else '', base.os_type, base.os_version))
    print("Gluu Version    :  {}".format(Config.oxVersion))
    print("Detected init   :  {}".format(base.os_initdaemon))
    print("Detected Apache :  {}".format(base.determineApacheVersion()))
    print()

setup_loaded = {}
if setupOptions['setup_properties']:
    base.logIt('%s Properties found!\n' % setupOptions['setup_properties'])
    setup_loaded = propertiesUtils.load_properties(setupOptions['setup_properties'])
elif os.path.isfile(Config.setup_properties_fn):
    base.logIt('%s Properties found!\n' % Config.setup_properties_fn)
    setup_loaded = propertiesUtils.load_properties(Config.setup_properties_fn)
elif os.path.isfile(Config.setup_properties_fn+'.enc'):
    base.logIt('%s Properties found!\n' % Config.setup_properties_fn+'.enc')
    setup_loaded = propertiesUtils.load_properties(Config.setup_properties_fn+'.enc')

if argsp.import_ldif and os.path.isdir(argsp.import_ldif):
    base.logIt("Found setup LDIF import directory {}".format(argsp.import_ldif))
else:
    base.logIt("The custom LDIF import directory {} does not exist. Exiting...".format(argsp.import_ldif, True, True))


collectProperties = CollectProperties()
if os.path.exists(Config.gluu_properties_fn):
    collectProperties.collect()
    Config.installed_instance = True

    if argsp.csx:
        print("Saving collected properties")
        collectProperties.save()
        sys.exit()


if not Config.noPrompt and not GSA and not Config.installed_instance and not setup_loaded:
    propertiesUtils.promptForProperties()

if not (GSA or base.argsp.dummy):
    propertiesUtils.check_properties()

# initialize installers, order is important!
jreInstaller = JreInstaller()
jettyInstaller = JettyInstaller()
jythonInstaller = JythonInstaller()
nodeInstaller = NodeInstaller()
openDjInstaller = OpenDjInstaller()
couchbaseInstaller = CouchbaseInstaller()
rdbmInstaller = RDBMInstaller()
httpdinstaller = HttpdInstaller()
oxauthInstaller = OxauthInstaller()
oxtrustInstaller = OxtrustInstaller()
fidoInstaller = FidoInstaller()
scimInstaller = ScimInstaller()
samlInstaller = SamlInstaller()
oxdInstaller = OxdInstaller()
casaInstaller = CasaInstaller()
passportInstaller = PassportInstaller()
radiusInstaller = RadiusInstaller()

rdbmInstaller.packageUtils = packageUtils

if Config.installed_instance:
    for installer in (openDjInstaller, couchbaseInstaller, httpdinstaller, 
                        oxauthInstaller, passportInstaller, scimInstaller, 
                        fidoInstaller, samlInstaller, oxdInstaller, 
                        casaInstaller, radiusInstaller, rdbmInstaller):

        setattr(Config, installer.install_var, installer.installed())

    if not GSA:
        propertiesUtils.promptForProperties()

        for service, arg in (
                        ('installSaml', 'install_shib'),
                        ('installPassport', 'install_passport'),
                        ('installGluuRadius', 'install_gluu_radius'),
                        ('installOxd', 'install_oxd'),
                        ('installCasa', 'install_casa'),
                        ('installScimServer', 'install_scim'),
                        ('installFido2', 'install_fido2')
                        ):
            if getattr(base.argsp, arg):
                Config.addPostSetupService.append(service)

                if service in Config.non_setup_properties['service_enable_dict']:
                    for attribute in Config.non_setup_properties['service_enable_dict'][service]:
                        setattr(Config, attribute, 'true')

            if 'installCasa' in Config.addPostSetupService and not 'installOxd' in Config.addPostSetupService and not oxdInstaller.installed():
                Config.addPostSetupService.append('installOxd')


        if not Config.addPostSetupService:
            print("No service was selected to install. Exiting ...")
            sys.exit()

if argsp.t or argsp.x:
    testDataLoader = TestDataLoader()
    testDataLoader.passportInstaller = passportInstaller
    testDataLoader.scimInstaller = scimInstaller

if argsp.x:
    print("Loading test data")
    testDataLoader.dbUtils.bind()
    testDataLoader.createLdapPw()
    testDataLoader.load_test_data()
    testDataLoader.deleteLdapPw()
    print("Test data loaded. Exiting ...")
    sys.exit()


if not GSA:

    if Config.ldap_install == static.InstallTypes.LOCAL and not Config.installed_instance:
        # check if opendj ports are available
        used_ports = base.check_port_available((1389, 4444, 1636))
        s, aux = ('', 'is') if len(used_ports) == 1 else ('s', 'are')
        if used_ports:
            print()
            print("{}Setup needs port{} {} {} free. Exiting ...{}".format(static.colors.DANGER, s, ','.join(used_ports), aux, static.colors.ENDC))
            print()
            sys.exit()

    print()
    print(gluuInstaller)

    proceed = True
    if not Config.noPrompt:
        proceed_prompt = input('Proceed with these values [Y|n] ').lower().strip()
        if proceed_prompt and proceed_prompt[0] !='y':
            proceed = False

    if Config.rdbm_install_type == static.InstallTypes.LOCAL:
        packageUtils.check_and_install_packages()

#register post setup progress
class PostSetup:
    service_name = 'post-setup'
    install_var = 'installPostSetup'
    app_type = static.AppType.APPLICATION
    install_type = static.InstallOption.MONDATORY

gluuProgress.register(PostSetup)
if not argsp.no_progress:
    gluuProgress.queue = queue

if argsp.shell:
    code.interact(local=locals())
    sys.exit()

def do_installation():

    if not GSA:
        gluuProgress.before_start()
        gluuProgress.start()

    try:
        jettyInstaller.calculate_selected_aplications_memory()

        if not Config.installed_instance:
            gluuInstaller.configureSystem()
            if not base.argsp.dummy:
                gluuInstaller.make_salt()
                oxauthInstaller.make_salt()

            if not base.snap:
                jreInstaller.start_installation()
                jettyInstaller.start_installation()
                jythonInstaller.start_installation()
                nodeInstaller.start_installation()

            if not base.argsp.dummy:
                gluuInstaller.copy_scripts()
                gluuInstaller.encode_passwords()

                oxtrustInstaller.generate_api_configuration()

                Config.ldapCertFn = Config.opendj_cert_fn
                Config.ldapTrustStoreFn = Config.opendj_p12_fn
                Config.encoded_ldapTrustStorePass = Config.encoded_opendj_p12_pass
                Config.oxTrustConfigGeneration = 'true' if Config.installSaml else 'false'

                gluuInstaller.prepare_base64_extension_scripts()
                gluuInstaller.render_templates()
                gluuInstaller.render_configuration_template()

                if not base.snap:
                    gluuInstaller.update_hostname()
                    gluuInstaller.set_ulimits()

                gluuInstaller.copy_output()
                gluuInstaller.setup_init_scripts()

                # Installing gluu components

                if Config.ldap_install:
                    openDjInstaller.start_installation()

                if Config.cb_install:
                    couchbaseInstaller.start_installation()

                if Config.rdbm_install:
                    rdbmInstaller.start_installation()

        if (Config.installed_instance and 'installHttpd' in Config.addPostSetupService) or (not Config.installed_instance and Config.installHttpd):
            httpdinstaller.configure()

        if (Config.installed_instance and 'installOxAuth' in Config.addPostSetupService) or (not Config.installed_instance and Config.installOxAuth):
            oxauthInstaller.start_installation()

        if (Config.installed_instance and 'installOxTrust' in Config.addPostSetupService) or (not Config.installed_instance and Config.installOxTrust):
            oxtrustInstaller.start_installation()

        if (Config.installed_instance and 'installFido2' in Config.addPostSetupService) or (not Config.installed_instance and Config.installFido2):
            fidoInstaller.start_installation()

        if (Config.installed_instance and 'installScimServer' in Config.addPostSetupService) or (not Config.installed_instance and Config.installScimServer):
            scimInstaller.start_installation()

        if (Config.installed_instance and 'installSaml' in Config.addPostSetupService) or (not Config.installed_instance and Config.installSaml):
            samlInstaller.start_installation()

        if (Config.installed_instance and 'installOxd' in Config.addPostSetupService) or (not Config.installed_instance and Config.installOxd):
            oxdInstaller.start_installation()

        if (Config.installed_instance and 'installCasa' in Config.addPostSetupService) or (not Config.installed_instance and Config.installCasa):
            casaInstaller.start_installation()

        if (Config.installed_instance and 'installPassport' in Config.addPostSetupService) or (not Config.installed_instance and Config.installPassport):
            passportInstaller.start_installation()

        if not Config.installed_instance:
            # this will install only base
            radiusInstaller.start_installation()

        if (Config.installed_instance and 'installGluuRadius' in Config.addPostSetupService) or (not Config.installed_instance and Config.installGluuRadius):
            radiusInstaller.install_gluu_radius()


        if not base.argsp.dummy:
            gluuProgress.progress(PostSetup.service_name, "Saving properties")
            propertiesUtils.save_properties()
            time.sleep(2)

            if argsp.t:
                base.logIt("Loading test data")
                testDataLoader.load_test_data()

            gluuInstaller.post_install_tasks()

            for service in gluuProgress.services:
                if service['app_type'] == static.AppType.SERVICE:
                    gluuProgress.progress(PostSetup.service_name, "Starting {}".format(service['name'].title()))
                    time.sleep(2)
                    service['object'].stop()
                    service['object'].start()

        gluuProgress.progress(static.COMPLETED)

        if not GSA:
            print()
            for m in Config.post_messages:
                print(m)

    except:
        if GSA:
            gluuProgress.progress(static.ERROR  , str(traceback.format_exc()))

        base.logIt("FATAL", True, True)

if not GSA and proceed:
    do_installation()
    if not (base.argsp.dummy or base.argsp.no_data):
        print('\n', static.colors.OKGREEN)
        msg_text = msg.post_installation if Config.installed_instance else msg.installation_completed.format(Config.hostname)
        print(msg_text)
        print('\n', static.colors.ENDC)
        # we need this for progress write last line
        time.sleep(2)
else:
    Config.thread_queue = queue
    GSA.do_installation = do_installation
    GSA.jettyInstaller = jettyInstaller
    GSA.setup_loaded = setup_loaded
    GSA.run()
    print('\033c')
    print()
    for m in Config.post_messages:
        print(m)
