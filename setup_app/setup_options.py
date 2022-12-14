import os
import sys

from setup_app.static import InstallTypes
from setup_app.utils import base
from setup_app.messages import msg

def get_setup_options():


    setupOptions = {
        'setup_properties': None,
        'noPrompt': False,
        'downloadWars': False,
        'installOxAuth': True,
        'installOxTrust': True,
        'ldap_install': InstallTypes.LOCAL,
        'installHTTPD': True,
        'installSaml': False,
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


    if base.argsp.install_local_ldap:
        setupOptions['ldap_install'] = InstallTypes.LOCAL

    if base.argsp.local_couchbase:
        setupOptions['cb_install'] = InstallTypes.LOCAL

    setupOptions['couchbase_bucket_prefix'] = base.argsp.couchbase_bucket_prefix
    setupOptions['cb_password'] = base.argsp.couchbase_admin_password
    setupOptions['couchebaseClusterAdmin'] = base.argsp.couchbase_admin_user

    if base.argsp.no_oxauth:
        setupOptions['installOxAuth'] = False

    if base.argsp.no_oxtrust:
        setupOptions['installOxTrust'] = False

    setupOptions['installGluuRadius'] = base.argsp.install_gluu_radius

    if base.argsp.ip_address:
        setupOptions['ip'] = base.argsp.ip_address

    if base.argsp.host_name:
        setupOptions['hostname'] = base.argsp.host_name
        
    if base.argsp.org_name:
        setupOptions['orgName'] = base.argsp.org_name

    if base.argsp.email:
        setupOptions['admin_email'] = base.argsp.email

    if base.argsp.city:
        setupOptions['city'] = base.argsp.city

    if base.argsp.state:
        setupOptions['state'] = base.argsp.state

    if base.argsp.country:
        setupOptions['countryCode'] = base.argsp.country

    if base.argsp.application_max_ram:
        setupOptions['application_max_ram'] = base.argsp.application_max_ram

    if base.argsp.oxtrust_admin_password:
        setupOptions['oxtrust_admin_password'] = base.argsp.oxtrust_admin_password

    if base.argsp.ldap_admin_password:
        setupOptions['ldapPass'] = base.argsp.ldap_admin_password

    if base.argsp.f:
        if os.path.isfile(base.argsp.f):
            setupOptions['setup_properties'] = base.argsp.f
            print("Found setup properties %s\n" % base.argsp.f)
        else:
            print("\nOoops... %s file not found for setup properties.\n" %base.argsp.f)

    setupOptions['noPrompt'] = base.argsp.n

    if base.argsp.no_httpd:
        setupOptions['installHTTPD'] = False

    setupOptions['installSaml'] = base.argsp.install_shib
    setupOptions['downloadWars'] = base.argsp.w
    setupOptions['installPassport'] = base.argsp.install_passport
    setupOptions['loadTestData'] = base.argsp.t
    setupOptions['loadTestDataExit'] = base.argsp.x
    setupOptions['allowPreReleasedFeatures'] = base.argsp.allow_pre_released_features
    setupOptions['listenAllInterfaces'] = base.argsp.listen_all_interfaces
    setupOptions['installCasa'] = base.argsp.install_casa
    setupOptions['installOxd'] = base.argsp.install_oxd
    setupOptions['installScimServer'] = base.argsp.install_scim
    setupOptions['installFido2'] = base.argsp.install_fido2

    if base.argsp.remote_ldap:
        setupOptions['ldap_install'] = InstallTypes.REMOTE
        setupOptions['listenAllInterfaces'] = True

    if not (base.argsp.remote_couchbase or getattr(base.argsp, 'remote_rdbm', None) or getattr(base.argsp, 'local_rdbm', None)):
        setupOptions['ldap_install'] = InstallTypes.LOCAL
    else:
        setupOptions['ldap_install'] = InstallTypes.NONE

        if base.argsp.remote_couchbase:
            setupOptions['cb_install'] = InstallTypes.REMOTE
            setupOptions['couchbase_hostname'] = base.argsp.couchbase_hostname

        if getattr(base.argsp, 'remote_rdbm', None):
            setupOptions['rdbm_install'] = True
            setupOptions['rdbm_install_type'] = InstallTypes.REMOTE
            setupOptions['rdbm_type'] = base.argsp.remote_rdbm
            if base.argsp.remote_rdbm != 'spanner':
                setupOptions['rdbm_host'] = base.argsp.rdbm_host

        if getattr(base.argsp, 'local_rdbm', None):
            setupOptions['rdbm_install'] = True
            setupOptions['rdbm_install_type'] = InstallTypes.LOCAL
            setupOptions['rdbm_type'] = base.argsp.local_rdbm
            setupOptions['rdbm_host'] = 'localhost'

        if getattr(base.argsp, 'rdbm_port', None):
            setupOptions['rdbm_port'] = base.argsp.rdbm_port
        else:
            if setupOptions.get('rdbm_type') == 'pgsql':
                setupOptions['rdbm_port'] = 5432

        if getattr(base.argsp, 'rdbm_db', None):
            setupOptions['rdbm_db'] = base.argsp.rdbm_db
        if getattr(base.argsp, 'rdbm_user', None):
            setupOptions['rdbm_user'] = base.argsp.rdbm_user
        if getattr(base.argsp, 'rdbm_password', None):
            setupOptions['rdbm_password'] = base.argsp.rdbm_password

        if getattr(base.argsp, 'spanner_project', None):
            setupOptions['spanner_project'] = base.argsp.spanner_project
        if getattr(base.argsp, 'spanner_instance', None):
            setupOptions['spanner_instance'] = base.argsp.spanner_instance
        if getattr(base.argsp, 'spanner_database', None):
            setupOptions['spanner_database'] = base.argsp.spanner_database
        if getattr(base.argsp, 'spanner_emulator_host', None):
            setupOptions['spanner_emulator_host'] = base.argsp.spanner_emulator_host
        if getattr(base.argsp, 'google_application_credentials', None):
            setupOptions['google_application_credentials'] = base.argsp.google_application_credentials

    if base.argsp.no_data:
        setupOptions['loadData'] = False

    if base.argsp.oxd_use_gluu_storage:
        setupOptions['oxd_use_gluu_storage'] = True

    if base.argsp.import_ldif:
        if os.path.isdir(base.argsp.import_ldif):
            setupOptions['importLDIFDir'] = base.argsp.import_ldif
            print("Found setup LDIF import directory {}\n".format(base.argsp.import_ldif))
        else:
            print("The custom LDIF import directory {} does not exist. Exiting...".format(base.argsp.import_ldif))
            sys.exit(2)

    if base.argsp.disable_local_ldap:
        setupOptions['ldap_install'] = InstallTypes.NONE

    if base.argsp.local_couchbase:
        setupOptions['cb_install'] = InstallTypes.LOCAL

    setupOptions['properties_password'] = base.argsp.properties_password

    if base.argsp.install_shib and base.argsp.remote_rdbm == 'spanner':
        print(msg.spanner_idp_warning)
        setupOptions['installSaml'] = False

    if base.argsp.properties:
        prop_list = base.argsp.properties.split(',')
        for props in prop_list:
            n = props.find(':')
            if n > 0:
                p_key = props[:n].strip()
                p_val = props[n+1:].strip()
                setupOptions[p_key] = p_val

    return setupOptions
