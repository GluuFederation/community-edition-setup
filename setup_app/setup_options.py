import os
import sys
import argparse

from setup_app.static import InstallTypes
from setup_app.utils import base

def get_setup_options():

    parser_description='''Use setup.py to configure your Gluu Server and to add initial data required for
    oxAuth and oxTrust to start. If setup.properties is found in this folder, these
    properties will automatically be used instead of the interactive setup.
    '''

    parser = argparse.ArgumentParser(description=parser_description)
    parser.add_argument('-c', help="Use command line instead of tui", action='store_true')
    parser.add_argument('-d', help="Installation directory")
    parser.add_argument('-r', '--install-oxauth-rp', help="Install oxAuth RP", action='store_true')
    parser.add_argument('-p', '--install-passport', help="Install Passport", action='store_true')
    parser.add_argument('-s', '--install-shib', help="Install the Shibboleth IDP", action='store_true')
    parser.add_argument('-f', help="Specify setup.properties file")
    parser.add_argument('-n', help="No interactive prompt before install starts. Run with -f", action='store_true')    
    parser.add_argument('-N', '--no-httpd', help="No apache httpd server", action='store_true')
    parser.add_argument('-u', help="Update hosts file with IP address / hostname", action='store_true')
    parser.add_argument('-w', help="Get the development head war files", action='store_true')
    parser.add_argument('-t', help="Load test data", action='store_true')
    parser.add_argument('-x', help="Load test data and exit", action='store_true')
    parser.add_argument('-csx', help="Collect setup properties, save and exit", action='store_true')
    parser.add_argument('-stm', '--enable-scim-test-mode', help="Enable Scim Test Mode", action='store_true')
    parser.add_argument('--allow-pre-released-features', help="Enable options to install experimental features, not yet officially supported", action='store_true')
    parser.add_argument('--import-ldif', help="Render ldif templates from directory and import them in LDAP")
    parser.add_argument('--listen_all_interfaces', help="Allow the LDAP server to listen on all server interfaces", action='store_true')

    ldap_group = parser.add_mutually_exclusive_group()
    ldap_group.add_argument('--remote-ldap', help="Enables using remote LDAP server", action='store_true')
    ldap_group.add_argument('--install-local-wrends', help="Installs local WrenDS", action='store_true')

    parser.add_argument('--remote-couchbase', help="Enables using remote couchbase server", action='store_true')
    parser.add_argument('--no-data', help="Do not import any data to database backend, used for clustering", action='store_true')
    parser.add_argument('--no-oxauth', help="Do not install oxAuth OAuth2 Authorization Server", action='store_true')
    parser.add_argument('--no-oxtrust', help="Do not install oxTrust Admin UI", action='store_true')
    parser.add_argument('--install-gluu-radius', help="Install oxTrust Admin UI", action='store_true')
    parser.add_argument('-ip-address', help="Used primarily by Apache httpd for the Listen directive")
    parser.add_argument('-host-name', help="Internet-facing FQDN that is used to generate certificates and metadata.")
    parser.add_argument('-org-name', help="Organization name field used for generating X.509 certificates")
    parser.add_argument('-email', help="Email address for support at your organization used for generating X.509 certificates")
    parser.add_argument('-city', help="City field used for generating X.509 certificates")
    parser.add_argument('-state', help="State field used for generating X.509 certificates")
    parser.add_argument('-country', help="Two letters country coude used for generating X.509 certificates")
    parser.add_argument('-oxtrust-admin-password', help="Used as the default admin user for oxTrust")
    parser.add_argument('-ldap-admin-password', help="Used as the LDAP directory manager password")
    parser.add_argument('-application-max-ram', help="Used as the LDAP directory manager password")
    parser.add_argument('-properties-password', help="Encoded setup.properties file password")
    parser.add_argument('--install-casa', help="Install Casa", action='store_true')
    parser.add_argument('--install-oxd', help="Install Oxd Server", action='store_true')
    parser.add_argument('--install-scim', help="Install Scim Server", action='store_true')
    parser.add_argument('--install-fido2', help="Install Fido2")
    parser.add_argument('--oxd-use-gluu-storage', help="Use Gluu Storage for Oxd Server", action='store_true')
    parser.add_argument('-couchbase-bucket-prefix', help="Set prefix for couchbase buckets", default='gluu')
    parser.add_argument('--generate-oxd-certificate', help="Generate certificate for oxd based on hostname", action='store_true')
    parser.add_argument('--shell', help="Drop into interactive shell before starting installation", action='store_true')

    argsp = parser.parse_args()

    setupOptions = {
        'setup_properties': None,
        'noPrompt': False,
        'downloadWars': False,
        'installOxAuth': True,
        'installOxTrust': True,
        'wrends_install': InstallTypes.LOCAL,
        'installHTTPD': True,
        'installSaml': False,
        'installOxAuthRP': False,
        'installPassport': False,
        'installGluuRadius': False,
        'installScimServer': False,
        'installCasa': False,
        'installOxd': False,
        'installFido2': False,
        'loadTestData': False,
        'allowPreReleasedFeatures': False,
        'listenAllInterfaces': False,
        'cb_install': InstallTypes.NONE,
        'loadTestDataExit': False,
        'loadData': True,
        'properties_password': None,
    }


    if argsp.install_local_wrends:
        setupOptions['wrends_install'] = InstallTypes.LOCAL

    if argsp.no_oxauth:
        setupOptions['installOxAuth'] = False

    if argsp.no_oxtrust:
        setupOptions['installOxTrust'] = False

    if argsp.ip_address:
        setupOptions['ip'] = argsp.ip_address

    if argsp.host_name:
        setupOptions['hostname'] = argsp.host_name
        
    if argsp.org_name:
        setupOptions['orgName'] = argsp.org_name

    if argsp.email:
        setupOptions['admin_email'] = argsp.email

    if argsp.city:
        setupOptions['city'] = argsp.city

    if argsp.state:
        setupOptions['state'] = argsp.state

    if argsp.country:
        setupOptions['countryCode'] = argsp.country

    if argsp.application_max_ram:
        setupOptions['application_max_ram'] = argsp.application_max_ram

    if argsp.oxtrust_admin_password:
        setupOptions['oxtrust_admin_password'] = argsp.oxtrust_admin_password

    if argsp.ldap_admin_password:
        setupOptions['ldapPass'] = argsp.ldap_admin_password

    if argsp.f:
        if os.path.isfile(argsp.f):
            setupOptions['setup_properties'] = argsp.f
            print("Found setup properties %s\n" % argsp.f)
        else:
            print("\nOoops... %s file not found for setup properties.\n" %argsp.f)

    setupOptions['noPrompt'] = argsp.n

    if argsp.no_httpd:
        setupOptions['installHTTPD'] = False

    if argsp.enable_scim_test_mode:
        setupOptions['scimTestMode'] = 'true'

    
    setupOptions['downloadWars'] = argsp.w
    setupOptions['loadTestData']  = argsp.t
    setupOptions['loadTestDataExit'] = argsp.x
    setupOptions['allowPreReleasedFeatures'] = argsp.allow_pre_released_features
    setupOptions['listenAllInterfaces'] = argsp.listen_all_interfaces
    setupOptions['installCasa'] = argsp.install_casa
    setupOptions['installOxd'] = argsp.install_oxd
    setupOptions['installScimServer'] = argsp.install_scim
    setupOptions['installFido2'] = argsp.install_fido2
    setupOptions['couchbase_bucket_prefix'] = argsp.couchbase_bucket_prefix

    if not base.snap:
        setupOptions['installGluuRadius'] = argsp.install_gluu_radius
        setupOptions['installSaml'] = argsp.install_shib
        setupOptions['installOxAuthRP'] = argsp.install_oxauth_rp
        setupOptions['installPassport'] = argsp.install_passport

    if argsp.remote_ldap:
        setupOptions['wrends_install'] = InstallTypes.REMOTE

    if argsp.remote_couchbase:
        setupOptions['cb_install'] = InstallTypes.REMOTE

    if argsp.no_data:
        setupOptions['loadData'] = False

    if argsp.remote_ldap:
        setupOptions['listenAllInterfaces'] = True

    if argsp.oxd_use_gluu_storage:
        setupOptions['oxd_use_gluu_storage'] = True

    if argsp.import_ldif:
        if os.path.isdir(argsp.import_ldif):
            setupOptions['importLDIFDir'] = argsp.import_ldif
            print("Found setup LDIF import directory {}\n".format(argsp.import_ldif))
        else:
            print("The custom LDIF import directory {} does not exist. Exiting...".format(argsp.import_ldif))
            sys.exit(2)

    setupOptions['properties_password'] = argsp.properties_password

    return argsp, setupOptions
