import sys
import argparse

def arg_parser():
    parser_description='''Use setup.py to configure your Gluu Server and to add initial data required for
    oxAuth and oxTrust to start. If setup.properties is found in this folder, these
    properties will automatically be used instead of the interactive setup.
    '''

    parser = argparse.ArgumentParser(description=parser_description)
    parser.add_argument('--dummy', help="Dummy installation. Used for re-storing backups", action='store_true')
    parser.add_argument('-a', help=argparse.SUPPRESS, action='store_true')
    parser.add_argument('-c', help="Use command line instead of tui", action='store_true')
    parser.add_argument('-d', help="Installation directory")
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
    parser.add_argument('-j', help="Use Java existing on system", action='store_true')
    parser.add_argument('-profile', help="Setup profile", choices=['CE', 'DISA-STIG'], default='CE')
    parser.add_argument('-opendj-keystore-type', help="OpenDj keystore type (Ony for DISA-STIG profile)", choices=['pkcs11', 'bcfks'], default='bcfks')

    scim_mode_group = parser.add_mutually_exclusive_group()
    scim_mode_group.add_argument('-stm', '--enable-scim-test-mode', help="Enable Scim Test Mode", action='store_true')
    scim_mode_group.add_argument('-sum', '--enable-scim-uma-mode', help="Enable Scim Uma Mode", action='store_true')

    parser.add_argument('--allow-pre-released-features', help="Enable options to install experimental features, not yet officially supported", action='store_true')
    parser.add_argument('--import-ldif', help="Render ldif templates from directory and import them in LDAP")
    parser.add_argument('--listen_all_interfaces', help="Allow the LDAP server to listen on all server interfaces", action='store_true')

    ldap_group = parser.add_mutually_exclusive_group()
    ldap_group.add_argument('--remote-ldap', help="Enables using remote LDAP server", action='store_true')
    ldap_group.add_argument('--install-local-ldap', help="Installs local LDAP Server", action='store_true')
    ldap_group.add_argument('--disable-local-ldap', help="Disables installing local LDAP server", action='store_true')

    rdbm_group = parser.add_mutually_exclusive_group()
    rdbm_group.add_argument('-remote-rdbm', choices=['mysql', 'pgsql', 'spanner'], help="Enables using remote RDBM server")
    rdbm_group.add_argument('-local-rdbm', choices=['mysql', 'pgsql'], help="Enables installing/configuring local RDBM server")

    parser.add_argument('-rdbm-user', help="RDBM username")
    parser.add_argument('-rdbm-password', help="RDBM password")
    parser.add_argument('-rdbm-port', help="RDBM port")
    parser.add_argument('-rdbm-db', help="RDBM database")
    parser.add_argument('-rdbm-host', help="RDBM host")
    parser.add_argument('--reset-rdbm-db', help="Deletes all table on target database. Warning! You will lose all data on target database.", action='store_true')

    parser.add_argument('--remote-couchbase', help="Enables using remote couchbase server", action='store_true')
    parser.add_argument('--local-couchbase', help="Enables installing couchbase server", action='store_true')
    parser.add_argument('-couchbase-hostname', help="Remote couchbase server hostname")

    parser.add_argument('-couchbase-admin-user', help="Couchbase admin user")
    parser.add_argument('-couchbase-admin-password', help="Couchbase admin user password")
    parser.add_argument('-couchbase-bucket-prefix', help="Set prefix for couchbase buckets", default='gluu')

    parser.add_argument('--no-data', help="Do not import any data to database backend, used for clustering", action='store_true')
    parser.add_argument('--no-oxauth', help="Do not install oxAuth OAuth2 Authorization Server", action='store_true')
    parser.add_argument('--no-oxtrust', help="Do not install oxTrust Admin UI", action='store_true')
    parser.add_argument('--install-gluu-radius', help="Install Gluu Radius Server", action='store_true')
    parser.add_argument('-ip-address', help="Used primarily by Apache httpd for the Listen directive")
    parser.add_argument('-host-name', help="Internet-facing FQDN that is used to generate certificates and metadata.")
    parser.add_argument('-org-name', help="Organization name field used for generating X.509 certificates")
    parser.add_argument('-email', help="Email address for support at your organization used for generating X.509 certificates")
    parser.add_argument('-city', help="City field used for generating X.509 certificates")
    parser.add_argument('-state', help="State field used for generating X.509 certificates")
    parser.add_argument('-country', help="Two letters country coude used for generating X.509 certificates")
    parser.add_argument('-oxtrust-admin-password', help="Used as the default admin user for oxTrust")
    parser.add_argument('-testadmin-password', help="Used as password for testadmin for oxTrust")
    parser.add_argument('-ldap-admin-password', help="Used as the LDAP directory manager password")
    parser.add_argument('-application-max-ram', help="Application max ram")
    parser.add_argument('-properties-password', help="Encoded setup.properties file password")
    parser.add_argument('--install-casa', help="Install Casa", action='store_true')
    parser.add_argument('--install-oxd', help="Install Oxd Server", action='store_true')
    parser.add_argument('--install-scim', help="Install Scim Server", action='store_true')
    parser.add_argument('--install-fido2', help="Install Fido2", action='store_true')
    parser.add_argument('--oxd-use-gluu-storage', help="Use Gluu Storage for Oxd Server", action='store_true')
    parser.add_argument('--generate-oxd-certificate', help="Generate certificate for oxd based on hostname", action='store_true')
    parser.add_argument('--shell', help="Drop into interactive shell before starting installation", action='store_true')
    parser.add_argument('--no-progress', help="Use simple progress", action='store_true')
    parser.add_argument('-enable-script', action='append', help="inum of script to enable", required=False)
    parser.add_argument('-ox-authentication-mode', help="Sets oxAuthenticationMode")
    parser.add_argument('-ox-trust-authentication-mode', help="Sets oxTrustAuthenticationMode")
    parser.add_argument('--gluu-passwurd-cert', help="Creates Gluu Passwurd API keystore", action='store_true')
    parser.add_argument('-properties', help="Other properties. Example: encode_salt:Y83EBo94vj9b4iyKDX2drmZk,default_store_type:JKS")

    # spanner options
    parser.add_argument('-spanner-project', help="Spanner project name")
    parser.add_argument('-spanner-instance', help="Spanner instance name")
    parser.add_argument('-spanner-database', help="Spanner database name")
    spanner_cred_group = parser.add_mutually_exclusive_group()
    spanner_cred_group.add_argument('-spanner-emulator-host', help="Use Spanner emulator host")
    spanner_cred_group.add_argument('-google-application-credentials', help="Path to Google application credentials json file")


    argsp = parser.parse_args()

    return argsp
