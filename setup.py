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

sys.path.append('/usr/lib/python{}.{}/gluu-packaged'.format(sys.version_info.major, sys.version_info.minor))

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

sys.path.append(os.path.join(Config.distFolder, 'app/gcs'))

# set profile
if argsp.profile == 'DISA-STIG' or os.path.exists(os.path.join(paths.INSTALL_DIR, 'disa-stig')):
    Config.profile = static.SetupProfiles.DISA_STIG


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
except Exception:
    argsp.no_progress = True


queue = Queue()
GSA = None

if (not argsp.c) and sys.stdout.isatty() and (int(tty_rows) > 24) and (int(tty_columns) > 79):
    try:
        import npyscreen
    except Exception:
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


if not GSA and not os.path.exists(Config.gluu_properties_fn):
    print()
    print("Installing Gluu Server...\n\nFor more info see:\n  {}  \n  {}\n".format(paths.LOG_FILE, paths.LOG_ERROR_FILE))
    print("Detected OS     :  {}".format(base.get_os_description()))
    print("Gluu Version    :  {}".format(Config.oxVersion))
    print("Detected init   :  {}".format(base.os_initdaemon))
    print("Detected Apache :  {}".format(base.determineApacheVersion()))
    print("Profile         :  {}".format(Config.profile.upper()))
    print()

setup_loaded = {}
prop_found_str = '{} Properties found!'
if setupOptions['setup_properties']:
    base.logIt(prop_found_str.format(setupOptions['setup_properties']))
    setup_loaded = propertiesUtils.load_properties(setupOptions['setup_properties'])
elif os.path.isfile(Config.setup_properties_fn):
    base.logIt(prop_found_str.format(Config.setup_properties_fn))
    setup_loaded = propertiesUtils.load_properties(Config.setup_properties_fn)
elif os.path.isfile(Config.setup_properties_fn+'.enc'):
    base.logIt(prop_found_str.format(Config.setup_properties_fn+'.enc'))
    setup_loaded = propertiesUtils.load_properties(Config.setup_properties_fn+'.enc')

if argsp.import_ldif:
    if os.path.isdir(argsp.import_ldif):
        base.logIt("Found setup LDIF import directory {}".format(argsp.import_ldif))
    else:
        base.logIt("The custom LDIF import directory {} does not exist. Exiting...".format(argsp.import_ldif), True, True)


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
oxdInstaller = OxdInstaller()
fidoInstaller = FidoInstaller()
scimInstaller = ScimInstaller()
samlInstaller = SamlInstaller()
casaInstaller = CasaInstaller()
passportInstaller = PassportInstaller()
radiusInstaller = RadiusInstaller()

rdbmInstaller.packageUtils = packageUtils



if Config.installed_instance:

    exit_after_me = False

    if argsp.enable_script:
        print("Enabling scripts {}".format(', '.join(argsp.enable_script)))
        gluuInstaller.enable_scripts(argsp.enable_script)
        exit_after_me = True

    if argsp.ox_authentication_mode or argsp.ox_trust_authentication_mode:
        print("Setting Authentication Modes")
        gluuInstaller.set_auth_modes()
        exit_after_me = True

    if exit_after_me:
        sys.exit()


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

            if 'installCasa' in Config.addPostSetupService and 'installOxd' not in Config.addPostSetupService and not oxdInstaller.installed():
                Config.addPostSetupService.append('installOxd')

        if argsp.gluu_passwurd_cert:
            Config.addPostSetupService.append('generate_passwurd_api_keystore')
        else:
            propertiesUtils.promptForPasswurdApiKeystore()

        if not Config.addPostSetupService:
            print("No service was selected to install. Exiting ...")
            sys.exit()

if argsp.t or argsp.x:
    testDataLoader = TestDataLoader()


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
    install_type = static.InstallOption.MANDATORY

gluuProgress.register(PostSetup)
if not argsp.no_progress:
    gluuProgress.queue = queue

if argsp.shell:
    code.interact(local=locals())
    sys.exit()


def prepare_for_installation():

    gluuInstaller.initialize()

    gluuInstaller.copy_scripts()
    gluuInstaller.encode_passwords()

    oxtrustInstaller.generate_api_configuration()
    Config.oxTrustConfigGeneration = 'true' if Config.installSaml else 'false'

    gluuInstaller.prepare_base64_extension_scripts()
    gluuInstaller.render_templates()
    gluuInstaller.render_configuration_template()

    gluuInstaller.update_hostname()
    gluuInstaller.set_ulimits()

    gluuInstaller.copy_output()
    gluuInstaller.setup_init_scripts()

    gluuInstaller.obtain_java_cacert_aliases()

    gluuInstaller.generate_configuration()

    # Installing gluu components

    if Config.ldap_install:
        openDjInstaller.start_installation()

    if Config.cb_install:
        couchbaseInstaller.start_installation()

    if Config.rdbm_install:
        rdbmInstaller.start_installation()


def install_services():

    for instance in (httpdinstaller, oxauthInstaller, oxtrustInstaller,
                    fidoInstaller, scimInstaller, samlInstaller,
                    oxdInstaller, casaInstaller, passportInstaller):

        if (Config.installed_instance and instance.install_var in Config.addPostSetupService) or (not Config.installed_instance and getattr(Config, instance.install_var)):
            instance.start_installation()

    if not Config.installed_instance and Config.profile != static.SetupProfiles.DISA_STIG:
        # this will install only base
        radiusInstaller.start_installation()

    if (Config.installed_instance and 'installGluuRadius' in Config.addPostSetupService) or (not Config.installed_instance and Config.installGluuRadius):
        radiusInstaller.install_gluu_radius()

def start_services():
    for service in gluuProgress.services:

        if service['app_type'] == static.AppType.SERVICE:
            # we don't restart opendj
            if service['object'].service_name in ('opendj', 'couchbase-server'):
                continue

            gluuProgress.progress(PostSetup.service_name, "Starting {}".format(service['name'].title()))
            time.sleep(2)
            service['object'].stop()
            service['object'].start()

def post_install():
    gluuProgress.progress(PostSetup.service_name, "Saving properties")
    propertiesUtils.save_properties()
    time.sleep(2)

    gluuInstaller.post_install_tasks()

    if Config.profile == static.SetupProfiles.DISA_STIG:
        gluuInstaller.stop('fapolicyd')
        gluuInstaller.start('fapolicyd')

    if argsp.t:
        base.logIt("Loading test data")
        testDataLoader.load_test_data()

    start_services()

def app_installations():

    jreInstaller.start_installation()
    jettyInstaller.start_installation()
    jythonInstaller.start_installation()
    if Config.profile == static.SetupProfiles.CE:
        nodeInstaller.start_installation()


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
                app_installations()
                prepare_for_installation()
        else:
            gluuInstaller.determine_key_gen_path()

        install_services()

        if not base.argsp.dummy:
            post_install()

        gluuProgress.progress(static.COMPLETED)

        if not GSA:
            print()
            for m in Config.post_messages:
                print(m)

    except Exception:
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
