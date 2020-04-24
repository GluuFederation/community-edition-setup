#!/usr/bin/python

# The MIT License (MIT)
#
# Copyright (c) 2014 Gluu
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import readline
import os.path
import Properties
import random
import shutil
import socket
import string
import time
import uuid
import json
import traceback
import subprocess
import sys
import getopt
import hashlib
import re
import glob
import base64
import platform


file_max = int(open("/proc/sys/fs/file-max").read().strip())

if file_max < 64000:
    sys.exit("""
Maximum number of files that can be opened on this computer is less than 64000.
Please increase number of file-max on the host system and re-run setup.py""")


try:
    tty_rows, tty_columns = os.popen('stty size', 'r').read().split()
except:
    tty_rows = 60
    tty_columns = 120

class ProgressBar:

    def __init__(self, tty_columns, max_steps=34):
        self.n = 0
        self.max_steps = max_steps
        self.tty_columns = tty_columns

    def complete(self, msg):
        self.n = self.max_steps
        self.progress(msg, False)

    def progress(self, msg, incr=True):
        if incr and self.n < self.max_steps:
            self.n +=1

        time.sleep(0.2)
        ft = '#' * self.n
        ft = ft.ljust(self.max_steps)
        msg =msg.ljust(40)
        if int(self.tty_columns) < 88:
            msg = msg[:int(self.tty_columns)-47]
        sys.stdout.write("\rInstalling [{0}] {1}".format(ft, msg))
        sys.stdout.flush()

class Setup(object):
    def __init__(self, install_dir=None):
        self.install_dir = install_dir

        self.oxVersion = '3.1.8.Final'
        self.githubBranchName = 'version_3.1.8'

        self.pbar = ProgressBar(tty_columns)

        # Used only if -w (get wars) options is given to setup.py
        self.oxauth_war = 'https://ox.gluu.org/maven/org/xdi/oxauth-server/%s/oxauth-server-%s.war' % (self.oxVersion, self.oxVersion)
        self.oxauth_rp_war = 'https://ox.gluu.org/maven/org/xdi/oxauth-rp/%s/oxauth-rp-%s.war' % (self.oxVersion, self.oxVersion)
        self.oxtrust_war = 'https://ox.gluu.org/maven/org/xdi/oxtrust-server/%s/oxtrust-server-%s.war' % (self.oxVersion, self.oxVersion)
        self.idp3_war = 'http://ox.gluu.org/maven/org/xdi/oxshibbolethIdp/%s/oxshibbolethIdp-%s.war' % (self.oxVersion, self.oxVersion)
        self.idp3_dist_jar = 'http://ox.gluu.org/maven/org/xdi/oxShibbolethStatic/%s/oxShibbolethStatic-%s.jar' % (self.oxVersion, self.oxVersion)
        self.idp3_cml_keygenerator = 'http://ox.gluu.org/maven/org/xdi/oxShibbolethKeyGenerator/%s/oxShibbolethKeyGenerator-%s.jar' % (self.oxVersion, self.oxVersion)
        self.asimba_war = 'http://ox.gluu.org/maven/org/asimba/asimba-wa/%s/asimba-wa-%s.war' % (self.oxVersion, self.oxVersion)
        self.ce_setup_zip = 'https://github.com/GluuFederation/community-edition-setup/archive/%s.zip' % self.githubBranchName

        self.downloadWars = None
        self.templateRenderingDict = {}

        # OS commands
        self.cmd_ln = '/bin/ln'
        self.cmd_chmod = '/bin/chmod'
        self.cmd_chown = '/bin/chown'
        self.cmd_chgrp = '/bin/chgrp'
        self.cmd_mkdir = '/bin/mkdir'
        self.cmd_rpm = '/bin/rpm'
        self.cmd_dpkg = '/usr/bin/dpkg'
        self.opensslCommand = '/usr/bin/openssl'

        self.sysemProfile = "/etc/profile"

        # java commands
        self.jre_home = '/opt/jre'
        self.cmd_java = '%s/bin/java' % self.jre_home
        self.cmd_keytool = '%s/bin/keytool' % self.jre_home
        self.cmd_jar = '%s/bin/jar' % self.jre_home
        os.environ["OPENDJ_JAVA_HOME"] =  self.jre_home
        self.open_jdk_archive_link = 'https://github.com/AdoptOpenJDK/openjdk11-binaries/releases/download/jdk-11.0.4%2B11/OpenJDK11U-jdk_x64_linux_hotspot_11.0.4_11.tar.gz'
        self.java_type = 'jre'


        # Component ithversions
        self.jre_version = '8.222.10.1'
        self.jetty_version = '9.4.12.v20180830'
        self.jython_version = '2.7.2a'
        self.node_version = '9.9.0'
        self.opendj_version_number = '3.0.1.gluu'
        self.apache_version = None
        self.opendj_version = None
        self.opendj_type = 'opendj'

        # Gluu components installation status
        self.installOxAuth = True
        self.installOxTrust = True
        self.installLdap = True
        self.installHttpd = True
        self.installSaml = False
        self.installAsimba = False
        self.installOxAuthRP = False
        self.installPassport = False

        self.allowPreReleasedApplications = False
        self.allowDeprecatedApplications = False

        self.currentGluuVersion = '3.1.8'

        self.jreDestinationPath = '/opt/amazon-corretto-%s-linux-x64' % self.jre_version

        self.os_types = ['centos', 'red', 'fedora', 'ubuntu', 'debian']
        self.os_type = None
        self.os_initdaemon = None

        self.shibboleth_version = 'v3'

        self.distFolder = '/opt/dist'
        self.distAppFolder = '%s/app' % self.distFolder
        self.distGluuFolder = '%s/gluu' % self.distFolder
        self.distTmpFolder = '%s/tmp' % self.distFolder

        self.setup_properties_fn = '%s/setup.properties' % self.install_dir
        self.log = '%s/setup.log' % self.install_dir
        self.logError = '%s/setup_error.log' % self.install_dir
        self.savedProperties = '%s/setup.properties.last' % self.install_dir

        self.gluuOptFolder = '/opt/gluu'
        self.gluuOptBinFolder = '%s/bin' % self.gluuOptFolder
        self.gluuOptSystemFolder = '%s/system' % self.gluuOptFolder
        self.gluuOptPythonFolder = '%s/python' % self.gluuOptFolder
        self.gluuBaseFolder = '/etc/gluu'
        self.configFolder = '%s/conf' % self.gluuBaseFolder
        self.fido2ConfigFolder = '%s/fido2' % self.configFolder
        self.certFolder = '/etc/certs'

        self.oxBaseDataFolder = "/var/ox"
        self.oxPhotosFolder = "/var/ox/photos"
        self.oxTrustRemovedFolder = "/var/ox/identity/removed"
        self.oxTrustCacheRefreshFolder = "/var/ox/identity/cr-snapshots"

        self.etc_hosts = '/etc/hosts'
        self.etc_hostname = '/etc/hostname'
        # OS /etc/default folder
        self.osDefault = '/etc/default'

        self.jython_home = '/opt/jython'

        self.node_home = '/opt/node'
        self.node_initd_script = '%s/static/system/initd/node' % self.install_dir
        self.node_base = '%s/node' % self.gluuOptFolder
        self.node_user_home = '/home/node'
        self.passport_initd_script = '%s/static/system/initd/passport' % self.install_dir

        self.jetty_dist = '/opt/jetty-9.4'
        self.jetty_home = '/opt/jetty'
        self.jetty_base = '%s/jetty' % self.gluuOptFolder
        self.jetty_user_home = '/home/jetty'
        self.jetty_user_home_lib = '%s/lib' % self.jetty_user_home
        self.jetty_app_configuration = {
            'oxauth' : {'name' : 'oxauth',
                        'jetty' : {'modules' : 'server,deploy,annotations,resources,http,http-forwarded,threadpool,console-capture,jsp,ext,websocket'},
                        'memory' : {'ratio' : 0.3, "jvm_heap_ration" : 0.7, "max_allowed_mb" : 4096},
                        'installed' : False
                        },
            'identity' : {'name' : 'identity',
                          'jetty' : {'modules' : 'server,deploy,annotations,resources,http,http-forwarded,threadpool,console-capture,jsp,ext,websocket'},
                          'memory' : {'ratio' : 0.2, "jvm_heap_ration" : 0.7, "max_allowed_mb" : 2048},
                          'installed' : False
                          },
            'idp' : {'name' : 'idp',
                     'jetty' : {'modules' : 'server,deploy,annotations,resources,http,http-forwarded,threadpool,console-capture,jsp'},
                     'memory' : {'ratio' : 0.2, "jvm_heap_ration" : 0.7, "max_allowed_mb" : 1024},
                     'installed' : False
                     },
            'asimba' : {'name' : 'asimba',
                        'jetty' : {'modules' : 'server,deploy,http,resources,console-capture,jsp'},
                        'memory' : {'ratio' : 0.1, "jvm_heap_ration" : 0.7, "max_allowed_mb" : 1024},
                        'installed' : False
                        },
            'oxauth-rp' : {'name' : 'oxauth-rp',
                           'jetty' : {'modules' : 'server,deploy,annotations,resources,http,http-forwarded,threadpool,console-capture,jsp,websocket'},
                           'memory' : {'ratio' : 0.1, "jvm_heap_ration" : 0.7, "max_allowed_mb" : 512},
                           'installed' : False
                           },
            'passport' : {'name' : 'passport',
                          'node' : {},
                          'memory' : {'ratio' : 0.1, "max_allowed_mb" : 1024},
                          'installed' : False
                           }
        }

        self.app_custom_changes = {
            'jetty' : {
                'name' : 'jetty',
                'files' : [{
                    'path' : '%s/etc/webdefault.xml' % self.jetty_home,
                    'replace' : [
                        {
                            'pattern' : r'(\<param-name\>dirAllowed<\/param-name\>)(\s*)(\<param-value\>)true(\<\/param-value\>)',
                            'update' : r'\1\2\3false\4'
                        }
                    ]
                },
                    {
                        'path' : '%s/etc/jetty.xml' % self.jetty_home,
                        'replace' : [
                            {
                                'pattern' : '<New id="DefaultHandler" class="org.eclipse.jetty.server.handler.DefaultHandler"/>',
                                'update' : '<New id="DefaultHandler" class="org.eclipse.jetty.server.handler.DefaultHandler">\n\t\t\t\t <Set name="showContexts">false</Set>\n\t\t\t </New>'
                            }
                        ]
                    }]
            }
        }

        self.idp3Folder = "/opt/shibboleth-idp"
        self.idp3MetadataFolder = "%s/metadata" % self.idp3Folder
        self.idp3MetadataCredentialsFolder = "%s/credentials" % self.idp3MetadataFolder
        self.idp3LogsFolder = "%s/logs" % self.idp3Folder
        self.idp3LibFolder = "%s/lib" % self.idp3Folder
        self.idp3ConfFolder = "%s/conf" % self.idp3Folder
        self.idp3ConfAuthnFolder = "%s/conf/authn" % self.idp3Folder
        self.idp3CredentialsFolder = "%s/credentials" % self.idp3Folder
        self.idp3WebappFolder = "%s/webapp" % self.idp3Folder
        # self.idp3WarFolder = "%s/war"

        self.hostname = None
        self.ip = None
        self.orgName = None
        self.orgShortName = None
        self.countryCode = None
        self.city = None
        self.state = None
        self.admin_email = None
        self.encoded_ox_ldap_pw = None
        self.encoded_ldap_pw = None
        self.encoded_shib_jks_pw = None
        self.application_max_ram = None    # in MB
        self.encode_salt = None

        self.baseInum = None
        self.inumOrg = None
        self.inumAppliance = None
        self.inumOrgFN = None
        self.inumApplianceFN = None
        self.ldapBaseFolderldapPass = None

        self.oxauth_client_id = None
        self.oxauthClient_pw = None
        self.oxauthClient_encoded_pw = None

        self.idp_client_id = None
        self.idpClient_pw = None
        self.idpClient_encoded_pw = None

        self.oxTrustConfigGeneration = None

        self.oxd_hostname = '%(oxd_hostname)s'
        self.oxd_port = '%(oxd_port)s'

        self.outputFolder = '%s/output' % self.install_dir
        self.templateFolder = '%s/templates' % self.install_dir
        self.staticFolder = '%s/static' % self.install_dir

        self.extensionFolder = '%s/extension' % self.staticFolder

        self.oxauth_error_json = '%s/oxauth/oxauth-errors.json' % self.staticFolder

        self.oxauth_openid_jwks_fn = "%s/oxauth-keys.json" % self.certFolder
        self.oxauth_openid_jks_fn = "%s/oxauth-keys.jks" % self.certFolder
        self.oxauth_openid_jks_pass = None

        self.httpdKeyPass = None
        self.httpdKeyFn = '%s/httpd.key' % self.certFolder
        self.httpdCertFn = '%s/httpd.crt' % self.certFolder
        self.shibJksPass = None
        self.shibJksFn = '%s/shibIDP.jks' % self.certFolder
        self.asimbaJksPass = None
        self.asimbaJksFn = '%s/asimbaIDP.jks' % self.certFolder

        self.ldapTrustStoreFn = None
        self.encoded_ldapTrustStorePass = None

        self.opendj_cert_fn = '%s/opendj.crt' % self.certFolder
        self.opendj_p12_fn = '%s/opendj.pkcs12' % self.certFolder
        self.opendj_p12_pass = None

        self.ldap_type = None
        self.opendj_ldap_binddn = 'cn=directory manager'
        self.ldap_hostname = "localhost"
        self.ldap_port = '1389'
        self.ldaps_port = '1636'
        self.ldap_admin_port = '4444'
        self.ldapBaseFolder = '/opt/opendj'

        self.ldapSetupCommand = '%s/setup' % self.ldapBaseFolder
        self.ldapDsconfigCommand = "%s/bin/dsconfig" % self.ldapBaseFolder
        self.ldapDsCreateRcCommand = "%s/bin/create-rc-script" % self.ldapBaseFolder
        self.ldapDsJavaPropCommand = "%s/bin/dsjavaproperties" % self.ldapBaseFolder
        
        self.ldap_user_home = '/home/ldap'
        self.ldapPassFn = '%s/.pw' % self.ldap_user_home
        self.ldap_backend_type = 'je'
        self.importLdifCommand = '%s/bin/import-ldif' % self.ldapBaseFolder
        self.ldapModifyCommand = '%s/bin/ldapmodify' % self.ldapBaseFolder
        self.loadLdifCommand = self.ldapModifyCommand
        self.gluuScriptFiles = ['%s/static/scripts/logmanager.sh' % self.install_dir,
                                '%s/static/scripts/testBind.py' % self.install_dir]

        self.openDjIndexJson = '%s/static/opendj/index.json' % self.install_dir
        self.openDjSchemaFolder = "%s/config/schema" % self.ldapBaseFolder
        self.openDjschemaFiles = ["%s/static/opendj/96-eduperson.ldif" % self.install_dir,
                            "%s/static/opendj/101-ox.ldif" % self.install_dir,
                            "%s/static/opendj/77-customAttributes.ldif" % self.install_dir]

        self.opendj_init_file = '%s/static/opendj/opendj' % self.install_dir
        self.opendj_service_centos7 = '%s/static/opendj/systemd/opendj.service' % self.install_dir

        self.redhat_services = ['httpd', 'rsyslog']
        self.debian_services = ['apache2', 'rsyslog']

        self.apache_start_script = '/etc/init.d/httpd'

        self.defaultTrustStoreFN = '%s/jre/lib/security/cacerts' % self.jre_home
        self.defaultTrustStorePW = 'changeit'

        self.openldapBaseFolder = '/opt/symas'
        self.openldapBinFolder = '/opt/symas/bin'
        self.openldapConfFolder = '/opt/symas/etc/openldap'
        self.openldapRootUser = "cn=directory manager,o=gluu"
        self.openldapSiteUser = "cn=directory manager,o=site"
        self.openldapMetricUser = "cn=directory manager,o=metric"
        self.openldapKeyPass = None
        self.openldapTLSCACert = '%s/openldap.pem' % self.certFolder
        self.openldapTLSCert = '%s/openldap.crt' % self.certFolder
        self.openldapTLSKey = '%s/openldap.key' % self.certFolder
        self.openldapJksPass = None
        self.openldapJksFn = '%s/openldap.jks' % self.certFolder
        self.openldapP12Fn = '%s/openldap.pkcs12' % self.certFolder

        self.passportSpKeyPass = None
        self.passportSpTLSCACert = '%s/passport-sp.pem' % self.certFolder
        self.passportSpTLSCert = '%s/passport-sp.crt' % self.certFolder
        self.passportSpTLSKey = '%s/passport-sp.key' % self.certFolder
        self.passportSpJksPass = None
        self.passportSpJksFn = '%s/passport-sp.jks' % self.certFolder

        self.openldapSlapdConf = '%s/slapd.conf' % self.outputFolder
        self.openldapSymasConf = '%s/symas-openldap.conf' % self.outputFolder
        self.openldapRootSchemaFolder = "%s/schema" % self.gluuOptFolder
        self.openldapSchemaFolder = "%s/openldap" % self.openldapRootSchemaFolder
        self.openldapLogDir = "/var/log/openldap/"
        self.openldapSyslogConf = "%s/static/openldap/openldap-syslog.conf" % self.install_dir
        self.openldapLogrotate = "%s/static/openldap/openldap_logrotate" % self.install_dir
        self.openldapSetupAccessLog = False
        self.accessLogConfFile = "%s/static/openldap/accesslog.conf" % self.install_dir
        self.gluuAccessLogConf = "%s/static/openldap/o_gluu_accesslog.conf" % self.install_dir
        self.opendlapIndexDef = "%s/static/openldap/index.json" % self.install_dir

        # Stuff that gets rendered; filename is necessary. Full path should
        # reflect final path if the file must be copied after its rendered.
        self.passport_saml_config = '%s/passport-saml-config.json' % self.configFolder
        self.passport_inbound_idp_initiated_json = '%s/passport-inbound-idp-initiated.json' % self.configFolder
        self.oxauth_config_json = '%s/oxauth-config.json' % self.outputFolder
        self.oxtrust_config_json = '%s/oxtrust-config.json' % self.outputFolder
        self.oxtrust_cache_refresh_json = '%s/oxtrust-cache-refresh.json' % self.outputFolder
        self.oxtrust_import_person_json = '%s/oxtrust-import-person.json' % self.outputFolder
        self.oxidp_config_json = '%s/oxidp-config.json' % self.outputFolder
        self.oxasimba_config_json = '%s/oxasimba-config.json' % self.outputFolder
        self.gluu_python_base = '%s/python' % self.gluuOptFolder
        self.gluu_python_readme = '%s/libs/python.txt' % self.gluuOptPythonFolder
        self.ox_ldap_properties = '%s/ox-ldap.properties' % self.configFolder
        self.oxauth_static_conf_json = '%s/oxauth-static-conf.json' % self.outputFolder
        self.oxTrust_log_rotation_configuration = "%s/conf/oxTrustLogRotationConfiguration.xml" % self.gluuBaseFolder
        self.apache2_conf = '%s/httpd.conf' % self.outputFolder
        self.apache2_ssl_conf = '%s/https_gluu.conf' % self.outputFolder
        self.apache2_24_conf = '%s/httpd_2.4.conf' % self.outputFolder
        self.apache2_ssl_24_conf = '%s/https_gluu.conf' % self.outputFolder
        self.ldif_base = '%s/base.ldif' % self.outputFolder
        self.ldif_appliance = '%s/appliance.ldif' % self.outputFolder
        self.ldif_attributes = '%s/attributes.ldif' % self.outputFolder
        self.ldif_scopes = '%s/scopes.ldif' % self.outputFolder
        self.ldif_clients = '%s/clients.ldif' % self.outputFolder
        self.ldif_people = '%s/people.ldif' % self.outputFolder
        self.ldif_groups = '%s/groups.ldif' % self.outputFolder
        self.ldif_metric = '%s/metric/o_metric.ldif' % self.staticFolder
        self.ldif_site = '%s/static/cache-refresh/o_site.ldif' % self.install_dir
        self.ldif_scripts = '%s/scripts.ldif' % self.outputFolder
        self.ldif_configuration = '%s/configuration.ldif' % self.outputFolder
        self.ldif_scim = '%s/scim.ldif' % self.outputFolder
        self.ldif_asimba = '%s/asimba.ldif' % self.outputFolder
        self.ldif_passport = '%s/passport.ldif' % self.outputFolder
        self.ldif_idp = '%s/oxidp.ldif' % self.outputFolder
        self.ldif_scripts_casa = '%s/scripts_casa.ldif' % self.outputFolder
        self.passport_config = '%s/passport-config.json' % self.configFolder
        self.encode_script = '%s/bin/encode.py' % self.gluuOptFolder
        self.network = "/etc/sysconfig/network"
        self.system_profile_update_init = '%s/system_profile_init' % self.outputFolder
        self.system_profile_update_systemd = '%s/system_profile_systemd' % self.outputFolder

        self.asimba_conf_folder = '%s/asimba' % self.configFolder
        self.asimba_configuration_xml = '%s/asimba.xml' % self.asimba_conf_folder
        self.asimba_configuration = '%s/asimba.xml' % self.outputFolder
        self.asimba_selector_configuration = '%s/asimba-selector.xml' % self.outputFolder
        self.asimba_properties = '%s/asimba.properties' % self.outputFolder
        self.asimba_selector_configuration_xml = '%s/asimba-selector.xml' % self.asimba_conf_folder

        self.staticIDP3FolderConf = '%s/static/idp3/conf' % self.install_dir
        self.staticIDP3FolderMetadata = '%s/static/idp3/metadata' % self.install_dir
        self.idp3_configuration_properties = 'idp.properties'
        self.idp3_configuration_ldap_properties = 'ldap.properties'
        self.idp3_configuration_saml_nameid = 'saml-nameid.properties'
        self.idp3_configuration_services = 'services.properties'
        self.idp3_configuration_password_authn = 'authn/password-authn-config.xml'
        self.idp3_metadata = 'idp-metadata.xml'

        self.casa_config = '%s/casa.json' % self.outputFolder

        ### rsyslog file customised for init.d
        self.rsyslogUbuntuInitFile = "%s/static/system/ubuntu/rsyslog" % self.install_dir

        self.ldap_setup_properties = '%s/opendj-setup.properties' % self.templateFolder

        # oxAuth/oxTrust Base64 configuration files
        self.pairwiseCalculationKey = None
        self.pairwiseCalculationSalt = None

        # OpenID key generation default setting
        self.default_openid_jks_dn_name = 'CN=oxAuth CA Certificates'
        self.default_key_algs = 'RS256 RS384 RS512 ES256 ES384 ES512'
        self.default_key_expiration = 365

        # oxTrust SCIM configuration
        self.scim_rs_client_id = None
        self.scim_rs_client_jwks = None
        self.scim_rs_client_jks_fn = "%s/scim-rs.jks" % self.certFolder
        self.scim_rs_client_jks_pass = None
        self.scim_rs_client_jks_pass_encoded = None

        self.scim_rp_client_id = None
        self.scim_rp_client_jwks = None
        self.scim_rp_client_jks_fn = "%s/scim-rp.jks" % self.outputFolder
        self.scim_rp_client_jks_pass = 'secret'
        self.scim_resource_oxid = None

        # oxPassport Configuration
        self.gluu_passport_base = '%s/passport' % self.node_base
        self.ldif_passport_config = '%s/oxpassport-config.ldif' % self.outputFolder

        self.passport_rs_client_id = None
        self.passport_rs_client_jwks = None
        self.passport_rs_client_jks_fn = "%s/passport-rs.jks" % self.certFolder
        self.passport_rs_client_jks_pass = None
        self.passport_rs_client_jks_pass_encoded = None

        self.passport_rp_client_id = None
        self.passport_rp_client_jwks = None
        self.passport_rp_client_jks_fn = "%s/passport-rp.jks" % self.certFolder
        self.passport_rp_client_cert_alg = "RS512"
        self.passport_rp_client_cert_alias = None
        self.passport_rp_client_cert_fn = "%s/passport-rp.pem" % self.certFolder
        self.passport_rp_client_jks_pass = 'secret'

        self.ldif_files = [self.ldif_base,
                           self.ldif_appliance,
                           self.ldif_attributes,
                           self.ldif_scopes,
                           self.ldif_clients,
                           self.ldif_people,
                           self.ldif_groups,
                           self.ldif_site,
                           self.ldif_metric,
                           self.ldif_scripts,
                           self.ldif_configuration,
                           self.ldif_scim,
                           self.ldif_asimba,
                           self.ldif_passport,
                           self.ldif_passport_config,
                           self.ldif_idp
                           ]

        self.ce_templates = {self.oxauth_config_json: False,
                             self.passport_saml_config:True,
                             self.gluu_python_readme: True,
                             self.oxtrust_config_json: False,
                             self.oxtrust_cache_refresh_json: False,
                             self.oxtrust_import_person_json: False,
                             self.oxidp_config_json: False,
                             self.oxasimba_config_json: False,
                             self.ox_ldap_properties: True,
                             self.oxauth_static_conf_json: False,
                             self.oxTrust_log_rotation_configuration: True,
                             self.ldap_setup_properties: False,
                             self.apache2_conf: False,
                             self.apache2_ssl_conf: False,
                             self.apache2_24_conf: False,
                             self.apache2_ssl_24_conf: False,
                             self.etc_hosts: False,
                             self.etc_hostname: False,
                             self.ldif_base: False,
                             self.ldif_appliance: False,
                             self.ldif_attributes: False,
                             self.ldif_scopes: False,
                             self.ldif_clients: False,
                             self.ldif_people: False,
                             self.ldif_groups: False,
                             self.ldif_scripts: False,
                             self.ldif_scim: False,
                             self.ldif_asimba: False,
                             self.ldif_passport: False,
                             self.ldif_passport_config: False,
                             self.ldif_idp: False,
                             self.asimba_configuration: False,
                             self.asimba_properties: False,
                             self.asimba_selector_configuration: False,
                             self.network: False,
                             self.casa_config: False,
                             self.ldif_scripts_casa: False,
                             self.passport_inbound_idp_initiated_json: True,
                             }

        self.oxauth_keys_utils_libs = [ 'bcprov-jdk15on-*.jar', 'bcpkix-jdk15on-*.jar', 'commons-lang-*.jar',
                                        'log4j-*.jar', 'commons-codec-*.jar', 'commons-cli-*.jar', 'commons-io-*.jar',
                                        'jackson-core-*.jar', 'jackson-core-asl-*.jar', 'jackson-mapper-asl-*.jar', 'jackson-xc-*.jar',
                                        'jettison-*.jar', 'oxauth-model-*.jar', 'oxauth-client-*.jar', 'oxcore-util-*.jar' ]


        self.service_requirements = {
                        'opendj': ['', 70],
                        'oxauth': ['opendj', 72],
                        'identity': ['opendj oxauth', 74],
                        'idp': ['opendj oxauth', 76],
                        'casa': ['opendj oxauth', 78],
                        'oxd-server': ['opendj oxauth', 80],
                        'passport': ['opendj oxauth', 82],
                        'oxauth-rp': ['opendj oxauth', 84],
                        'asimba': ['opendj oxauth', 86],
                        }
                                

        self.install_time_ldap = None

    def __repr__(self):
        try:
            partA = 'hostname'.ljust(30) + self.hostname.rjust(35) + "\n" \
                   + 'orgName'.ljust(30) + self.orgName.rjust(35) + "\n" \
                   + 'os'.ljust(30) + self.os_type.rjust(35) + "\n" \
                   + 'city'.ljust(30) + self.city.rjust(35) + "\n" \
                   + 'state'.ljust(30) + self.state.rjust(35) + "\n" \
                   + 'countryCode'.ljust(30) + self.countryCode.rjust(35) + "\n" \
                   + 'support email'.ljust(30) + self.admin_email.rjust(35) + "\n" \
                   + 'Applications max ram'.ljust(30) + self.application_max_ram.rjust(35) + "\n" \
                   + 'Admin Pass'.ljust(30) + self.ldapPass.rjust(35) + "\n" \
                   + 'Install oxAuth'.ljust(30) + repr(self.installOxAuth).rjust(35) + "\n" \
                   + 'Install oxTrust'.ljust(30) + repr(self.installOxTrust).rjust(35) + "\n" \
                   + 'Java Type'.ljust(30) + self.java_type.rjust(35) + "\n" \
                   + 'Install LDAP'.ljust(30) + repr(self.installLdap).rjust(35) + "\n" \
                   + 'Install Apache 2 web server'.ljust(30) + repr(self.installHttpd).rjust(35) + "\n" \
                   + 'Install Shibboleth SAML IDP'.ljust(30) + repr(self.installSaml).rjust(35) + "\n"
            if self.allowDeprecatedApplications:       
                partB = 'Install Asimba SAML Proxy'.ljust(30) + repr(self.installAsimba).rjust(35) + "\n"
            else:
                partB = ''

            partC = 'Install oxAuth RP'.ljust(30) + repr(self.installOxAuthRP).rjust(35) + "\n" \
                    + 'Install Passport '.ljust(30) + repr(self.installPassport).rjust(35) + "\n"
            return partA + partB + partC
        except:
            s = ""
            for key in self.__dict__.keys():
                val = self.__dict__[key]
                s = s + "%s\n%s\n%s\n\n" % (key, "-" * len(key), val)
            return s

    def initialize(self):
        self.install_time_ldap = time.strftime('%Y%m%d%H%M%SZ', time.gmtime(time.time()))

    def set_ownership(self):
        self.logIt("Changing ownership")
        realCertFolder = os.path.realpath(self.certFolder)
        realConfigFolder = os.path.realpath(self.configFolder)
        realOptPythonFolderFolder = os.path.realpath(self.gluuOptPythonFolder)
        realAsimbaJks = os.path.realpath(self.asimbaJksFn)

        self.run([self.cmd_chown, '-R', 'root:gluu', realCertFolder])
        self.run([self.cmd_chown, '-R', 'root:gluu', realConfigFolder])
        self.run([self.cmd_chown, '-R', 'root:gluu', realOptPythonFolderFolder])
        self.run([self.cmd_chown, '-R', 'root:gluu', self.oxBaseDataFolder])

        # Set right permissions
        self.run([self.cmd_chmod, '-R', '440', realCertFolder])
        self.run([self.cmd_chmod, 'a+X', realCertFolder])

        # Set write permission for Asimba's keystore (oxTrust can change it)
        self.run([self.cmd_chmod, 'u+w', realAsimbaJks])

        if self.installOxAuth:
            self.run([self.cmd_chown, '-R', 'jetty:jetty', self.oxauth_openid_jwks_fn])
            self.run([self.cmd_chown, '-R', 'jetty:jetty', self.oxauth_openid_jks_fn])
            self.run([self.cmd_chmod, '660', self.oxauth_openid_jwks_fn])
            self.run([self.cmd_chmod, '660', self.oxauth_openid_jks_fn])

        if self.installSaml:
            realIdp3Folder = os.path.realpath(self.idp3Folder)
            self.run([self.cmd_chown, '-R', 'jetty:jetty', realIdp3Folder])

    def set_permissions(self):
        self.logIt("Changing permissions")

        ### Below commands help us to set permissions readable if umask is set as 077
        self.run(['find', "/opt", '-user', 'root', '-perm', '700', '-exec', 'chmod', "755", '{}',  ';'])
        self.run(['find', "/opt", '-user', 'root', '-perm', '600', '-exec', 'chmod', "644", '{}',  ';'])
        self.run(['find', "/opt", '-user', 'root', '-perm', '400', '-exec', 'chmod', "444", '{}',  ';'])

        self.run(['find', "%s" % self.gluuBaseFolder, '-perm', '700', '-exec', self.cmd_chmod, "755", '{}', ';'])
        self.run(['find', "%s" % self.gluuBaseFolder, '-perm', '600', '-exec', self.cmd_chmod, "644", '{}', ';'])

        self.run(['find', "%s" % self.osDefault, '-perm', '700', '-exec', self.cmd_chmod, "755", '{}', ';'])
        self.run(['find', "%s" % self.osDefault, '-perm', '600', '-exec', self.cmd_chmod, "644", '{}', ';'])

        self.run(['/bin/chmod', '-R', '644', self.etc_hosts])

        if self.os_type in ['debian', 'ubuntu']:
            self.run(['/bin/chmod', '-f', '644', self.etc_hostname])

        if self.installSaml:
            realIdp3Folder = os.path.realpath(self.idp3Folder)
            realIdp3BinFolder = "%s/bin" % realIdp3Folder;
            if os.path.exists(realIdp3BinFolder):
                self.run(['find', realIdp3BinFolder, '-name', '*.sh', '-exec', 'chmod', "755", '{}',  ';'])

    def get_ip(self):
        testIP = None
        detectedIP = None
        try:
            testSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            detectedIP = [(testSocket.connect(('8.8.8.8', 80)),
                           testSocket.getsockname()[0],
                           testSocket.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]
        except:
            self.logIt("No detected IP address", True)
            self.logIt(traceback.format_exc(), True)

        while not testIP:
            if detectedIP:
                testIP = self.getPrompt("Enter IP Address", detectedIP)
            else:
                testIP = self.getPrompt("Enter IP Address")
            if not self.isIP(testIP):
                testIP = None
                print 'ERROR: The IP Address is invalid. Try again\n'

        return testIP

    def check_installed(self):
        return os.path.exists(self.configFolder)

    def check_properties(self):
        self.logIt('Checking properties')
        while not self.hostname:
            testhost = raw_input('Hostname of this server: ').strip()
            if len(testhost.split('.')) >= 3:
                self.hostname = testhost
            else:
                print 'The hostname has to be at least three domain components. Try again\n'
        while not self.ip:
            self.ip = self.get_ip()
        while not self.orgName:
            self.orgName = raw_input('Organization Name: ').strip()
        while not self.countryCode:
            testCode = raw_input('2 Character Country Code: ').strip()
            if len(testCode) == 2:
                self.countryCode = testCode
            else:
                print 'Country code should only be two characters. Try again\n'
        while not self.city:
            self.city = raw_input('City: ').strip()
        while not self.state:
            self.state = raw_input('State or Province: ').strip()
        if not self.admin_email:
            tld = None
            try:
                tld = ".".join(self.hostname.split(".")[-2:])
            except:
                tld = self.hostname
            self.admin_email = "support@%s" % tld
        if not self.httpdKeyPass:
            self.httpdKeyPass = self.getPW()
        if not self.ldapPass:
            self.ldapPass = self.getPW()
        if not self.shibJksPass:
            self.shibJksPass = self.getPW()
        if not self.oxauth_openid_jks_pass:
            self.oxauth_openid_jks_pass = self.getPW()
        if not self.asimbaJksPass:
            self.asimbaJksPass = self.getPW()
        if not self.openldapKeyPass:
            self.openldapKeyPass = self.getPW()
            self.openldapJksPass = self.getPW()
        if not self.opendj_p12_pass:
            self.opendj_p12_pass = self.getPW()
        if not self.passportSpKeyPass:
            self.passportSpKeyPass = self.getPW()
            self.passportSpJksPass = self.getPW()
        if not self.encode_salt:
            self.encode_salt= self.getPW() + self.getPW()
        if not self.baseInum:
            self.baseInum = '@!%s.%s.%s.%s' % tuple([self.getQuad() for i in xrange(4)])
        if not self.inumOrg:
            orgTwoQuads = '%s.%s' % tuple([self.getQuad() for i in xrange(2)])
            self.inumOrg = '%s!0001!%s' % (self.baseInum, orgTwoQuads)
        if not self.inumAppliance:
            applianceTwoQuads = '%s.%s' % tuple([self.getQuad() for i in xrange(2)])
            self.inumAppliance = '%s!0002!%s' % (self.baseInum, applianceTwoQuads)
        if not self.oxauth_client_id:
            clientTwoQuads = '%s.%s' % tuple([self.getQuad() for i in xrange(2)])
            self.oxauth_client_id = '%s!0008!%s' % (self.inumOrg, clientTwoQuads)
        if not self.idp_client_id:
            clientTwoQuads = '%s.%s' % tuple([self.getQuad() for i in xrange(2)])
            self.idp_client_id = '%s!0008!%s' % (self.inumOrg, clientTwoQuads)
        if not self.scim_rs_client_id:
            scimClientTwoQuads = '%s.%s' % tuple([self.getQuad() for i in xrange(2)])
            self.scim_rs_client_id = '%s!0008!%s' % (self.inumOrg, scimClientTwoQuads)
        if not self.scim_rp_client_id:
            scimClientTwoQuads = '%s.%s' % tuple([self.getQuad() for i in xrange(2)])
            self.scim_rp_client_id = '%s!0008!%s' % (self.inumOrg, scimClientTwoQuads)
        if not self.scim_resource_oxid:
            self.scim_resource_oxid = str(uuid.uuid4())
        if not self.passport_rs_client_id:
            passportClientTwoQuads = '%s.%s' % tuple([self.getQuad() for i in xrange(2)])
            self.passport_rs_client_id = '%s!0008!%s' % (self.inumOrg, passportClientTwoQuads)
        if not self.passport_rp_client_id:
            passportClientTwoQuads = '%s.%s' % tuple([self.getQuad() for i in xrange(2)])
            self.passport_rp_client_id = '%s!0008!%s' % (self.inumOrg, passportClientTwoQuads)
        if not self.inumApplianceFN:
            self.inumApplianceFN = self.inumAppliance.replace('@', '').replace('!', '').replace('.', '')
        if not self.inumOrgFN:
            self.inumOrgFN = self.inumOrg.replace('@', '').replace('!', '').replace('.', '')
        if not self.application_max_ram:
            self.application_max_ram = 3072

    def choose_from_list(self, list_of_choices, choice_name="item", default_choice_index=0):
        return_value = None
        choice_map = {}
        chosen_index = 0
        print "\nSelect the number for the %s from the following list:" % choice_name
        for choice in list_of_choices:
            choice_map[chosen_index] = choice
            chosen_index += 1
            print "  [%i]   %s" % (chosen_index, choice)
        while not return_value:
            choice_number = self.getPrompt("Please select a number listed above", str(default_choice_index + 1))
            try:
                choice_number = int(choice_number) - 1
                if (choice_number >= 0) & (choice_number < len(list_of_choices)):
                    return_value = choice_map[choice_number]
                else:
                    print '"%i" is not a valid choice' % (choice_number + 1)
            except:
                print 'Cannot convert "%s" to a number' % choice_number
                self.logIt(traceback.format_exc(), True)
        return return_value


    def enable_service_at_start(self, serviceName, startSequence=None, stopSequence=None):
        # Enable service autoload on Gluu-Server startup
        if self.os_type in ['centos', 'fedora', 'red']:
            if self.os_initdaemon == 'systemd':
                self.run(["/usr/bin/systemctl", 'enable', serviceName])
            else:
                self.run(["/sbin/chkconfig", serviceName, "on"])
        elif self.os_type in ['ubuntu', 'debian']:
            cmd_list = ["/usr/sbin/update-rc.d", serviceName, 'defaults']
            if startSequence and stopSequence:
                cmd_list.append(str(startSequence))
                cmd_list.append(str(stopSequence))
            elif self.os_type+self.os_version == 'ubuntu14':
                cmd_list.append(str(self.service_requirements[serviceName][1]))
                cmd_list.append(str(100 - self.service_requirements[serviceName][1]))
            
            self.run(cmd_list)

    # = File system  =================================================================
    def findFiles(self, filePatterns, filesFolder):
        foundFiles = []
        try:
            for filePattern in filePatterns:
                fileFullPathPattern = "%s/%s" % (filesFolder, filePattern)
                for fileFullPath in glob.iglob(fileFullPathPattern):
                    foundFiles.append(fileFullPath)
        except:
            self.logIt("Error finding files %s in folder %s" % (":".join(filePatterns), filesFolder), True)
            self.logIt(traceback.format_exc(), True)

        return foundFiles

    def readFile(self, inFilePath, logError=True):
        inFilePathText = None

        try:
            f = open(inFilePath)
            inFilePathText = f.read()
            f.close
        except:
            if logError:
                self.logIt("Error reading %s" % inFilePathText, True)
                self.logIt(traceback.format_exc(), True)

        return inFilePathText

    def writeFile(self, outFilePath, text):
        inFilePathText = None
        self.backupFile(outFilePath)
        try:
            f = open(outFilePath, 'w')
            f.write(text)
            f.close()
        except:
            self.logIt("Error writing %s" % inFilePathText, True)
            self.logIt(traceback.format_exc(), True)

        return inFilePathText

    def insertLinesInFile(self, inFilePath, index, text):        
            inFilePathLines = None                    
            try:            
                f = open(inFilePath, "r")            
                inFilePathLines = f.readlines()            
                f.close()
                try:
                    self.backupFile(inFilePath)
                    inFilePathLines.insert(index, text)            
                    f = open(inFilePath, "w")            
                    inFilePathLines = "".join(inFilePathLines)            
                    f.write(inFilePathLines)            
                    f.close()        
                except:            
                    self.logIt("Error writing %s" % inFilePathLines, True)            
                    self.logIt(traceback.format_exc(), True)
            except:            
                self.logIt("Error reading %s" % inFilePathLines, True)
                self.logIt(traceback.format_exc(), True)        
                    
    def commentOutText(self, text):
        textLines = text.split('\n')

        lines = []
        for textLine in textLines:
            lines.append('#%s' % textLine)

        return "\n".join(lines)

    def replaceInText(self, text, pattern, update):
        rePattern = re.compile(pattern,  flags=re.DOTALL | re.M)
        return rePattern.sub(update, text)

    def applyChangesInFiles(self, changes):
        self.logIt("Applying changes to %s files..." % changes['name'])
        for change in changes['files']:
            file = change['path']

            text = self.readFile(file)
            file_backup = '%s.bak' % file
            self.writeFile(file_backup, text)
            self.logIt("Created backup of %s file %s..." % (changes['name'], file_backup))

            for replace in change['replace']:
                text = self.replaceInText(text, replace['pattern'], replace['update'])

            self.writeFile(file, text)
            self.logIt("Wrote updated %s file %s..." % (changes['name'], file))

    def logOSChanges(self, text):
        F=open("os-changes.log","a")
        F.write(text+"\n")
        F.close()

    def backupFile(self, inFile, destFolder=None):

        if destFolder:
            if os.path.isfile(destFolder):
                destFile = destFolder
            else:
                inFolder, inName = os.path.split(inFile)
                destFile = os.path.join(destFolder, inName)
        else:
            destFile = inFile

        if not destFile.startswith('/opt'):
            backupFile = destFile+'.gluu-'+self.currentGluuVersion+'~'
            if os.path.exists(destFile) and not os.path.exists(backupFile):
                shutil.copy(destFile, backupFile)
                self.logOSChanges("File %s was backed up as %s" % (destFile, backupFile))

    def copyFile(self, inFile, destFolder):
        self.backupFile(inFile, destFolder)
        try:
            shutil.copy(inFile, destFolder)
            self.logIt("Copied %s to %s" % (inFile, destFolder))
        except:
            self.logIt("Error copying %s to %s" % (inFile, destFolder), True)
            self.logIt(traceback.format_exc(), True)

    def copyTree(self, src, dst, overwrite=False):
        try:
            if not os.path.exists(dst):
                os.makedirs(dst)

            for item in os.listdir(src):
                s = os.path.join(src, item)
                d = os.path.join(dst, item)
                if os.path.isdir(s):
                    self.copyTree(s, d, overwrite)
                else:
                    if overwrite and os.path.exists(d):
                        self.removeFile(d)

                    if not os.path.exists(d) or os.stat(s).st_mtime - os.stat(d).st_mtime > 1:
                        shutil.copy2(s, d)
                        self.backupFile(s, d)

            self.logIt("Copied tree %s to %s" % (src, dst))
        except:
            self.logIt("Error copying tree %s to %s" % (src, dst), True)
            self.logIt(traceback.format_exc(), True)

    def createDirs(self, name):
        try:
            if not os.path.exists(name):
                os.makedirs(name, 0700)
                self.logIt('Created dir: %s' % name)
        except:
            self.logIt("Error making directory %s" % name, True)
            self.logIt(traceback.format_exc(), True)

    def removeDirs(self, name):
        try:
            if os.path.exists(name):
                shutil.rmtree(name)
                self.logIt('Removed dir: %s' % name)
        except:
            self.logIt("Error removing directory %s" % name, True)
            self.logIt(traceback.format_exc(), True)

    def removeFile(self, fileName):
        try:
            if os.path.exists(fileName):
                os.remove(fileName)
                self.logIt('Removed file: %s' % fileName)
        except:
            self.logIt("Error removing file %s" % fileName, True)
            self.logIt(traceback.format_exc(), True)

    # = Utilities ====================================================================

    def logIt(self, msg, errorLog=False):
        if errorLog:
            f = open(self.logError, 'a')
            f.write('%s %s\n' % (time.strftime('%X %x'), msg))
            f.close()
        f = open(self.log, 'a')
        f.write('%s %s\n' % (time.strftime('%X %x'), msg))
        f.close()

    def appendLine(self, line, fileName=False):
        
        self.backupFile(fileName)
        
        try:
            f = open(fileName, 'a')
            f.write('%s\n' % line)
            f.close()
        except:
            self.logIt("Error loading file %s" % fileName)

    def set_ulimits(self):
        try:
            if self.os_type in ['centos', 'red', 'fedora']:
                apache_user = 'apache'
            else:
                apache_user = 'www-data'

            self.appendLine("ldap       soft nofile     131072", "/etc/security/limits.conf")
            self.appendLine("ldap       hard nofile     262144", "/etc/security/limits.conf")
            self.appendLine("%s     soft nofile     131072" % apache_user, "/etc/security/limits.conf")
            self.appendLine("%s     hard nofile     262144" % apache_user, "/etc/security/limits.conf")
            self.appendLine("jetty      soft nofile     131072", "/etc/security/limits.conf")
            self.appendLine("jetty      hard nofile     262144", "/etc/security/limits.conf")
        except:
            self.logIt("Could not set limits.")
            self.logIt(traceback.format_exc(), True)

    def load_properties(self, fn):
        self.logIt('Loading Properties %s' % fn)
        p = Properties.Properties()
        try:
            p.load(open(fn))
            properties_list = p.keys()
            for prop in properties_list:
                try:
                    self.__dict__[prop] = p[prop]
                    if p[prop] == 'True':
                        self.__dict__[prop] = True
                    elif p[prop] == 'False':
                        self.__dict__[prop] = False
                except:
                    self.logIt("Error loading property %s" % prop)
                    self.logIt(traceback.format_exc(), True)
        except:
            self.logIt("Error loading properties", True)
            self.logIt(traceback.format_exc(), True)

    def load_json(self, fn):
        self.logIt('Loading JSON from %s' % fn)
        try:
            json_file = open(fn)
            json_text = json_file.read()
            json_file.close()
            return json.loads(json_text)
        except:
            self.logIt("Unable to read or parse json file from %s" % fn, True)
            self.logIt(traceback.format_exc(), True)
        return None

    def obscure(self, data=""):
        engine = triple_des(self.encode_salt, ECB, pad=None, padmode=PAD_PKCS5)
        data = data.encode('ascii')
        en_data = engine.encrypt(data)
        return base64.b64encode(en_data)

    # ================================================================================

    def configure_httpd(self):
        # Detect sevice path and apache service name
        service_path = '/sbin/service'
        apache_service_name = 'httpd'
        if self.os_type in ['debian', 'ubuntu']:
            service_path = '/usr/sbin/service'
            apache_service_name = 'apache2'

        self.run([service_path, apache_service_name, 'stop'])

        # CentOS 7.* + systemd + apache 2.4
        if self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd' and self.apache_version == "2.4":
            self.copyFile(self.apache2_24_conf, '/etc/httpd/conf/httpd.conf')
            self.copyFile(self.apache2_ssl_24_conf, '/etc/httpd/conf.d/https_gluu.conf')

        # CentOS 6.* + init + apache 2.2
        if self.os_type == 'centos' and self.os_initdaemon == 'init':
            self.copyFile(self.apache2_conf, '/etc/httpd/conf/httpd.conf')
            self.copyFile(self.apache2_ssl_conf, '/etc/httpd/conf.d/https_gluu.conf')
        if self.os_type in ['red', 'fedora'] and self.os_initdaemon == 'init':
            self.copyFile(self.apache2_conf, '/etc/httpd/conf/httpd.conf')
            self.copyFile(self.apache2_ssl_conf, '/etc/httpd/conf.d/https_gluu.conf')
        if self.os_type in ['debian', 'ubuntu']:
            self.copyFile(self.apache2_ssl_conf, '/etc/apache2/sites-available/https_gluu.conf')
            self.run([self.cmd_ln, '-s', '/etc/apache2/sites-available/https_gluu.conf',
                      '/etc/apache2/sites-enabled/https_gluu.conf'])

        self.run([service_path, apache_service_name, 'start'])

    def copy_output(self):
        self.logIt("Copying rendered templates to final destination")

        for dest_fn in self.ce_templates.keys():
            if self.ce_templates[dest_fn]:
                fn = os.path.split(dest_fn)[-1]
                output_fn = os.path.join(self.outputFolder, fn)
                try:
                    self.logIt("Copying %s to %s" % (output_fn, dest_fn))
                    dest_dir = os.path.dirname(dest_fn)
                    if not os.path.exists(dest_dir):
                        self.logIt("Created destination folder %s" % dest_dir)
                        os.makedirs(dest_dir)
                    self.backupFile(output_fn, dest_fn)
                    shutil.copyfile(output_fn, dest_fn)
                except:
                    self.logIt("Error writing %s to %s" % (output_fn, dest_fn), True)
                    self.logIt(traceback.format_exc(), True)

    def copy_scripts(self):
        self.logIt("Copying script files")
        for script in self.gluuScriptFiles:
            self.copyFile(script, self.gluuOptBinFolder)
        self.logIt("Rendering encode.py")
        try:
            f = open('%s/encode.py' % self.templateFolder)
            encode_script = f.read()
            f.close()
            f = open("%s/encode.py" % self.gluuOptBinFolder, 'w')
            f.write(encode_script % self.merge_dicts(self.__dict__, self.templateRenderingDict))
            f.close()
        except:
            self.logIt("Error rendering encode script")
            self.logIt(traceback.format_exc(), True)
        self.run([self.cmd_chmod, '-R', '700', self.gluuOptBinFolder])

    def copy_static(self):
        if self.installOxAuth:
            self.copyFile("%s/static/auth/lib/duo_web.py" % self.install_dir, "%s/libs" % self.gluuOptPythonFolder)
            self.copyFile("%s/static/auth/conf/duo_creds.json" % self.install_dir, "%s/" % self.certFolder)
            self.copyFile("%s/static/auth/conf/gplus_client_secrets.json" % self.install_dir, "%s/" % self.certFolder)
            self.copyFile("%s/static/auth/conf/super_gluu_creds.json" % self.install_dir, "%s/" % self.certFolder)
            self.copyFile("%s/static/auth/conf/vericloud_gluu_creds.json" % self.install_dir, "%s/" % self.certFolder)
            self.copyFile("%s/static/auth/conf/cert_creds.json" % self.install_dir, "%s/" % self.certFolder)
            self.copyFile("%s/static/auth/conf/otp_configuration.json" % self.install_dir, "%s/" % self.certFolder)
            
            # Fido2 authenticators
            self.copyFile("%s/static/auth/fido2//authenticator_cert/yubico-u2f-ca-certs.crt" % self.install_dir, "%s/%s" % (self.fido2ConfigFolder, '/authenticator_cert'))
            self.copyFile("%s/static/auth/fido2//authenticator_cert/yubico-u2f-ca-certs.txt" % self.install_dir, "%s/%s" % (self.fido2ConfigFolder, '/authenticator_cert'))
            self.copyFile("%s/static/auth/fido2//authenticator_cert/yubico-u2f-ca-certs.json" % self.install_dir, "%s/%s" % (self.fido2ConfigFolder, '/authenticator_cert'))

    def detect_os_type(self):
        try:
            p = platform.linux_distribution()
            os_type = p[0].split()[0].lower()
            os_version = p[1].split('.')[0]
            return os_type, os_version
        except:
            return self.choose_from_list(self.os_types, "Operating System")

    def detect_initd(self):
        return open(os.path.join('/proc/1/status'), 'r').read().split()[1]

    def determineApacheVersion(self, apache_cmd):
        cmd = "/usr/sbin/%s -v | egrep '^Server version'" % apache_cmd
        PIPE = subprocess.PIPE
        p = subprocess.Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=subprocess.STDOUT, close_fds=True, cwd=None)
        apache_version = p.stdout.read().strip().split(' ')[2].split('/')[1]
        if re.match(r'2\.4\..*', apache_version):
            return "2.4"

        return "2.2"

    def determineApacheVersionForOS(self):
        if self.os_type in ['centos', 'red', 'fedora']:
            # httpd -v
            # Server version: Apache/2.2.15 (Unix)  /etc/redhat-release  CentOS release 6.7 (Final)
            # OR
            # Server version: Apache/2.4.6 (CentOS) /etc/redhat-release  CentOS Linux release 7.1.1503 (Core)
            return self.determineApacheVersion("httpd")
        else:
            return self.determineApacheVersion("apache2")

    def determineOpenDJVersion(self):
        f = open('/opt/opendj/template/config/buildinfo', 'r')
        encode_script = f.read().split()[0]
        f.close()

        if re.match(r'2\.6\.0\..*', encode_script):
            return "2.6"

        return "3.0"

    def installJRE(self):
        self.logIt("Installing server JRE 1.8 %s..." % self.jre_version)

        if self.java_type == 'jre':
            jreArchive = 'amazon-corretto-{}-linux-x64.tar.gz'.format(self.jre_version)
        else:
            self.logIt("Downloading " + self.open_jdk_archive_link)
            jreArchive = os.path.basename(self.open_jdk_archive_link)
            self.run(['wget', '-nv', self.open_jdk_archive_link, '-O', os.path.join(self.distAppFolder, jreArchive)])

        try:
            self.logIt("Extracting %s into /opt/" % jreArchive)
            self.run(['tar', '-xzf', '%s/%s' % (self.distAppFolder, jreArchive), '-C', '/opt/', '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
        except:
            self.logIt("Error encountered while extracting archive %s" % jreArchive)
            self.logIt(traceback.format_exc(), True)

        if self.java_type == 'jdk':
            self.jreDestinationPath = max(glob.glob('/opt/jdk-11*'))

        self.run([self.cmd_ln, '-sf', self.jreDestinationPath, self.jre_home])
        self.run([self.cmd_chmod, '-R', "755", "%s/bin/" % self.jreDestinationPath])
        self.run([self.cmd_chown, '-R', 'root:root', self.jreDestinationPath])
        self.run([self.cmd_chown, '-h', 'root:root', self.jre_home])
        
        if self.java_type == 'jre':
            self.run(['sed', '-i', '/^#crypto.policy=unlimited/s/^#//', '%s/jre/lib/security/java.security' % self.jre_home])

    def extractOpenDJ(self):
        if self.opendj_type == 'opendj':
            openDJArchive = max(glob.glob(os.path.join(self.distFolder, 'app/opendj-server-*3*gluu*.zip')))
        else:
            openDJArchive = max(glob.glob(os.path.join(self.distFolder, 'app/opendj-server-*4*.zip')))

        try:
            self.logIt("Unzipping %s in /opt/" % openDJArchive)
            self.run(['unzip', '-n', '-q', openDJArchive, '-d', '/opt/' ])
        except:
            self.logIt("Error encountered while doing unzip %s/%s -d /opt/" % (self.distAppFolder, openDJArchive))
            self.logIt(traceback.format_exc(), True)

        realLdapBaseFolder = os.path.realpath(self.ldapBaseFolder)
        self.run([self.cmd_chown, '-R', 'ldap:ldap', realLdapBaseFolder])

    def installJetty(self):
        self.logIt("Installing jetty %s..." % self.jetty_version)

        jettyTemp = '%s/temp' % self.jetty_dist
        self.run([self.cmd_mkdir, '-p', jettyTemp])
        self.run([self.cmd_chown, '-R', 'jetty:jetty', jettyTemp])

        jettyArchive = 'jetty-distribution-%s.tar.gz' % self.jetty_version
        jettyDestinationPath = '%s/jetty-distribution-%s' % (self.jetty_dist, self.jetty_version)
        try:
            self.logIt("Extracting %s into /opt/jetty" % jettyArchive)
            self.run(['tar', '-xzf', '%s/%s' % (self.distAppFolder, jettyArchive), '-C', self.jetty_dist, '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
        except:
            self.logIt("Error encountered while extracting archive %s" % jettyArchive)
            self.logIt(traceback.format_exc(), True)

        self.run([self.cmd_ln, '-sf', jettyDestinationPath, self.jetty_home])
        self.run([self.cmd_chmod, '-R', "755", "%s/bin/" % jettyDestinationPath])

        self.applyChangesInFiles(self.app_custom_changes['jetty'])

        self.run([self.cmd_chown, '-R', 'jetty:jetty', jettyDestinationPath])
        self.run([self.cmd_chown, '-h', 'jetty:jetty', self.jetty_home])

        self.run([self.cmd_mkdir, '-p', self.jetty_base])
        self.run([self.cmd_chown, '-R', 'jetty:jetty', self.jetty_base])

        jettyRunFolder = '/var/run/jetty'
        self.run([self.cmd_mkdir, '-p', jettyRunFolder])
        self.run([self.cmd_chmod, '-R', '775', jettyRunFolder])
        self.run([self.cmd_chgrp, '-R', 'jetty', jettyRunFolder])

    def installNode(self):
        self.logIt("Installing node %s..." % self.node_version)

        nodeArchive = 'node-v%s-linux-x64.tar.xz' % self.node_version
        nodeDestinationPath = '/opt/node-v%s-linux-x64' % self.node_version
        try:
            self.logIt("Extracting %s into /opt" % nodeArchive)
            self.run(['tar', '-xJf', '%s/%s' % (self.distAppFolder, nodeArchive), '-C', '/opt/', '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
        except:
            self.logIt("Error encountered while extracting archive %s" % nodeArchive)
            self.logIt(traceback.format_exc(), True)

        self.run([self.cmd_ln, '-sf', nodeDestinationPath, self.node_home])
        self.run([self.cmd_chmod, '-R', "755", "%s/bin/" % nodeDestinationPath])

        # Create temp folder
        self.run([self.cmd_mkdir, '-p', "%s/temp" % self.node_home])

        # Copy init.d script
        self.copyFile(self.node_initd_script, self.gluuOptSystemFolder)
        self.copyFile(self.passport_initd_script, self.gluuOptSystemFolder)
        self.run([self.cmd_chmod, '-R', "755", "%s/node" % self.gluuOptSystemFolder])
        self.run([self.cmd_chmod, '-R', "755", "%s/passport" % self.gluuOptSystemFolder])

        self.run([self.cmd_chown, '-R', 'node:node', nodeDestinationPath])
        self.run([self.cmd_chown, '-h', 'node:node', self.node_home])

        self.run([self.cmd_mkdir, '-p', self.node_base])
        self.run([self.cmd_chown, '-R', 'node:node', self.node_base])

    def fix_init_scripts(self, serviceName, initscript_fn):

        changeTo = None
        os_ = self.os_type + self.os_version

        if self.ldap_type == 'openldap':
            changeTo = 'slapd'

        if changeTo != None:
            for service in self.service_requirements:
                self.service_requirements[service][0] = self.service_requirements[service][0].replace('opendj', changeTo)

        initscript = open(initscript_fn).readlines()
        
        for i,l in enumerate(initscript):
            if l.startswith('# Provides:'):
                initscript[i] = '# Provides:          {0}\n'.format(serviceName)
            elif l.startswith('# description:'):
                initscript[i] = '# description: Jetty 9 {0}\n'.format(serviceName)
            elif l.startswith('# Required-Start:'):
                initscript[i] = '# Required-Start:    $local_fs $network {0}\n'.format(self.service_requirements[serviceName][0])
            elif l.startswith('# chkconfig:'):
                initscript[i] = '# chkconfig: 345 {0} {1}\n'.format(self.service_requirements[serviceName][1], 100 - self.service_requirements[serviceName][1])
        
        service_init_script_fn = os.path.join('/etc/init.d', serviceName)
        with open(service_init_script_fn, 'w') as W:
            W.write(''.join(initscript))

        self.run([self.cmd_chmod, '+x', service_init_script_fn])


    def installJettyService(self, serviceConfiguration, supportCustomizations=False):
        serviceName = serviceConfiguration['name']
        self.logIt("Installing jetty service %s..." % serviceName)
        jettyServiceBase = '%s/%s' % (self.jetty_base, serviceName)
        jettyModules = serviceConfiguration['jetty']['modules']
        jettyModulesList = jettyModules.split(',')

        self.logIt("Preparing %s service base folders" % serviceName)
        self.run([self.cmd_mkdir, '-p', jettyServiceBase])

        # Create ./ext/lib folder for custom libraries only if installed Jetty "ext" module
        if "ext" in jettyModulesList:
            self.run([self.cmd_mkdir, '-p', "%s/lib/ext" % jettyServiceBase])

        # Create ./custom/pages and ./custom/static folders for custom pages and static resources, only if application supports them
        if supportCustomizations:
            if not os.path.exists("%s/custom" % jettyServiceBase):
                self.run([self.cmd_mkdir, '-p', "%s/custom" % jettyServiceBase])
            self.run([self.cmd_mkdir, '-p', "%s/custom/i18n" % jettyServiceBase])
            self.run([self.cmd_mkdir, '-p', "%s/custom/pages" % jettyServiceBase])
            self.run([self.cmd_mkdir, '-p', "%s/custom/static" % jettyServiceBase])
            self.run([self.cmd_mkdir, '-p', "%s/custom/libs" % jettyServiceBase])

        self.logIt("Preparing %s service base configuration" % serviceName)
        jettyEnv = os.environ.copy()
        jettyEnv['PATH'] = '%s/bin:' % self.jre_home + jettyEnv['PATH']

        self.run([self.cmd_java, '-jar', '%s/start.jar' % self.jetty_home, 'jetty.home=%s' % self.jetty_home, 'jetty.base=%s' % jettyServiceBase, '--add-to-start=%s' % jettyModules], None, jettyEnv)
        self.run([self.cmd_chown, '-R', 'jetty:jetty', jettyServiceBase])

        try:
            self.renderTemplateInOut(serviceName, '%s/jetty' % self.templateFolder, '%s/jetty' % self.outputFolder)
        except:
            self.setup.logIt("Error rendering service '%s' defaults" % serviceName, True)
            self.setup.logIt(traceback.format_exc(), True)

        jettyServiceConfiguration = '%s/jetty/%s' % (self.outputFolder, serviceName)
        self.copyFile(jettyServiceConfiguration, "/etc/default")
        self.run([self.cmd_chown, 'root:root', "/etc/default/%s" % serviceName])

        try:
            web_resources = '%s_web_resources.xml' % serviceName
            if os.path.exists('%s/jetty/%s' % (self.templateFolder, web_resources)):
                self.renderTemplateInOut(web_resources, '%s/jetty' % self.templateFolder, '%s/jetty' % self.outputFolder)
                self.copyFile('%s/jetty/%s' % (self.outputFolder, web_resources), self.jetty_base+"/"+serviceName+"/webapps")
        except:
            self.setup.logIt("Error rendering service '%s' web_resources.xml" % serviceName, True)
            self.setup.logIt(traceback.format_exc(), True)

        initscript_fn = os.path.join(self.jetty_home, 'bin/jetty.sh')
        self.fix_init_scripts(serviceName, initscript_fn)

        self.enable_service_at_start(serviceName)

        tmpfiles_base = '/usr/lib/tmpfiles.d'
        if self.os_initdaemon == 'systemd' and os.path.exists(tmpfiles_base):
            self.logIt("Creating 'jetty.conf' tmpfiles daemon file")
            jetty_tmpfiles_src = '%s/jetty.conf.tmpfiles.d' % self.templateFolder
            jetty_tmpfiles_dst = '%s/jetty.conf' % tmpfiles_base
            self.copyFile(jetty_tmpfiles_src, jetty_tmpfiles_dst)
            self.run([self.cmd_chown, 'root:root', jetty_tmpfiles_dst])
            self.run([self.cmd_chmod, '644', jetty_tmpfiles_dst])

        serviceConfiguration['installed'] = True

    def installNodeService(self, serviceName):
        self.logIt("Installing node service %s..." % serviceName)

        nodeServiceConfiguration = '%s/node/%s' % (self.outputFolder, serviceName)
        self.copyFile(nodeServiceConfiguration, '/etc/default')
        self.run([self.cmd_chown, 'root:root', '/etc/default/%s' % serviceName])

        if serviceName == 'passport':
            initscript_fn = os.path.join(self.gluuOptSystemFolder, serviceName)
            self.fix_init_scripts(serviceName, initscript_fn)
        else:
            self.run([self.cmd_ln, '-sf', '%s/node' % self.gluuOptSystemFolder, '/etc/init.d/%s' % serviceName])

    def installJython(self):
        self.logIt("Installing Jython %s..." % self.jython_version)
        jythonInstaller = 'jython-%s.jar' % self.jython_version

        try:
            self.run(['rm', '-rf', '/opt*-%s' % self.jython_version])
            self.run([self.cmd_java, '-jar', '%s/jython-installer-%s.jar' % (self.distAppFolder, self.jython_version), '-v', '-s', '-d', '/opt/jython-%s' % self.jython_version, '-t', 'standard', '-e', 'ensurepip'])
        except:
            self.logIt("Error installing jython-installer-%s.jar" % self.jython_version)
            self.logIt(traceback.format_exc(), True)

        self.run([self.cmd_ln, '-sf', '/opt/jython-%s' % self.jython_version, self.jython_home])
        self.run([self.cmd_chown, '-R', 'root:root', '/opt/jython-%s' % self.jython_version])
        self.run([self.cmd_chown, '-h', 'root:root', self.jython_home])

    def downloadWarFiles(self):
        if self.downloadWars:
            self.pbar.progress("Downloading oxAuth war file")
            
            self.run(['/usr/bin/wget', self.oxauth_war, '--no-verbose', '--retry-connrefused', '--tries=10', '-O', '%s/oxauth.war' % self.distGluuFolder])
            self.pbar.progress("Downloading oxTrust war file", False)
            self.run(['/usr/bin/wget', self.oxtrust_war, '--no-verbose', '--retry-connrefused', '--tries=10', '-O', '%s/identity.war' % self.distGluuFolder])

        if self.installAsimba:
            # Asimba is not part of CE package. We need to download it if needed
            distAsimbaPath = '%s/%s' % (self.distGluuFolder, "asimba.war")
            if not os.path.exists(distAsimbaPath):
                self.pbar.progress("Downloading Asimba war file", False)
                self.run(['/usr/bin/wget', self.asimba_war, '--no-verbose', '--retry-connrefused', '--tries=10', '-O', '%s/asimba.war' % self.distGluuFolder])

        if self.installOxAuthRP:
            # oxAuth RP is not part of CE package. We need to download it if needed
            distOxAuthRpPath = '%s/%s' % (self.distGluuFolder, "oxauth-rp.war")
            if not os.path.exists(distOxAuthRpPath):
                self.pbar.progress("Downloading oxAuth RP war file", False)
                self.run(['/usr/bin/wget', self.oxauth_rp_war, '--no-verbose', '--retry-connrefused', '--tries=10', '-O', '%s/oxauth-rp.war' % self.distGluuFolder])

        if self.downloadWars and self.installSaml:
            
            self.pbar.progress("Downloading Shibboleth IDP v3 war file", False)
            self.run(['/usr/bin/wget', self.idp3_war, '--no-verbose', '-c', '--retry-connrefused', '--tries=10', '-O', '%s/idp.war' % self.distGluuFolder])
            self.pbar.progress("Downloading Shibboleth IDP v3 keygenerator", False)
            self.run(['/usr/bin/wget', self.idp3_cml_keygenerator, '--no-verbose', '-c', '--retry-connrefused', '--tries=10', '-O', self.distGluuFolder + '/idp3_cml_keygenerator.jar'])
            self.pbar.progress("Downloading Shibboleth IDP v3 binary distributive file", False)
            self.run(['/usr/bin/wget', self.idp3_dist_jar, '--no-verbose', '-c', '--retry-connrefused', '--tries=10', '-O', self.distGluuFolder + '/shibboleth-idp.jar'])


    def encode_passwords(self):
        self.logIt("Encoding passwords")
        try:
            self.encoded_ldap_pw = self.ldap_encode(self.ldapPass)
            self.encoded_shib_jks_pw = self.obscure(self.shibJksPass)
            self.encoded_ox_ldap_pw = self.obscure(self.ldapPass)
            self.encoded_openldapJksPass = self.obscure(self.openldapJksPass)
            self.encoded_opendj_p12_pass = self.obscure(self.opendj_p12_pass)

            self.oxauthClient_pw = self.getPW()
            self.oxauthClient_encoded_pw = self.obscure(self.oxauthClient_pw)

            self.idpClient_pw = self.getPW()
            self.idpClient_encoded_pw = self.obscure(self.idpClient_pw)
        except:
            self.logIt("Error encoding passwords", True)
            self.logIt(traceback.format_exc(), True)

    def encode_test_passwords(self):
        self.logIt("Encoding test passwords")
        try:
            self.templateRenderingDict['oxauthClient_2_pw'] = self.getPW()
            self.templateRenderingDict['oxauthClient_2_encoded_pw'] = self.obscure(self.templateRenderingDict['oxauthClient_2_pw'])

            self.templateRenderingDict['oxauthClient_3_pw'] = self.getPW()
            self.templateRenderingDict['oxauthClient_3_encoded_pw'] = self.obscure(self.templateRenderingDict['oxauthClient_3_pw'])

            self.templateRenderingDict['oxauthClient_4_pw'] = self.getPW()
            self.templateRenderingDict['oxauthClient_4_encoded_pw'] = self.obscure(self.templateRenderingDict['oxauthClient_4_pw'])
        except:
            self.logIt("Error encoding test passwords", True)
            self.logIt(traceback.format_exc(), True)

    def gen_cert(self, suffix, password, user='root', cn=None):
        self.logIt('Generating Certificate for %s' % suffix)
        key_with_password = '%s/%s.key.orig' % (self.certFolder, suffix)
        key = '%s/%s.key' % (self.certFolder, suffix)
        csr = '%s/%s.csr' % (self.certFolder, suffix)
        public_certificate = '%s/%s.crt' % (self.certFolder, suffix)
        self.run([self.opensslCommand,
                  'genrsa',
                  '-des3',
                  '-out',
                  key_with_password,
                  '-passout',
                  'pass:%s' % password,
                  '2048'
                  ])
        self.run([self.opensslCommand,
                  'rsa',
                  '-in',
                  key_with_password,
                  '-passin',
                  'pass:%s' % password,
                  '-out',
                  key
                  ])

        certCn = cn
        if certCn == None:
            certCn = self.hostname

        self.run([self.opensslCommand,
                  'req',
                  '-new',
                  '-key',
                  key,
                  '-out',
                  csr,
                  '-subj',
                  '/C=%s/ST=%s/L=%s/O=%s/CN=%s/emailAddress=%s' % (self.countryCode, self.state, self.city, self.orgName, certCn, self.admin_email)
                  ])
        self.run([self.opensslCommand,
                  'x509',
                  '-req',
                  '-days',
                  '365',
                  '-in',
                  csr,
                  '-signkey',
                  key,
                  '-out',
                  public_certificate
                  ])
        self.run([self.cmd_chown, '%s:%s' % (user, user), key_with_password])
        self.run([self.cmd_chmod, '700', key_with_password])
        self.run([self.cmd_chown, '%s:%s' % (user, user), key])
        self.run([self.cmd_chmod, '700', key])

        self.run([self.cmd_keytool, "-import", "-trustcacerts", "-alias", "%s_%s" % (self.hostname, suffix), \
                  "-file", public_certificate, "-keystore", self.defaultTrustStoreFN, \
                  "-storepass", "changeit", "-noprompt"])

    def generate_crypto(self):
        try:
            self.logIt('Generating certificates and keystores')
            self.gen_cert('httpd', self.httpdKeyPass, 'jetty')
            self.gen_cert('shibIDP', self.shibJksPass, 'jetty')
            self.gen_cert('idp-encryption', self.shibJksPass, 'jetty')
            self.gen_cert('idp-signing', self.shibJksPass, 'jetty')
            self.gen_cert('asimba', self.asimbaJksPass, 'jetty')

            if self.installLdap and self.ldap_type == 'openldap':
                self.gen_cert('openldap', self.openldapKeyPass, 'ldap', self.ldap_hostname)

            self.gen_cert('passport-sp', self.passportSpKeyPass, 'ldap', self.ldap_hostname)
            # Shibboleth IDP and Asimba will be added soon...
            self.gen_keystore('shibIDP',
                              self.shibJksFn,
                              self.shibJksPass,
                              '%s/shibIDP.key' % self.certFolder,
                              '%s/shibIDP.crt' % self.certFolder,
                              'jetty')
            self.gen_keystore('asimba',
                              self.asimbaJksFn,
                              self.asimbaJksPass,
                              '%s/asimba.key' % self.certFolder,
                              '%s/asimba.crt' % self.certFolder,
                              'jetty')
            if self.installLdap and self.ldap_type == 'openldap':
                self.gen_keystore('openldap',
                                  self.openldapJksFn,
                                  self.openldapJksPass,
                                  '%s/openldap.key' % self.certFolder,
                                  '%s/openldap.crt' % self.certFolder,
                                  'jetty')
            # samp.pem from asimba.crt for asimba scrypt input
            self.run([self.opensslCommand,
                      'x509',
                      '-inform',
                      'pem',
                      '-outform',
                      'pem',
                      '-in',
                      '%s/asimba.crt' % self.certFolder,
                      '-out',
                      '%s/saml.pem' % self.certFolder
                      ])
            # permissions
            self.run([self.cmd_chown, '-R', 'jetty:jetty', self.certFolder])
            self.run([self.cmd_chmod, '-R', '500', self.certFolder])
            # oxTrust UI can add key to asimba's keystore
            self.run([self.cmd_chmod, 'u+w', self.asimbaJksFn])
        except:
            self.logIt("Error generating cyrpto")
            self.logIt(traceback.format_exc(), True)

    def gen_keystore(self, suffix, keystoreFN, keystorePW, inKey, inCert, user='root'):
        self.logIt("Creating keystore %s" % suffix)
        # Convert key to pkcs12
        pkcs_fn = '%s/%s.pkcs12' % (self.certFolder, suffix)
        self.run([self.opensslCommand,
                  'pkcs12',
                  '-export',
                  '-inkey',
                  inKey,
                  '-in',
                  inCert,
                  '-out',
                  pkcs_fn,
                  '-name',
                  self.hostname,
                  '-passout',
                  'pass:%s' % keystorePW
                  ])
        # Import p12 to keystore
        self.run([self.cmd_keytool,
                  '-importkeystore',
                  '-srckeystore',
                  '%s/%s.pkcs12' % (self.certFolder, suffix),
                  '-srcstorepass',
                  keystorePW,
                  '-srcstoretype',
                  'PKCS12',
                  '-destkeystore',
                  keystoreFN,
                  '-deststorepass',
                  keystorePW,
                  '-deststoretype',
                  'JKS',
                  '-keyalg',
                  'RSA',
                  '-noprompt'
                  ])
        self.run([self.cmd_chown, '%s:%s' % (user, user), pkcs_fn])
        self.run([self.cmd_chmod, '700', pkcs_fn])
        self.run([self.cmd_chown, '%s:%s' % (user, user), keystoreFN])
        self.run([self.cmd_chmod, '700', keystoreFN])

    def gen_openid_jwks_jks_keys(self, jks_path, jks_pwd, jks_create = True, key_expiration = None, dn_name = None, key_algs = None, enc_keys=None):
        self.logIt("Generating oxAuth OpenID Connect keys")

        if dn_name == None:
            dn_name = self.default_openid_jks_dn_name

        if key_algs == None:
            key_algs = self.default_key_algs

        if not enc_keys:
            enc_keys = key_algs

        if key_expiration == None:
            key_expiration = self.default_key_expiration


        # We can remove this once KeyGenerator will do the same
        if jks_create == True:
            self.logIt("Creating empty JKS keystore")
            # Create JKS with dummy key
            cmd = " ".join([self.cmd_keytool,
                            '-genkey',
                            '-alias',
                            'dummy',
                            '-keystore',
                            jks_path,
                            '-storepass',
                            jks_pwd,
                            '-keypass',
                            jks_pwd,
                            '-dname',
                            '"%s"' % dn_name])
            self.run(['/bin/sh', '-c', cmd])

            # Delete dummy key from JKS
            cmd = " ".join([self.cmd_keytool,
                            '-delete',
                            '-alias',
                            'dummy',
                            '-keystore',
                            jks_path,
                            '-storepass',
                            jks_pwd,
                            '-keypass',
                            jks_pwd,
                            '-dname',
                            '"%s"' % dn_name])
            self.run(['/bin/sh', '-c', cmd])

        oxauth_lib_files = self.findFiles(self.oxauth_keys_utils_libs, self.jetty_user_home_lib)

        cmd = " ".join([self.cmd_java,
                        "-Dlog4j.defaultInitOverride=true",
                        "-cp",
                        ":".join(oxauth_lib_files),
                        "org.xdi.oxauth.util.KeyGenerator",
                        "-keystore",
                        jks_path,
                        "-keypasswd",
                        jks_pwd,
                        "-sig_keys",
                        "%s" % key_algs,
                        "-enc_keys",
                        "%s" % enc_keys,
                        "-dnname",
                        '"%s"' % dn_name,
                        "-expiration",
                        "%s" % key_expiration])
        args = ['/bin/sh', '-c', cmd]

        self.logIt("Runnning: %s" % " ".join(args))
        try:
            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, err = p.communicate()
            p.wait()
            if err:
                self.logIt(err, True)
            if output:
                return output.split(os.linesep)
        except:
            self.logIt("Error running command : %s" % " ".join(args), True)
            self.logIt(traceback.format_exc(), True)

        return None

    def export_openid_key(self, jks_path, jks_pwd, cert_alias, cert_path):
        self.logIt("Exporting oxAuth OpenID Connect keys")

        oxauth_lib_files = self.findFiles(self.oxauth_keys_utils_libs, self.jetty_user_home_lib)

        cmd = " ".join([self.cmd_java,
                        "-Dlog4j.defaultInitOverride=true",
                        "-cp",
                        ":".join(oxauth_lib_files),
                        "org.xdi.oxauth.util.KeyExporter",
                        "-keystore",
                        jks_path,
                        "-keypasswd",
                        jks_pwd,
                        "-alias",
                        cert_alias,
                        "-exportfile",
                        cert_path])
        self.run(['/bin/sh', '-c', cmd])

    def write_openid_keys(self, fn, jwks):
        self.logIt("Writing oxAuth OpenID Connect keys")
        if not jwks:
            self.logIt("Failed to write oxAuth OpenID Connect key to %s" % fn)
            return

        self.backupFile(fn)

        try:
            jwks_text = '\n'.join(jwks)
            f = open(fn, 'w')
            f.write(jwks_text)
            f.close()
            self.run([self.cmd_chown, 'jetty:jetty', fn])
            self.run([self.cmd_chmod, '600', fn])
            self.logIt("Wrote oxAuth OpenID Connect key to %s" % fn)
        except:
            self.logIt("Error writing command : %s" % fn, True)
            self.logIt(traceback.format_exc(), True)

    def generate_oxauth_openid_keys(self):
        sig_keys = 'RS256 RS384 RS512 ES256 ES384 ES512 PS256 PS384 PS512'
        enc_keys = 'RSA1_5 RSA-OAEP'
        jwks = self.gen_openid_jwks_jks_keys(self.oxauth_openid_jks_fn, self.oxauth_openid_jks_pass, key_algs=sig_keys, enc_keys=enc_keys)
        self.write_openid_keys(self.oxauth_openid_jwks_fn, jwks)

    def generate_base64_string(self, lines, num_spaces):
        if not lines:
            return None

        plain_text = ''.join(lines)
        plain_b64encoded_text = plain_text.encode('base64').strip()

        if num_spaces > 0:
            plain_b64encoded_text = self.reindent(plain_b64encoded_text, num_spaces)

        return plain_b64encoded_text

    def genRandomString(self, N):
        return ''.join(random.SystemRandom().choice(string.ascii_lowercase
                                                    + string.ascii_uppercase
                                                    + string.digits) for _ in range(N))

    def generate_scim_configuration(self):
        self.scim_rs_client_jks_pass = self.getPW()

        self.scim_rs_client_jks_pass_encoded = self.obscure(self.scim_rs_client_jks_pass)

        self.scim_rs_client_jwks = self.gen_openid_jwks_jks_keys(self.scim_rs_client_jks_fn, self.scim_rs_client_jks_pass)
        self.templateRenderingDict['scim_rs_client_base64_jwks'] = self.generate_base64_string(self.scim_rs_client_jwks, 1)

        self.scim_rp_client_jwks = self.gen_openid_jwks_jks_keys(self.scim_rp_client_jks_fn, self.scim_rp_client_jks_pass)
        self.templateRenderingDict['scim_rp_client_base64_jwks'] = self.generate_base64_string(self.scim_rp_client_jwks, 1)

    def generate_passport_configuration(self):
        self.passport_rs_client_jks_pass = self.getPW()

        self.passport_rs_client_jks_pass_encoded = self.obscure(self.passport_rs_client_jks_pass)

        self.passport_rs_client_jwks = self.gen_openid_jwks_jks_keys(self.passport_rs_client_jks_fn, self.passport_rs_client_jks_pass)
        self.templateRenderingDict['passport_rs_client_base64_jwks'] = self.generate_base64_string(self.passport_rs_client_jwks, 1)

        self.passport_rp_client_jwks = self.gen_openid_jwks_jks_keys(self.passport_rp_client_jks_fn, self.passport_rp_client_jks_pass)
        self.templateRenderingDict['passport_rp_client_base64_jwks'] = self.generate_base64_string(self.passport_rp_client_jwks, 1)

    def getPrompt(self, prompt, defaultValue=None):
        try:
            if defaultValue:
                user_input = raw_input("%s [%s] : " % (prompt, defaultValue)).strip()
                if user_input == '':
                    return defaultValue
                else:
                    return user_input
            else:
                input = False
                while not input:
                    user_input = raw_input("%s : " % prompt).strip()
                    if user_input != '':
                        input = True
                        return user_input
        except KeyboardInterrupt:
            sys.exit()
        except:
            return None

    def getPW(self, size=12, chars=string.ascii_uppercase + string.digits + string.lowercase):
        return ''.join(random.choice(chars) for _ in range(size))

    def getQuad(self):
        return str(uuid.uuid4())[:4].upper()

    def prepare_openid_keys_generator(self):
        self.logIt("Preparing files needed to run OpenId keys generator")
        # Unpack oxauth.war to get libs needed to run key generator
        oxauthWar = 'oxauth.war'
        distOxAuthPath = '%s/%s' % (self.distGluuFolder, oxauthWar)

        tmpOxAuthDir = '%s/tmp_oxauth' % self.distGluuFolder

        self.logIt("Unpacking %s..." % oxauthWar)
        self.removeDirs(tmpOxAuthDir)
        self.createDirs(tmpOxAuthDir)

        self.run([self.cmd_jar,
                  'xf',
                  distOxAuthPath], tmpOxAuthDir)

        tmpLibsOxAuthPath = '%s/WEB-INF/lib' % tmpOxAuthDir

        self.logIt("Copying files to %s..." % self.jetty_user_home_lib)
        oxauth_lib_files = self.findFiles(self.oxauth_keys_utils_libs, tmpLibsOxAuthPath)
        for oxauth_lib_file in oxauth_lib_files:
            self.copyFile(oxauth_lib_file, self.jetty_user_home_lib)

        self.removeDirs(tmpOxAuthDir)

    def install_gluu_base(self):
        self.logIt("Installing Gluu base...")
        self.prepare_openid_keys_generator()

        self.generate_scim_configuration()
        self.generate_passport_configuration()

        self.ldap_binddn = self.openldapRootUser
        self.ldap_site_binddn = self.openldapSiteUser

        if self.installLdap:
            if self.ldap_type == 'opendj':
                self.ldap_binddn = self.opendj_ldap_binddn
                self.ldap_site_binddn = self.opendj_ldap_binddn

                self.ldapCertFn = self.opendj_cert_fn
                self.ldapTrustStoreFn = self.opendj_p12_fn
                self.encoded_ldapTrustStorePass = self.encoded_opendj_p12_pass
            elif self.ldap_type == 'openldap':
                self.ldapCertFn = self.openldapTLSCert
                self.ldapTrustStoreFn = self.openldapP12Fn
                self.encoded_ldapTrustStorePass = self.encoded_openldapJksPass
                

        if self.installSaml:
            self.oxTrustConfigGeneration = "true"
        else:
            self.oxTrustConfigGeneration = "false"

    def load_certificate_text(self, filePath):
        self.logIt("Load certificate %s" % filePath)
        f = open(filePath)
        certificate_text = f.read()
        f.close()
        certificate_text = certificate_text.replace('-----BEGIN CERTIFICATE-----', '').replace('-----END CERTIFICATE-----', '').strip()
        return certificate_text

    def install_oxauth(self):
        self.logIt("Copying identity.war into jetty webapps folder...")

        jettyServiceName = 'oxauth'
        self.installJettyService(self.jetty_app_configuration[jettyServiceName], True)

        jettyServiceWebapps = '%s/%s/webapps' % (self.jetty_base, jettyServiceName)
        self.copyFile('%s/oxauth.war' % self.distGluuFolder, jettyServiceWebapps)

    def install_oxtrust(self):
        self.logIt("Copying oxauth.war into jetty webapps folder...")

        jettyServiceName = 'identity'
        self.installJettyService(self.jetty_app_configuration[jettyServiceName], True)

        jettyServiceWebapps = '%s/%s/webapps' % (self.jetty_base, jettyServiceName)
        self.copyFile('%s/identity.war' % self.distGluuFolder, jettyServiceWebapps)

    def install_saml(self):
        if self.installSaml:
            self.logIt("Install SAML Shibboleth IDP v3...")

            # Put latest SAML templates
            identityWar = 'identity.war'
            distIdentityPath = '%s/%s' % (self.distGluuFolder, identityWar)

            tmpIdentityDir = '%s/tmp_identity' % self.distGluuFolder

            self.logIt("Unpacking %s from %s..." % ('oxtrust-configuration.jar', identityWar))
            self.removeDirs(tmpIdentityDir)
            self.createDirs(tmpIdentityDir)

            identityConfFilePattern = 'WEB-INF/lib/oxtrust-configuration-%s.jar' % self.oxVersion

            self.run([self.cmd_jar,
                      'xf',
                      distIdentityPath], tmpIdentityDir)

            self.logIt("Unpacking %s..." % 'oxtrust-configuration.jar')
            self.run([self.cmd_jar,
                      'xf',
                      identityConfFilePattern], tmpIdentityDir)

            self.logIt("Preparing SAML templates...")
            self.removeDirs('%s/conf/shibboleth3' % self.gluuBaseFolder)
            self.createDirs('%s/conf/shibboleth3/idp' % self.gluuBaseFolder)
            self.createDirs('%s/conf/shibboleth3/sp' % self.gluuBaseFolder)

            # Put IDP templates to oxTrust conf folder
            jettyIdentityServiceName = 'identity'
            jettyIdentityServiceConf = '%s/%s/conf' % (self.jetty_base, jettyIdentityServiceName)
            self.run([self.cmd_mkdir, '-p', jettyIdentityServiceConf])

            self.copyTree('%s/shibboleth3' % tmpIdentityDir, '%s/shibboleth3' % jettyIdentityServiceConf)

            self.removeDirs(tmpIdentityDir)

            # unpack IDP3 JAR with static configs
            self.run([self.cmd_jar, 'xf', self.distGluuFolder + '/shibboleth-idp.jar'], '/opt')
            self.removeDirs('/opt/META-INF')

            # Process templates
            self.renderTemplateInOut(self.idp3_configuration_properties, self.staticIDP3FolderConf, self.idp3ConfFolder)
            self.renderTemplateInOut(self.idp3_configuration_ldap_properties, self.staticIDP3FolderConf, self.idp3ConfFolder)
            self.renderTemplateInOut(self.idp3_configuration_saml_nameid, self.staticIDP3FolderConf, self.idp3ConfFolder)
            self.renderTemplateInOut(self.idp3_configuration_services, self.staticIDP3FolderConf, self.idp3ConfFolder)
            self.renderTemplateInOut(self.idp3_configuration_password_authn, self.staticIDP3FolderConf + '/authn', self.idp3ConfFolder + '/authn')

            # load certificates to update metadata
            self.templateRenderingDict['idp3EncryptionCertificateText'] = self.load_certificate_text(self.certFolder + '/idp-encryption.crt')
            self.templateRenderingDict['idp3SigningCertificateText'] = self.load_certificate_text(self.certFolder + '/idp-signing.crt')
            # update IDP3 metadata
            self.renderTemplateInOut(self.idp3_metadata, self.staticIDP3FolderMetadata, self.idp3MetadataFolder)

            self.idpWarFullPath = '%s/idp.war' % self.distGluuFolder

            jettyIdpServiceName = 'idp'
            jettyIdpServiceWebapps = '%s/%s/webapps' % (self.jetty_base, jettyIdpServiceName)

            self.installJettyService(self.jetty_app_configuration[jettyIdpServiceName], True)
            self.copyFile('%s/idp.war' % self.distGluuFolder, jettyIdpServiceWebapps)

            # Prepare libraries needed to for command line IDP3 utilities
            self.install_saml_libraries()

            # generate new keystore with AES symmetric key
            # there is one throuble with Shibboleth IDP 3.x - it doesn't load keystore from /etc/certs. It accepts %{idp.home}/credentials/sealer.jks  %{idp.home}/credentials/sealer.kver path format only.
            cmd = [self.cmd_java,'-classpath', '"{}"'.format(os.path.join(self.idp3Folder,'webapp/WEB-INF/lib/*')),
                    'net.shibboleth.utilities.java.support.security.BasicKeystoreKeyStrategyTool',
                    '--storefile', os.path.join(self.idp3Folder,'credentials/sealer.jks'),
                    '--versionfile',  os.path.join(self.idp3Folder, 'credentials/sealer.kver'),
                    '--alias secret',
                    '--storepass', self.shibJksPass]
                
            self.run(' '.join(cmd), shell=True)

            # chown -R jetty:jetty /opt/shibboleth-idp
            # self.run([self.cmd_chown,'-R', 'jetty:jetty', self.idp3Folder], '/opt')
            self.run([self.cmd_chown, '-R', 'jetty:jetty', jettyIdpServiceWebapps], '/opt')

    def install_saml_libraries(self):
        # Unpack oxauth.war to get bcprov-jdk16.jar
        idpWar = 'idp.war'
        distIdpPath = '%s/idp.war' % self.distGluuFolder

        tmpIdpDir = '%s/tmp/tmp_idp' % self.distFolder

        self.logIt("Unpacking %s..." % idpWar)
        self.removeDirs(tmpIdpDir)
        self.createDirs(tmpIdpDir)

        self.run([self.cmd_jar,
                  'xf',
                  distIdpPath], tmpIdpDir)

        # Copy libraries into webapp
        idp3WebappLibFolder = "%s/WEB-INF/lib" % self.idp3WebappFolder
        self.createDirs(idp3WebappLibFolder)
        self.copyTree('%s/WEB-INF/lib' % tmpIdpDir, idp3WebappLibFolder)

        self.removeDirs(tmpIdpDir)

    def install_asimba(self):
        asimbaWar = 'asimba.war'
        distAsimbaPath = '%s/%s' % (self.distGluuFolder, asimbaWar)

        self.logIt("Configuring Asimba...")
        self.copyFile(self.asimba_configuration, self.asimba_configuration_xml)
        self.copyFile(self.asimba_selector_configuration, self.asimba_selector_configuration_xml)
        self.run([self.cmd_chmod, '-R', 'uga+x', self.asimba_conf_folder])
        self.run([self.cmd_chmod, '-R', 'ug+w', self.asimba_conf_folder])
        self.run([self.cmd_chmod, '-R', 'uga+r', self.asimba_configuration_xml, self.asimba_selector_configuration_xml])
        self.run([self.cmd_chown, '-R', 'jetty:jetty', self.asimba_conf_folder+'/metadata'])

        self.logIt("Copying asimba.war into jetty webapps folder...")
        jettyServiceName = 'asimba'
        self.installJettyService(self.jetty_app_configuration[jettyServiceName])

        jettyServiceWebapps = '%s/%s/webapps' % (self.jetty_base, jettyServiceName)
        self.copyFile(distAsimbaPath, jettyServiceWebapps)

    def install_oxauth_rp(self):
        oxAuthRPWar = 'oxauth-rp.war'
        distOxAuthRpPath = '%s/%s' % (self.distGluuFolder, oxAuthRPWar)

        self.logIt("Copying oxauth-rp.war into jetty webapps folder...")

        jettyServiceName = 'oxauth-rp'
        self.installJettyService(self.jetty_app_configuration[jettyServiceName])

        jettyServiceWebapps = '%s/%s/webapps' % (self.jetty_base, jettyServiceName)
        self.copyFile('%s/oxauth-rp.war' % self.distGluuFolder, jettyServiceWebapps)

    def install_passport(self):
        self.logIt("Installing Passport...")

        self.logIt("Preparing passport service base folders")
        self.run([self.cmd_mkdir, '-p', self.gluu_passport_base])

        # Extract package
        passportArchive = 'passport.tgz'
        try:
            self.logIt("Extracting %s into %s" % (passportArchive, self.gluu_passport_base))
            self.run(['tar', '--strip', '1', '-xzf', '%s/%s' % (self.distGluuFolder, passportArchive), '-C', self.gluu_passport_base, '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
        except:
            self.logIt("Error encountered while extracting archive %s" % passportArchive)
            self.logIt(traceback.format_exc(), True)
        
        passport_modules_archive = os.path.join(self.distGluuFolder, 'passport-%s-node_modules.tar.gz' % self.githubBranchName)
        modules_target_dir = os.path.join(self.gluu_passport_base, 'node_modules')
        self.run([self.cmd_mkdir, '-p', modules_target_dir])

        if os.path.exists(passport_modules_archive):
            self.logIt("Extracting passport node modules")
            self.run(['tar', '--strip', '1', '-xzf', passport_modules_archive, '-C', modules_target_dir, '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
        else:
            # Install dependencies
            try: 
                self.logIt("Running npm install in %s" % self.gluu_passport_base)

                nodeEnv = os.environ.copy()
                nodeEnv['PATH'] = '%s/bin:' % self.node_home + nodeEnv['PATH']

                self.run(['npm', 'install', '-P'], self.gluu_passport_base, nodeEnv, True)
            except:
                self.logIt("Error encountered running npm install in %s" % self.gluu_passport_base)
                self.logIt(traceback.format_exc(), True)

        # Create logs folder
        self.run([self.cmd_mkdir, '-p', '%s/server/logs' % self.gluu_passport_base])
        
        #create empty log file
        log_file = os.path.join(self.gluu_passport_base, 'server/logs/start.log')
        open(log_file,'w')

        self.run([self.cmd_chown, '-R', 'node:node', self.gluu_passport_base])

        self.logIt("Preparing Passport OpenID RP certificate...")
        passport_rp_client_jwks_json = json.loads(''.join(self.passport_rp_client_jwks))
        for jwks_key in passport_rp_client_jwks_json["keys"]:
            if jwks_key["alg"]  == self.passport_rp_client_cert_alg:
                self.passport_rp_client_cert_alias = jwks_key["kid"]
                break

        self.export_openid_key(self.passport_rp_client_jks_fn, self.passport_rp_client_jks_pass, self.passport_rp_client_cert_alias, self.passport_rp_client_cert_fn)
        self.renderTemplateInOut(self.passport_config, self.templateFolder, self.configFolder)


        # Install passport system service script
        self.installNodeService('passport')

        # enable service at startup
        self.enable_service_at_start('passport')


    def install_gluu_components(self):
        if self.installLdap:
            self.pbar.progress("Installing Gluu components: LDAP", False)
            self.install_ldap_server()

        if self.installHttpd:
            self.pbar.progress("Installing Gluu components: HTTPD", False)
            self.configure_httpd()

        if self.installOxAuth:
            self.pbar.progress("Installing Gluu components: OxAuth", False)
            self.install_oxauth()

        if self.installOxTrust:
            self.pbar.progress("Installing Gluu components: oxTrust", False)
            self.install_oxtrust()

        if self.installSaml:
            self.pbar.progress("Installing Gluu components: saml", False)
            self.install_saml()

        if self.installAsimba:
            self.pbar.progress("Installing Gluu components: Asimba", False)
            self.install_asimba()

        if self.installOxAuthRP:
            self.pbar.progress("Installing Gluu components: OxAuthRP", False)
            self.install_oxauth_rp()

        if self.installPassport:
            self.pbar.progress("Installing Gluu components: Passport", False)
            self.install_passport()

    def isIP(self, address):
        try:
            socket.inet_aton(address)
            return True
        except socket.error:
            return False

    def ldap_encode(self, password):
        salt = os.urandom(4)
        sha = hashlib.sha1(password)
        sha.update(salt)
        b64encoded = '{0}{1}'.format(sha.digest(), salt).encode('base64').strip()
        encrypted_password = '{{SSHA}}{0}'.format(b64encoded)
        return encrypted_password

    def createUser(self, userName, homeDir):
        try:
            useradd = '/usr/sbin/useradd'
            self.run([useradd, '--system', '--create-home', '--user-group', '--shell', '/bin/bash', '--home-dir', homeDir, userName])
            self.logOSChanges("User %s with homedir %s was created" % (userName, homeDir))
        except:
            self.logIt("Error adding user", True)
            self.logIt(traceback.format_exc(), True)

    def createGroup(self, groupName):
        try:
            groupadd = '/usr/sbin/groupadd'
            self.run([groupadd, groupName])
            self.logOSChanges("Group %s was created" % (groupName))
        except:
            self.logIt("Error adding group", True)
            self.logIt(traceback.format_exc(), True)

    def addUserToGroup(self, groupName, userName):
        try:
            usermod = '/usr/sbin/usermod'
            self.run([usermod, '-a', '-G', groupName, userName])
            self.logOSChanges("User %s was added to group %s" % (userName,groupName))
        except:
            self.logIt("Error adding group", True)
            self.logIt(traceback.format_exc(), True)

    def createUsers(self):
        self.createUser('ldap', self.ldap_user_home)
        self.createUser('jetty', self.jetty_user_home)
        self.createUser('node', self.node_user_home)

        self.createGroup('gluu')

        self.addUserToGroup('gluu', 'ldap')
        self.addUserToGroup('gluu', 'jetty')
        self.addUserToGroup('gluu', 'node')

        self.addUserToGroup('adm', 'ldap')

    def makeFolders(self):
        try:
            # Allow write to /tmp
            self.run([self.cmd_chmod, 'ga+w', "/tmp"])

            # Create these folder on all instances
            self.run([self.cmd_mkdir, '-p', self.gluuOptFolder])
            self.run([self.cmd_mkdir, '-p', self.gluuOptBinFolder])
            self.run([self.cmd_mkdir, '-p', self.gluuOptSystemFolder])
            self.run([self.cmd_mkdir, '-p', self.gluuOptPythonFolder])
            self.run([self.cmd_mkdir, '-p', self.configFolder])
            self.run([self.cmd_mkdir, '-p', self.certFolder])
            self.run([self.cmd_mkdir, '-p', self.outputFolder])
            self.run([self.cmd_mkdir, '-p', self.jetty_user_home_lib])

            # Create Fido2 folders
            if self.installOxAuth:
                self.run([self.cmd_mkdir, '-p', self.fido2ConfigFolder])
                self.run([self.cmd_mkdir, '-p', '%s/%s' % (self.fido2ConfigFolder, '/authenticator_cert')])
                self.run([self.cmd_mkdir, '-p', '%s/%s' % (self.fido2ConfigFolder, '/mds/cert')])
                self.run([self.cmd_mkdir, '-p', '%s/%s' % (self.fido2ConfigFolder, '/mds/toc')])
                self.run([self.cmd_mkdir, '-p', '%s/%s' % (self.fido2ConfigFolder, '/server_metadata')])

            if not os.path.exists(self.osDefault):
                self.run([self.cmd_mkdir, '-p', self.osDefault])

            if self.installOxTrust | self.installOxAuth:
                self.run([self.cmd_mkdir, '-m', '775', '-p', self.oxPhotosFolder])
                self.run([self.cmd_mkdir, '-m', '775', '-p', self.oxTrustRemovedFolder])
                self.run([self.cmd_mkdir, '-m', '775', '-p', self.oxTrustCacheRefreshFolder])

                self.run([self.cmd_chown, '-R', 'root:gluu', self.oxPhotosFolder])
                self.run([self.cmd_chown, '-R', 'root:gluu', self.oxTrustRemovedFolder])
                self.run([self.cmd_chown, '-R', 'root:gluu', self.oxTrustCacheRefreshFolder])

            if self.installSaml:
                self.run([self.cmd_mkdir, '-p', self.idp3Folder])
                self.run([self.cmd_mkdir, '-p', self.idp3MetadataFolder])
                self.run([self.cmd_mkdir, '-p', self.idp3MetadataCredentialsFolder])
                self.run([self.cmd_mkdir, '-p', self.idp3LogsFolder])
                self.run([self.cmd_mkdir, '-p', self.idp3LibFolder])
                self.run([self.cmd_mkdir, '-p', self.idp3ConfFolder])
                self.run([self.cmd_mkdir, '-p', self.idp3ConfAuthnFolder])
                self.run([self.cmd_mkdir, '-p', self.idp3CredentialsFolder])
                self.run([self.cmd_mkdir, '-p', self.idp3WebappFolder])
                # self.run([self.cmd_mkdir, '-p', self.idp3WarFolder])
                self.run([self.cmd_chown, '-R', 'jetty:jetty', self.idp3Folder])

            if self.installLdap and self.ldap_type == 'openldap':
                self.run([self.cmd_mkdir, '-p', '/opt/gluu/data/main_db'])
                self.run([self.cmd_mkdir, '-p', '/opt/gluu/data/site_db'])
                self.run([self.cmd_mkdir, '-p', '/opt/gluu/data/metric_db'])

            if self.installAsimba:
                self.run([self.cmd_mkdir, '-p', self.asimba_conf_folder])
                self.run([self.cmd_mkdir, '-p', self.asimba_conf_folder+'/metadata'])
                self.run([self.cmd_mkdir, '-p', self.asimba_conf_folder+'/metadata/idp'])
                self.run([self.cmd_mkdir, '-p', self.asimba_conf_folder+'/metadata/sp'])
                self.run([self.cmd_chown, '-R', 'jetty:jetty', self.asimba_conf_folder+'/metadata'])

        except:
            self.logIt("Error making folders", True)
            self.logIt(traceback.format_exc(), True)

    def customiseSystem(self):
        if self.os_initdaemon == 'init':
            system_profile_update = self.system_profile_update_init
        else:
            system_profile_update = self.system_profile_update_systemd

        # Render customized part
        self.renderTemplate(system_profile_update)
        renderedSystemProfile = self.readFile(system_profile_update)

        # Read source file
        currentSystemProfile = self.readFile(self.sysemProfile)

        # Write merged file
        self.backupFile(self.sysemProfile)
        resultSystemProfile = "\n".join((currentSystemProfile, renderedSystemProfile))
        self.writeFile(self.sysemProfile, resultSystemProfile)

        # Fix new file permissions
        self.run([self.cmd_chmod, '644', self.sysemProfile])

    def configureSystem(self):
        self.customiseSystem()
        self.createUsers()
        self.makeFolders()

    def make_salt(self):
        try:
            f = open("%s/salt" % self.configFolder, 'w')
            f.write('encodeSalt = %s' % self.encode_salt)
            f.close()
        except:
            self.logIt("Error writing salt", True)
            self.logIt(traceback.format_exc(), True)
            sys.exit()


    def make_oxauth_salt(self):
        self.pairwiseCalculationKey = self.genRandomString(random.randint(20,30))
        self.pairwiseCalculationSalt = self.genRandomString(random.randint(20,30))

    def promptForProperties(self):

        promptForMITLicense = self.getPrompt("Do you acknowledge that use of the Gluu Server is under the MIT license?","N|y")[0].lower()
        if promptForMITLicense != 'y':
            sys.exit(0)
        
        # IP address needed only for Apache2 and hosts file update
        if self.installHttpd:
            self.ip = self.get_ip()

        detectedHostname = None
        try:
            detectedHostname = socket.gethostbyaddr(self.ip)[0]
        except:
            try:
                detectedHostname = os.popen("/bin/hostname").read().strip()
            except:
                self.logIt("No detected hostname", True)
                self.logIt(traceback.format_exc(), True)

        if detectedHostname == 'localhost':
            detectedHostname = None

        while True:
            if detectedHostname:
                self.hostname = self.getPrompt("Enter hostname", detectedHostname)
            else:
                self.hostname = self.getPrompt("Enter hostname")

            if self.hostname != 'localhost':
                break
            else:
                print "Hostname can't be \033[;1mlocalhost\033[0;0m"

        # Get city and state|province code
        self.city = self.getPrompt("Enter your city or locality")
        self.state = self.getPrompt("Enter your state or province two letter code")

        # Get the Country Code
        long_enough = False
        while not long_enough:
            countryCode = self.getPrompt("Enter two letter Country Code")
            if len(countryCode) != 2:
                print "Country code must be two characters"
            else:
                self.countryCode = countryCode
                long_enough = True

        self.orgName = self.getPrompt("Enter Organization Name")
        self.admin_email = self.getPrompt('Enter email address for support at your organization')
        self.application_max_ram = self.getPrompt("Enter maximum RAM for applications in MB", '3072')
        randomPW = self.getPW()
        self.ldapPass = self.getPrompt("Optional: enter password for oxTrust and LDAP superuser", randomPW)

        if setupOptions['allowPreReleasedApplications']:
            while True:
                java_type = self.getPrompt("Select Java type: 1.Jre-1.8   2.OpenJDK-11", '1')
                if not java_type:
                    java_type = 1
                    break
                if java_type in '12':
                    break
                else:
                    print "Please enter 1 or 2"

            if java_type == '1':
                self.java_type = 'jre'
            else:
                self.java_type = 'jdk'
                self.defaultTrustStoreFN = '%s/lib/security/cacerts' % self.jre_home

        promptForOxAuth = self.getPrompt("Install oxAuth OAuth2 Authorization Server?", "Yes")[0].lower()
        if promptForOxAuth == 'y':
            self.installOxAuth = True
        else:
            self.installOxAuth = False

        promptForOxTrust = self.getPrompt("Install oxTrust Admin UI?", "Yes")[0].lower()
        if promptForOxTrust == 'y':
            self.installOxTrust = True
        else:
            self.installOxTrust = False

        promptForLDAP = self.getPrompt("Install LDAP Server?", "Yes")[0].lower()
        if promptForLDAP == 'y':
            
            backend_types = []

            if glob.glob(self.distFolder+'/app/opendj-server*.zip'):
                backend_types.append(('Gluu OpenDj','opendj'))
            
            if self.os_type in ('ubuntu', 'debian'):
                suffix = 'deb'

            elif self.os_type in ('centos', 'red', 'fedora'):
                suffix = 'rpm'

            if self.allowDeprecatedApplications and glob.glob(self.distFolder+'/symas/symas-openldap*.'+suffix):
                backend_types.append(('OpenLDAP Gluu Edition','openldap'))
            

            if self.allowPreReleasedApplications and glob.glob(self.distFolder+'/app/opendj-server-*4*.zip'):
                backend_types.append(('Wren:DS','wrends'))

            self.installLdap = True
            option = None
            
            if len(backend_types) == 1:
                self.ldap_type = backend_types[0][1] 

            else:
                prompt_text = 'Install '
                options = []
                for i, backend in enumerate(backend_types):
                    prompt_text += '({0}) {1} '.format(i+1, backend[0])
                    options.append(str(i+1))

                prompt_text += '[{0}]'.format('|'.join(options))
                option=None

                while not option in options:
                    option=self.getPrompt(prompt_text, options[0])
                    if not option in options:
                        print "You did not enter the correct option. Enter one of this options: {0}".format(', '.join(options))

                self.ldap_type = backend_types[int(option)-1][1]

                if self.ldap_type == 'wrends':
                    self.ldap_type = 'opendj'
                    self.opendj_type = 'wrends'

        else:
            self.installLdap = False

        promptForHTTPD = self.getPrompt("Install Apache HTTPD Server", "Yes")[0].lower()
        if promptForHTTPD == 'y':
            self.installHttpd = True
        else:
            self.installHttpd = False

        promptForShibIDP = self.getPrompt("Install Shibboleth SAML IDP?", "No")[0].lower()
        if promptForShibIDP == 'y':
            self.shibboleth_version = 'v3'
            self.installSaml = True
        else:
            self.installSaml = False

        promptForOxAuthRP = self.getPrompt("Install oxAuth RP?", "No")[0].lower()
        if promptForOxAuthRP == 'y':
            self.installOxAuthRP = True
        else:
            self.installOxAuthRP = False

        promptForPassport = self.getPrompt("Install Passport?", "No")[0].lower()
        if promptForPassport == 'y':
            self.installPassport = True
        else:
            self.installPassport = False

        if self.allowDeprecatedApplications:
            promptForAsimba = self.getPrompt("Install Asimba SAML Proxy?", "No")[0].lower()
            if promptForAsimba == 'y':
                self.installAsimba = True
            else:
                self.installAsimba = False

    def get_filepaths(self, directory):
        file_paths = []

        for root, directories, files in os.walk(directory):
            for filename in files:
                # filepath = os.path.join(root, filename)
                file_paths.append(filename)

        return file_paths

    def fomatWithDict(self, text, dictionary):
        text = re.sub(r"%([^\(])", r"%%\1", text)
        text = re.sub(r"%$", r"%%", text)  # There was a % at the end?

        return text % dictionary

    def renderTemplateInOut(self, filePath, templateFolder, outputFolder):
        self.logIt("Rendering template %s" % filePath)
        fn = os.path.split(filePath)[-1]
        f = open(os.path.join(templateFolder, fn))
        template_text = f.read()
        f.close()

        # Create output folder if needed
        if not os.path.exists(outputFolder):
            os.makedirs(outputFolder)
        self.backupFile(fn)
        newFn = open(os.path.join(outputFolder, fn), 'w+')
        newFn.write(self.fomatWithDict(template_text, self.merge_dicts(self.__dict__, self.templateRenderingDict)))
        newFn.close()

    def renderTemplate(self, filePath):
        self.renderTemplateInOut(filePath, self.templateFolder, self.outputFolder)

    def render_templates(self):
        self.logIt("Rendering templates")
        for fullPath in self.ce_templates.keys():
            try:
                self.renderTemplate(fullPath)
            except:
                self.logIt("Error writing template %s" % fullPath, True)
                self.logIt(traceback.format_exc(), True)

    def render_custom_templates(self, fullPath):
        output_dir = fullPath + '.output'

        self.logIt("Rendering custom templates")
        self.logIt("Rendering custom templates from %s to %s" % (fullPath, output_dir))

        try:
            self.run([self.cmd_mkdir, '-p', output_dir])
        except:
            self.logIt("Error creating output directory %s" % output_dir, True)
            self.logIt(traceback.format_exc(), True)

        try:
            for filename in self.get_filepaths(fullPath):
                self.renderTemplateInOut(filename, fullPath, output_dir)
        except:
            self.logIt("Error writing template %s" % fullPath, True)
            self.logIt(traceback.format_exc(), True)

    def render_configuration_template(self):
        self.logIt("Rendering configuration templates")

        fullPath = self.ldif_configuration
        try:
            self.renderTemplate(fullPath)
        except:
            self.logIt("Error writing template %s" % fullPath, True)
            self.logIt(traceback.format_exc(), True)

    def render_templates_folder(self, templatesFolder):
        self.logIt("Rendering templates folder: %s" % templatesFolder)

        for templateBase, templateDirectories, templateFiles in os.walk(templatesFolder):
            for templateFile in templateFiles:
                fullPath = '%s/%s' % (templateBase, templateFile)
                try:
                    self.logIt("Rendering test template %s" % fullPath)
                    # Remove ./template/ and everything left of it from fullPath
                    fn = re.match(r'(^.+/templates/)(.*$)', fullPath).groups()[1]
                    f = open(os.path.join(self.templateFolder, fn))
                    template_text = f.read()
                    f.close()

                    fullOutputFile = os.path.join(self.outputFolder, fn)
                    # Create full path to the output file
                    fullOutputDir = os.path.dirname(fullOutputFile)
                    if not os.path.exists(fullOutputDir):
                        os.makedirs(fullOutputDir)

                    self.backupFile(fullOutputFile)
                    newFn = open(fullOutputFile, 'w+')
                    newFn.write(template_text % self.merge_dicts(self.__dict__, self.templateRenderingDict))
                    newFn.close()
                except:
                    self.logIt("Error writing template %s" % fullPath, True)
                    self.logIt(traceback.format_exc(), True)

    def render_test_templates(self):
        self.logIt("Rendering test templates")

        testTepmplatesFolder = '%s/test/' % self.templateFolder
        self.render_templates_folder(testTepmplatesFolder)

    def render_node_templates(self):
        self.logIt("Rendering node templates")

        nodeTepmplatesFolder = '%s/node/' % self.templateFolder
        self.render_templates_folder(nodeTepmplatesFolder)

    def prepare_base64_extension_scripts(self):
        try:
            if not os.path.exists(self.extensionFolder):
                return None

            for extensionType in os.listdir(self.extensionFolder):
                extensionTypeFolder = os.path.join(self.extensionFolder, extensionType)
                if not os.path.isdir(extensionTypeFolder):
                    continue

                for scriptFile in os.listdir(extensionTypeFolder):
                    scriptFilePath = os.path.join(extensionTypeFolder, scriptFile)
                    base64ScriptFile = self.generate_base64_file(scriptFilePath, 1)

                    # Prepare key for dictionary
                    extensionScriptName = '%s_%s' % (extensionType, os.path.splitext(scriptFile)[0])
                    extensionScriptName = extensionScriptName.decode('utf-8').lower()

                    self.templateRenderingDict[extensionScriptName] = base64ScriptFile
                    self.logIt("Loaded script %s with type %s into %s" % (scriptFile, extensionType, extensionScriptName))

        except:
            self.logIt("Error loading scripts from %s" % self.extensionFolder, True)
            self.logIt(traceback.format_exc(), True)

    def reindent(self, text, num_spaces):
        text = string.split(text, '\n')
        text = [(num_spaces * ' ') + string.lstrip(line) for line in text]
        text = string.join(text, '\n')

        return text

    def generate_base64_file(self, fn, num_spaces):
        self.logIt('Loading file %s' % fn)
        plain_file_b64encoded_text = None
        try:
            plain_file = open(fn)
            plain_file_text = plain_file.read()
            plain_file_b64encoded_text = base64.b64encode(plain_file_text).strip()
            plain_file.close()
        except:
            self.logIt("Error loading file", True)
            self.logIt(traceback.format_exc(), True)

        if num_spaces > 0:
            plain_file_b64encoded_text = self.reindent(plain_file_b64encoded_text, num_spaces)

        return plain_file_b64encoded_text

    def generate_base64_ldap_file(self, fn):
        return self.generate_base64_file(fn, 1)

    def generate_base64_configuration(self):
        self.templateRenderingDict['oxauth_config_base64'] = self.generate_base64_ldap_file(self.oxauth_config_json)
        self.templateRenderingDict['oxauth_static_conf_base64'] = self.generate_base64_ldap_file(self.oxauth_static_conf_json)
        self.templateRenderingDict['oxauth_error_base64'] = self.generate_base64_ldap_file(self.oxauth_error_json)
        self.templateRenderingDict['oxauth_openid_key_base64'] = self.generate_base64_ldap_file(self.oxauth_openid_jwks_fn)

        self.templateRenderingDict['oxtrust_config_base64'] = self.generate_base64_ldap_file(self.oxtrust_config_json);
        self.templateRenderingDict['oxtrust_cache_refresh_base64'] = self.generate_base64_ldap_file(self.oxtrust_cache_refresh_json)
        self.templateRenderingDict['oxtrust_import_person_base64'] = self.generate_base64_ldap_file(self.oxtrust_import_person_json)

        self.templateRenderingDict['oxidp_config_base64'] = self.generate_base64_ldap_file(self.oxidp_config_json)
        self.templateRenderingDict['oxasimba_config_base64'] = self.generate_base64_ldap_file(self.oxasimba_config_json)

    def get_clean_args(self, args):
        argsc = args[:]

        for a in ('-R', '-h', '-p'):
            if a in argsc:
                argsc.remove(a)

        if '-m' in argsc:
            m = argsc.index('-m')
            argsc.pop(m)
            argsc.pop(m)
            
        return argsc

    # args = command + args, i.e. ['ls', '-ltr']
    def run(self, args, cwd=None, env=None, useWait=False, shell=False):
        output = ''
        log_arg = ' '.join(args) if type(args) is list else args
        self.logIt('Running: %s' % log_arg)
        
        if args[0] == self.cmd_chown:
            argsc = self.get_clean_args(args)
            if not argsc[2].startswith('/opt'):
                self.logOSChanges('Making owner of %s to %s' % (', '.join(argsc[2:]), argsc[1]))
        elif args[0] == self.cmd_chmod:
            argsc = self.get_clean_args(args)
            if not argsc[2].startswith('/opt'):
                self.logOSChanges('Setting permission of %s to %s' % (', '.join(argsc[2:]), argsc[1]))
        elif args[0] == self.cmd_chgrp:
            argsc = self.get_clean_args(args)
            if not argsc[2].startswith('/opt'):
                self.logOSChanges('Making group of %s to %s' % (', '.join(argsc[2:]), argsc[1]))
        elif args[0] == self.cmd_mkdir:
            argsc = self.get_clean_args(args)
            if not (argsc[1].startswith('/opt') or argsc[1].startswith('.')):
                self.logOSChanges('Creating directory %s' % (', '.join(argsc[1:])))

        try:
            p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env, shell=shell)
            if useWait:
                code = p.wait()
                self.logIt('Run: %s with result code: %d' % (' '.join(args), code) )
            else:
                output, err = p.communicate()
                if output:
                    self.logIt(output)
                if err:
                    self.logIt(err, True)
        except:
            self.logIt("Error running command : %s" % " ".join(args), True)
            self.logIt(traceback.format_exc(), True)

    def save_properties(self):
        self.logIt('Saving properties to %s' % self.savedProperties)

        def getString(value):
            if isinstance(value, str):
                return value.strip()
            elif isinstance(value, bool):
                return str(value)
            else:
                return ""
        try:
            p = Properties.Properties()
            keys = self.__dict__.keys()
            keys.sort()
            for key in keys:
                value = getString(self.__dict__[key])
                if value != '':
                    p[key] = value
            p.store(open(self.savedProperties, 'w'))
        except:
            self.logIt("Error saving properties", True)
            self.logIt(traceback.format_exc(), True)

    def createLdapPw(self):
        try:
            f = open(self.ldapPassFn, 'w')
            f.write(self.ldapPass)
            f.close()
            self.run([self.cmd_chown, 'ldap:ldap', self.ldapPassFn])
        except:
            self.logIt("Error writing temporary LDAP password.")
            self.logIt(traceback.format_exc(), True)

    def deleteLdapPw(self):
        try:
            os.remove(self.ldapPassFn)
        except:
            self.logIt("Error deleting ldap pw. Make sure %s is deleted" % self.ldapPassFn)
            self.logIt(traceback.format_exc(), True)

    def install_opendj(self):
        self.logIt("Running OpenDJ Setup")
        # Copy opendj-setup.properties so user ldap can find it in /opt/opendj
        setupPropsFN = os.path.join(self.ldapBaseFolder, 'opendj-setup.properties')
        shutil.copy("%s/opendj-setup.properties" % self.outputFolder, setupPropsFN)
        self.set_ownership()
        try:
            ldapSetupCommand = '%s/setup' % self.ldapBaseFolder
            setupCmd = "cd /opt/opendj ; export OPENDJ_JAVA_HOME=" + self.jre_home + " ; " + " ".join([ldapSetupCommand,
                                                                                                       '--no-prompt',
                                                                                                       '--cli',
                                                                                                       '--propertiesFilePath',
                                                                                                       setupPropsFN,
                                                                                                       '--acceptLicense'
                                                                                                       ])
            self.run(['/bin/su',
                      'ldap',
                      '-c',
                      setupCmd])
        except:
            self.logIt("Error running LDAP setup script", True)
            self.logIt(traceback.format_exc(), True)


        if self.opendj_type == 'opendj':

            try:
                dsjavaCmd = "cd /opt/opendj/bin ; %s" % self.ldapDsJavaPropCommand
                self.run(['/bin/su',
                          'ldap',
                          '-c',
                          dsjavaCmd
                          ])
            except:
                self.logIt("Error running dsjavaproperties", True)
                self.logIt(traceback.format_exc(), True)

        try:
            stopDsJavaPropCommand = "%s/bin/stop-ds" % self.ldapBaseFolder
            dsjavaCmd = "cd /opt/opendj/bin ; %s" % stopDsJavaPropCommand
            self.run(['/bin/su',
                      'ldap',
                      '-c',
                      dsjavaCmd
                      ])
        except:
            self.logIt("Error running stop-ds", True)
            self.logIt(traceback.format_exc(), True)

    def post_install_opendj(self):
        try:
            os.remove(os.path.join(self.ldapBaseFolder, 'opendj-setup.properties'))
        except:
            self.logIt("Error deleting OpenDJ properties. Make sure %s/opendj-setup.properties is deleted" % self.ldapBaseFolder)
            self.logIt(traceback.format_exc(), True)

    def configure_opendj(self):
        self.logIt("Configuring OpenDJ")

        opendj_prop_name = 'global-aci:\'(targetattr!="userPassword||authPassword||debugsearchindex||changes||changeNumber||changeType||changeTime||targetDN||newRDN||newSuperior||deleteOldRDN")(version 3.0; acl "Anonymous read access"; allow (read,search,compare) userdn="ldap:///anyone";)\''
        config_changes = [
                          ['set-backend-prop', '--backend-name', 'userRoot', '--set', 'db-cache-percent:70'],  
                          ['set-global-configuration-prop', '--set', 'single-structural-objectclass-behavior:accept'],
                          ['set-password-policy-prop', '--policy-name', '"Default Password Policy"', '--set', 'allow-pre-encoded-passwords:true'],
                          ['set-log-publisher-prop', '--publisher-name', '"File-Based Audit Logger"', '--set', 'enabled:true'],
                          ['create-backend', '--backend-name', 'site', '--set', 'base-dn:o=site', '--type %s' % self.ldap_backend_type, '--set', 'enabled:true', '--set', 'db-cache-percent:20'],
                          ['create-backend', '--backend-name', 'metric', '--set', 'base-dn:o=metric', '--type %s' % self.ldap_backend_type, '--set', 'enabled:true', '--set', 'db-cache-percent:10'],
                          ['set-connection-handler-prop', '--handler-name', '"LDAP Connection Handler"', '--set', 'enabled:false'],
                          ['set-connection-handler-prop', '--handler-name', '"JMX Connection Handler"', '--set', 'enabled:false'],
                          ['set-access-control-handler-prop', '--remove', '%s' % opendj_prop_name],
                          ['set-global-configuration-prop', '--set', 'reject-unauthenticated-requests:true'],
                          ['set-password-policy-prop', '--policy-name', '"Default Password Policy"', '--set', 'default-password-storage-scheme:"Salted SHA-512"'],
                          ['set-global-configuration-prop', '--set', 'reject-unauthenticated-requests:true'],
                          ['create-plugin', '--plugin-name', '"Unique mail address"', '--type', 'unique-attribute', '--set enabled:true',  '--set', 'base-dn:o=gluu', '--set', 'type:mail'],
                          ['create-plugin', '--plugin-name', '"Unique uid entry"', '--type', 'unique-attribute', '--set enabled:true',  '--set', 'base-dn:o=gluu', '--set', 'type:uid'],
                          ]

        if self.opendj_type == 'opendj':
            config_changes.insert(2, ['set-attribute-syntax-prop', '--syntax-name', '"Directory String"',   '--set', 'allow-zero-length-values:true'])

        
        if not self.listenAllInterfaces:
            config_changes.append(['set-connection-handler-prop', '--handler-name', '"LDAPS Connection Handler"', '--set', 'enabled:true', '--set', 'listen-address:127.0.0.1'])
            config_changes.append(['set-administration-connector-prop', '--set', 'listen-address:127.0.0.1'])

        for changes in config_changes:
            dsconfigCmd = " ".join(['cd %s/bin ; ' % self.ldapBaseFolder,
                                    self.ldapDsconfigCommand,
                                    '--trustAll',
                                    '--no-prompt',
                                    '--hostname',
                                    self.ldap_hostname,
                                    '--port',
                                    self.ldap_admin_port,
                                    '--bindDN',
                                    '"%s"' % self.ldap_binddn,
                                    '--bindPasswordFile',
                                    self.ldapPassFn] + changes)
            self.run(['/bin/su',
                      'ldap',
                      '-c',
                      dsconfigCmd])

    def export_opendj_public_cert(self):
        # Load password to acces OpenDJ truststore
        self.logIt("Reading OpenDJ truststore")

        openDjPinFn = '%s/config/keystore.pin' % self.ldapBaseFolder
        openDjTruststoreFn = '%s/config/truststore' % self.ldapBaseFolder

        openDjPin = None
        try:
            f = open(openDjPinFn)
            openDjPin = f.read().splitlines()[0]
            f.close()
        except:
            self.logIt("Error reding OpenDJ truststore", True)
            self.logIt(traceback.format_exc(), True)

        # Export public OpenDJ certificate
        self.logIt("Exporting OpenDJ certificate")
        self.run([self.cmd_keytool,
                  '-exportcert',
                  '-keystore',
                  openDjTruststoreFn,
                  '-storepass',
                  openDjPin,
                  '-file',
                  self.opendj_cert_fn,
                  '-alias',
                  'server-cert',
                  '-rfc'])

        # Convert OpenDJ certificate to PKCS12
        self.logIt("Converting OpenDJ truststore")
        self.run([self.cmd_keytool,
                  '-importkeystore',
                  '-srckeystore',
                  openDjTruststoreFn,
                  '-srcstoretype',
                  'jks',
                  '-srcstorepass',
                  openDjPin,
                  '-destkeystore',
                  self.opendj_p12_fn,
                  '-deststoretype',
                  'pkcs12',
                  '-deststorepass',
                  self.opendj_p12_pass,
                  '-srcalias',
                  'server-cert'])

        # Import OpenDJ certificate into java truststore
        self.logIt("Import OpenDJ certificate")

        self.run([self.cmd_keytool, "-import", "-trustcacerts", "-alias", "%s_opendj" % self.hostname, \
                  "-file", self.opendj_cert_fn, "-keystore", self.defaultTrustStoreFN, \
                  "-storepass", "changeit", "-noprompt"])

    def import_ldif_template_opendj(self, ldif):
        self.logIt("Importing LDIF file '%s' into OpenDJ" % ldif)
        realInstallDir = os.path.realpath(self.outputFolder)

        ldif_file_fullpath = os.path.realpath(ldif)

        importParams = ['cd %s/bin ; ' % self.ldapBaseFolder,
                              self.loadLdifCommand,
                              '--hostname',
                              self.ldap_hostname,
                              '--port',
                              self.ldap_admin_port,
                              '--bindDN',
                              '"%s"' % self.ldap_binddn,
                              '-j',
                              self.ldapPassFn,
                              '--trustAll']
        importParams.append('--useSSL')

        if self.opendj_type == 'opendj':
            importParams.append('--defaultAdd')
        
        importParams.append('--continueOnError')
        importParams.append('--filename')
        importParams.append(ldif_file_fullpath)

        importCmd = " ".join(importParams)
        
        # Check if there is no .pw file
        createPwFile = not os.path.exists(self.ldapPassFn)
        if createPwFile:
            self.createLdapPw()
        
        self.run(['/bin/su',
                  'ldap',
                  '-c',
                  '%s' % importCmd])

        if createPwFile:
            self.deleteLdapPw()

    def import_ldif_opendj(self):
        self.logIt("Importing userRoot LDIF data")
        realInstallDir = os.path.realpath(self.outputFolder)
        for ldif_file_fn in self.ldif_files:
            ldif_file_fullpath = os.path.realpath(ldif_file_fn)

            importParams = ['cd %s/bin ; ' % self.ldapBaseFolder,
                                  self.loadLdifCommand,
                                  '--hostname',
                                  self.ldap_hostname,
                                  '--port',
                                  self.ldap_admin_port,
                                  '--bindDN',
                                  '"%s"' % self.ldap_binddn,
                                  '-j',
                                  self.ldapPassFn,
                                  '--trustAll']
            importParams.append('--useSSL')
            
            if self.opendj_type == 'opendj':
                importParams.append('--defaultAdd')
            
            importParams.append('--continueOnError')
            importParams.append('--filename')
            importParams.append(ldif_file_fullpath)

            importCmd = " ".join(importParams)
            self.run(['/bin/su',
                      'ldap',
                      '-c',
                      '%s' % importCmd])

    def index_opendj_backend(self, backend):
        index_command = 'create-backend-index'
            
        try:
            self.logIt("Running LDAP index creation commands for " + backend + " backend")
            # This json file contains a mapping of the required indexes.
            # [ { "attribute": "inum", "type": "string", "index": ["equality"] }, ...}
            index_json = self.load_json(self.openDjIndexJson)
            if index_json:
                for attrDict in index_json:
                    attr_name = attrDict['attribute']
                    index_types = attrDict['index']
                    for index_type in index_types:
                        backend_names = attrDict['backend']
                        for backend_name in backend_names:
                            if (backend_name == backend):
                                self.logIt("Creating %s index for attribute %s" % (index_type, attr_name))
                                indexCmd = " ".join(['cd %s/bin ; ' % self.ldapBaseFolder,
                                                     self.ldapDsconfigCommand,
                                                     index_command,
                                                     '--backend-name',
                                                     backend,
                                                     '--type',
                                                     'generic',
                                                     '--index-name',
                                                     attr_name,
                                                     '--set',
                                                     'index-type:%s' % index_type,
                                                     '--set',
                                                     'index-entry-limit:4000',
                                                     '--hostName',
                                                     self.ldap_hostname,
                                                     '--port',
                                                     self.ldap_admin_port,
                                                     '--bindDN',
                                                     '"%s"' % self.ldap_binddn,
                                                     '-j', self.ldapPassFn,
                                                     '--trustAll',
                                                     '--noPropertiesFile',
                                                     '--no-prompt'])
                                self.run(['/bin/su',
                                          'ldap',
                                          '-c',
                                          indexCmd])
            else:
                self.logIt('NO indexes found %s' % self.indexJson, True)
        except:
            self.logIt("Error occured during backend " + backend + " LDAP indexing", True)
            self.logIt(traceback.format_exc(), True)

    def index_opendj(self):
        self.index_opendj_backend('userRoot')
        self.index_opendj_backend('site')

    def prepare_opendj_schema(self):
        self.logIt("Copying OpenDJ schema")
        for schemaFile in self.openDjschemaFiles:
            self.copyFile(schemaFile, self.openDjSchemaFolder)

        self.run([self.cmd_chmod, '-R', 'a+rX', self.ldapBaseFolder])
        self.run([self.cmd_chown, '-R', 'ldap:ldap', self.ldapBaseFolder])

    def setup_opendj_service(self):
        service_path = self.detect_service_path()

        if self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd':
            opendj_script_name = os.path.split(self.opendj_service_centos7)[-1]
            opendj_dest_folder = "/etc/systemd/system"
            try:
                self.copyFile(self.opendj_service_centos7, opendj_dest_folder)
                self.run([service_path, 'daemon-reload'])
                self.run([service_path, 'enable', 'opendj.service'])
                self.run([service_path, 'start', 'opendj.service'])
            except:
                self.logIt("Error copying script file %s to %s" % (opendj_script_name, opendj_dest_folder))
                self.logIt(traceback.format_exc(), True)
        else:
            os.environ["OPENDJ_JAVA_HOME"] =  self.jre_home
            self.run([self.ldapDsCreateRcCommand, "--outputFile", "/etc/init.d/opendj", "--userName",  "ldap"])
            # Make the generated script LSB compliant   
            lsb_str=(
                    '### BEGIN INIT INFO\n'
                    '# Provides:          opendj\n'
                    '# Required-Start:    $remote_fs $syslog\n'
                    '# Required-Stop:     $remote_fs $syslog\n'
                    '# Default-Start:     2 3 4 5\n'
                    '# Default-Stop:      0 1 6\n'
                    '# Short-Description: Start daemon at boot time\n'
                    '# Description:       Enable service provided by daemon.\n'
                    '### END INIT INFO\n'
                    )

            self.insertLinesInFile("/etc/init.d/opendj", 1, lsb_str)

            if self.os_type in ['ubuntu', 'debian']:
                self.run(["/usr/sbin/update-rc.d", "-f", "opendj", "remove"])

            self.fix_init_scripts('opendj', '/etc/init.d/opendj')
            self.enable_service_at_start('opendj')
            
            if self.opendj_type == 'wrends':
                self.run([service_path, 'opendj', 'stop'])
            
            self.run([service_path, 'opendj', 'start'])
            

    def setup_init_scripts(self):
        if self.os_initdaemon == 'initd':
            for init_file in self.init_files:
                try:
                    script_name = os.path.split(init_file)[-1]
                    self.copyFile(init_file, "/etc/init.d")
                    self.run([self.cmd_chmod, "755", "/etc/init.d/%s" % script_name])
                except:
                    self.logIt("Error copying script file %s to /etc/init.d" % init_file)
                    self.logIt(traceback.format_exc(), True)

        if self.os_type in ['centos', 'fedora']:
            for service in self.redhat_services:
                self.run(["/sbin/chkconfig", service, "on"])
        elif self.os_type in ['red']:
            for service in self.redhat_services:
                self.run(["/sbin/chkconfig", service, "on"])
        elif self.os_type in ['ubuntu', 'debian']:
            for service in self.debian_services:
                self.run(["/usr/sbin/update-rc.d", service, 'defaults'])
                self.run(["/usr/sbin/update-rc.d", service, 'enable'])

    def detect_service_path(self):
        service_path = '/sbin/service'
        if self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd':
            service_path = '/usr/bin/systemctl'
        elif self.os_type in ['debian', 'ubuntu']:
            service_path = '/usr/sbin/service'

        return service_path

    def run_service_command(self, service, operation):
        service_path = self.detect_service_path()

        try:
            if self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd':
                self.run([service_path, operation, service], None, None, True)
            else:
                self.run([service_path, service, operation], None, None, True)
        except:
            self.logIt("Error starting Jetty service '%s'" % operation)
            self.logIt(traceback.format_exc(), True)

    def start_services(self):
        # Detect service path and apache service name
        service_path = self.detect_service_path()
        apache_service_name = 'httpd'
        if self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd':
            apache_service_name = 'httpd'
        elif self.os_type in ['debian', 'ubuntu']:
            apache_service_name = 'apache2'

        # Apache HTTPD
        if self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd':
            self.run([service_path, 'enable', apache_service_name])
            self.run([service_path, 'start', apache_service_name])
        else:
            self.run([service_path, apache_service_name, 'start'])

        # LDAP services
        if self.installLdap:
            if self.ldap_type == 'openldap':
                if self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd':
                    self.run([service_path, 'restart', 'rsyslog.service'])
                    self.run([service_path, 'start', 'solserver.service'])
                else:
                    # Below two lines are specifically for Ubuntu 14.04
                    if self.os_type == 'ubuntu':
                        self.copyFile(self.rsyslogUbuntuInitFile, "/etc/init.d")
                        self.removeFile("/etc/init/rsyslog.conf")
                        rsyslogFn = os.path.split(self.rsyslogUbuntuInitFile)[-1]
                        self.run([self.cmd_chmod, "755", "/etc/init.d/%s" % rsyslogFn])
    
                    self.run([service_path, 'rsyslog', 'restart'])
                    self.run([service_path, 'solserver', 'restart'])
            elif self.ldap_type == 'opendj':
                self.run_service_command('opendj', 'stop')
                self.run_service_command('opendj', 'start')

        # Jetty services
        # Iterate through all components and start installed
        for applicationName, applicationConfiguration in self.jetty_app_configuration.iteritems():
            if applicationConfiguration['installed']:
                self.run_service_command(applicationName, 'start')
                
        # Passport service
        if self.installPassport:
            self.run_service_command('passport', 'start')

    def update_hostname(self):
        self.logIt("Copying hosts and hostname to final destination")

        #disable setting hostname
        """
        if self.os_initdaemon == 'systemd' and self.os_type in ['centos', 'red', 'fedora']:
            self.run(['/usr/bin/hostnamectl', 'set-hostname', self.hostname])
        else:
            if self.os_type in ['debian', 'ubuntu']:
                self.copyFile("%s/hostname" % self.outputFolder, self.etc_hostname)
                self.run(['/bin/chmod', '-f', '644', self.etc_hostname])

            if self.os_type in ['centos', 'red', 'fedora']:
                self.copyFile("%s/network" % self.outputFolder, self.network)

            self.run(['/bin/hostname', self.hostname])
        """

        self.copyFile("%s/hosts" % self.outputFolder, self.etc_hosts)
        self.run(['/bin/chmod', '-R', '644', self.etc_hosts])

    def install_openldap(self):
        self.logIt("Installing OpenLDAP from package")
        self.pbar.progress("Installing OpenLDAP", False)
        # Determine package type
        packageRpm = True
        packageExtension = ".rpm"
        if self.os_type in ['debian', 'ubuntu']:
            packageRpm = False
            packageExtension = ".deb"

        openLdapDistFolder = "%s/%s" % (self.distFolder, "symas")

        # Find package
        packageName = None
        for file in os.listdir(openLdapDistFolder):
            if file.endswith(packageExtension):
                packageName = "%s/%s" % ( openLdapDistFolder, file )

        if packageName == None:
            self.logIt('Failed to find OpenLDAP package in folder %s !' % openLdapDistFolder)
            return

        self.logIt("Found package '%s' for install" % packageName)
        if packageRpm:
            self.run([self.cmd_rpm, '--install', '--verbose', '--hash', packageName])
        else:
            self.run([self.cmd_dpkg, '--install', packageName])

        openldapRunFolder = '/var/symas/run'
        self.run([self.cmd_chmod, '-R', '775', openldapRunFolder])
        self.run([self.cmd_chgrp, '-R', 'ldap', openldapRunFolder])

    def get_openldap_indexes(self):
        """Function that reads the static/openldap/index.json file and generates
        slapd.conf compatible index configuration string"""
        f = open(self.opendlapIndexDef, 'r')
        jsoninfo = json.loads(f.read())
        f.close()
        outString = ""
        for entry in jsoninfo["indexes"]:
            outString += "\t".join(["index", entry["attribute"], entry["index"]]) + "\n"
        return outString


    def configure_openldap(self):
        self.logIt("Configuring OpenLDAP")
        # 1. Render templates
        self.templateRenderingDict['openldap_accesslog_conf'] = self.readFile(self.accessLogConfFile)
        self.templateRenderingDict['openldap_gluu_accesslog'] = self.readFile(self.gluuAccessLogConf)
        if not self.openldapSetupAccessLog:
            self.templateRenderingDict['openldap_accesslog_conf'] = self.commentOutText(self.templateRenderingDict['openldap_accesslog_conf'])
            self.templateRenderingDict['openldap_gluu_accesslog'] = self.commentOutText(self.templateRenderingDict['openldap_gluu_accesslog'])

        # 1.1 convert the indexes
        self.templateRenderingDict['openldap_indexes'] = self.get_openldap_indexes()

        self.renderTemplate(self.openldapSlapdConf)
        self.renderTemplate(self.openldapSymasConf)

        # 2. Copy the conf files to
        self.copyFile(self.openldapSlapdConf, self.openldapConfFolder)
        self.copyFile(self.openldapSymasConf, self.openldapConfFolder)

        # 3. Copy the schema files into place
        self.createDirs(self.openldapSchemaFolder)
        self.copyFile("%s/static/openldap/gluu.schema" % self.install_dir, self.openldapSchemaFolder)
        self.copyFile("%s/static/openldap/custom.schema" % self.install_dir, self.openldapSchemaFolder)

        self.run([self.cmd_chown, '-R', 'ldap:ldap', '/opt/gluu/data'])
        self.run([self.cmd_chmod, '-R', 'a+rX', self.openldapRootSchemaFolder])
        self.run([self.cmd_chown, '-R', 'ldap:ldap', self.openldapRootSchemaFolder])

        # 5. Create the PEM file from key and crt
        with open(self.openldapTLSCACert, 'w') as pem:
            with open(self.openldapTLSCert, 'r') as crt:
                pem.write(crt.read())
            with open(self.openldapTLSKey, 'r') as key:
                pem.write(key.read())

        with open(self.passportSpTLSCACert, 'w') as pem:
            with open(self.passportSpTLSCert, 'r') as crt:
                pem.write(crt.read())
            with open(self.passportSpTLSKey, 'r') as key:
                pem.write(key.read())

        # 6. Setup Logging
        self.run([self.cmd_mkdir, '-m', '775', '-p', self.openldapLogDir])
        if self.os_type in ['debian', 'ubuntu']:
            self.run([self.cmd_chown, '-R', 'syslog:adm', self.openldapLogDir])
        if not os.path.isdir('/etc/rsyslog.d/'):
            self.run([self.cmd_mkdir, '-p', '/etc/rsyslog.d/'])
        self.copyFile(self.openldapSyslogConf, '/etc/rsyslog.d/')
        self.copyFile(self.openldapLogrotate, '/etc/logrotate.d/')
        
        #Fix me: for some reason broken startup links are created for opendj.
        #Remove them.
        if self.os_type in ['ubuntu', 'debian']:
            self.run(["/usr/sbin/update-rc.d", "-f", "opendj", "remove"])

    def import_ldif_template_openldap(self, ldif):
        self.logIt("Importing LDIF file '%s' into OpenLDAP" % ldif)
        cmd = os.path.join(self.openldapBinFolder, 'slapadd')
        config = os.path.join(self.openldapConfFolder, 'slapd.conf')
        realInstallDir = os.path.realpath(self.install_dir)
        self.run(['/bin/su', 'ldap', '-c', "cd " + realInstallDir + "; " + " ".join([cmd, '-b', 'o=gluu', '-f', config, '-l', ldif])])

    def import_custom_ldif(self, fullPath):
        output_dir = os.path.join(fullPath, '.output')
        self.logIt("Importing Custom LDIF files")
        cmd = os.path.join(self.openldapBinFolder, 'slapadd')
        config = os.path.join(self.openldapConfFolder, 'slapd.conf')
        realInstallDir = os.path.realpath(self.install_dir)

        try:
            for ldif in self.get_filepaths(output_dir):
                custom_ldif = output_dir + '/' + ldif
                if self.ldap_type == 'openldap':
                    self.run(['/bin/su', 'ldap', '-c', "cd " + realInstallDir + "; " + " ".join([cmd, '-b', 'o=gluu', '-f', config, '-l', custom_ldif])])
                else:
                    self.import_ldif_template_opendj(custom_ldif)
        except:
            self.logIt("Error importing custom ldif file %s" % ldif, True)
            self.logIt(traceback.format_exc(), True)


    def import_ldif_openldap(self):
        self.logIt("Importing LDIF files into OpenLDAP")
        cmd = os.path.join(self.openldapBinFolder, 'slapadd')
        config = os.path.join(self.openldapConfFolder, 'slapd.conf')
        realInstallDir = os.path.realpath(self.install_dir)

        for ldif in self.ldif_files:

            if 'site.ldif' in ldif:
                db_base = 'o=site'
            elif 'metric.ldif' in ldif:
                db_base = 'o=metric'
            else:
                db_base = 'o=gluu'

            self.run(['/bin/su', 'ldap', '-c', "cd " + realInstallDir + "; " + " ".join([cmd, '-b', db_base, '-f', config, '-l', ldif])])

    def import_custom_ldif_openldap(self, fullPath):
        output_dir = fullPath + '.output'

        self.logIt("Importing Custom LDIF files into OpenLDAP")
        cmd = os.path.join(self.openldapBinFolder, 'slapadd')
        config = os.path.join(self.openldapConfFolder, 'slapd.conf')
        realInstallDir = os.path.realpath(self.install_dir)
        try:
            for ldif in self.get_filepaths(fullPath):
                custom_ldif = output_dir + '/' + ldif
                self.run(['/bin/su', 'ldap', '-c', "cd " + realInstallDir + "; " + " ".join([cmd, '-b', 'o=gluu', '-f', config, '-l', custom_ldif])])
        except:
            self.logIt("Error importing custom ldif file %s" % ldif, True)
            self.logIt(traceback.format_exc(), True)

    def install_ldap_server(self):
        self.logIt("Running OpenDJ Setup")
        self.pbar.progress("Extracting OpenDJ", False)

        self.extractOpenDJ()
        self.opendj_version = self.determineOpenDJVersion()

        self.createLdapPw()
        try:
            self.pbar.progress("OpenDJ: installing", False)
            self.install_opendj()
    
            if self.ldap_type == 'opendj':
                self.pbar.progress("OpenDJ: preparing schema", False)
                self.prepare_opendj_schema()
                self.pbar.progress("OpenDJ: setting up service", False)
                self.setup_opendj_service()
                self.pbar.progress("OpenDJ: configuring", False)
                self.configure_opendj()
                self.export_opendj_public_cert()
                self.pbar.progress("OpenDJ: creating indexes", False)
                self.index_opendj()
                self.pbar.progress("OpenDJ: importing Ldif files", False)
                self.import_ldif_opendj()
            
            self.pbar.progress("OpenDJ: post installation", False)
            self.post_install_opendj()
        finally:
            self.deleteLdapPw()

        if self.ldap_type == 'openldap':
            self.logIt("Running OpenLDAP Setup")
            self.pbar.progress("OpenLDAP: installing", False)
            self.install_openldap()
            self.pbar.progress("OpenLDAP: configuring", False)
            self.configure_openldap()
            self.pbar.progress("OpenLDAP: importing Ldif files", False)
            self.import_ldif_openldap()

    def calculate_aplications_memory(self, application_max_ram, jetty_app_configuration, installedComponents):
        self.logIt("Calculating memory setting for applications")

        allowedApplicationsMemory = {}

        usedRatio = 0.001
        for installedComponent in installedComponents:
            usedRatio += installedComponent['memory']['ratio']

        ratioMultiplier = 1.0 + (1.0 - usedRatio)/usedRatio

        for installedComponent in installedComponents:
            allowedRatio = installedComponent['memory']['ratio'] * ratioMultiplier
            allowedMemory = int(round(allowedRatio * int(application_max_ram)))

            if allowedMemory > installedComponent['memory']['max_allowed_mb']:
                allowedMemory = installedComponent['memory']['max_allowed_mb']

            allowedApplicationsMemory[installedComponent['name']] = allowedMemory

        # Iterate through all components into order to prepare all keys
        for applicationName, applicationConfiguration in jetty_app_configuration.iteritems():
            if applicationName in allowedApplicationsMemory:
                applicationMemory = allowedApplicationsMemory.get(applicationName)
            else:
                # We uses this dummy value to render template properly of not installed application
                applicationMemory = 256

            self.templateRenderingDict["%s_max_mem" % applicationName] = applicationMemory

            if 'jvm_heap_ration' in applicationConfiguration['memory']:
                jvmHeapRation = applicationConfiguration['memory']['jvm_heap_ration']

                minHeapMem = 256
                maxHeapMem = int(applicationMemory * jvmHeapRation)
                if maxHeapMem < minHeapMem:
                    minHeapMem = maxHeapMem

                self.templateRenderingDict["%s_max_heap_mem" % applicationName] = maxHeapMem
                self.templateRenderingDict["%s_min_heap_mem" % applicationName] = minHeapMem

                self.templateRenderingDict["%s_max_meta_mem" % applicationName] = applicationMemory - self.templateRenderingDict["%s_max_heap_mem" % applicationName]

    def calculate_selected_aplications_memory(self):
        installedComponents = []

        # Jetty apps
        if self.installOxAuth:
            installedComponents.append(self.jetty_app_configuration['oxauth'])
        if self.installOxTrust:
            installedComponents.append(self.jetty_app_configuration['identity'])
        if self.installSaml:
            installedComponents.append(self.jetty_app_configuration['idp'])
        if self.installAsimba:
            installedComponents.append(self.jetty_app_configuration['asimba'])
        if self.installOxAuthRP:
            installedComponents.append(self.jetty_app_configuration['oxauth-rp'])

        # Node apps
        if self.installPassport:
            installedComponents.append(self.jetty_app_configuration['passport'])
            
        self.calculate_aplications_memory(self.application_max_ram, self.jetty_app_configuration, installedComponents)

    def merge_dicts(self, *dict_args):
        result = {}
        for dictionary in dict_args:
            result.update(dictionary)

        return result

    # MB: will be removed after all init scripts is fixed
    ##### Below function is temporary and will serve only 
    ##### Untill we're done with systemd units for all services for Ubuntu 16 and CentOS 7
    def process_rc_links(self, init_fixes):
        if self.os_type in ['ubuntu', 'debian']:
            for appName, initFixes in init_fixes.iteritems():
                src_pattern = initFixes['src_pattern']
                result_name = initFixes['result_name']

                init_file = self.findFiles(src_pattern, '/etc/rc3.d')
                if len(init_file) > 0:
                        self.run(['mv -f %s%s %s%s' % ('/etc/rc3.d/', src_pattern, '/etc/rc3.d/', result_name)], None, None, True, True)


    def run_command(self, cmd):
        
        self.logIt("Running command: "+cmd)

        p = subprocess.Popen(cmd, shell=True,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, close_fds=True)

        sin, sout, serr = (p.stdin, p.stdout, p.stderr)
        o = sout.read().strip()
        e = serr.read().strip()
        
        self.logIt(o+'\n')
        
        if e:
            self.logIt(e+'\n', True)

        return o, e



    def check_and_install_packages(self):

        if self.os_type in ('ubuntu', 'debian'):
            install_command = 'DEBIAN_FRONTEND=noninteractive apt-get install -y {0}'
            update_command = 'DEBIAN_FRONTEND=noninteractive apt-get update -y'
            query_command = 'dpkg -l {0}'
            check_text = 'no packages found matching'

        elif self.os_type in ('centos', 'red', 'fedora'):
            install_command = 'yum install -y {0}'
            update_command = 'yum install -y epel-release'
            query_command = 'rpm -q {0}'
            check_text = 'is not installed'


        install_list = []

        package_list = {
                'debian 9': 'apache2 curl wget tar xz-utils unzip facter python rsyslog',
                'debian 8': 'apache2 curl wget tar xz-utils unzip facter python rsyslog',
                'ubuntu 14': 'apache2 curl wget xz-utils unzip facter python rsyslog',
                'ubuntu 16': 'apache2 curl wget xz-utils unzip facter python rsyslog',
                'ubuntu 18': 'apache2 curl wget xz-utils unzip facter python rsyslog',
                'centos 6': 'httpd mod_ssl curl wget tar xz unzip facter python rsyslog',
                'centos 7': 'httpd mod_ssl curl wget tar xz unzip facter python rsyslog',
                'red 6': 'httpd mod_ssl curl wget tar xz unzip facter python rsyslog',
                'red 7': 'httpd mod_ssl curl wget tar xz unzip facter python rsyslog',
                'fedora 22': 'httpd mod_ssl curl wget tar xz unzip facter python rsyslog'
                }
        for package in package_list[self.os_type+' '+self.os_version].split():
            sout, serr = self.run_command(query_command.format(package))
            if check_text in sout+serr:
                self.logIt('Package {0} was not installed'.format(package))
                install_list.append(package)
            else:
                self.logIt('Package {0} was installed'.format(package))

        if install_list:

            install = True

            if not setupOptions['noPrompt']:

                print "The following packages are required for Gluu Server"
                print "\n".join(install_list)
                r = raw_input("Do you want to install these now? [Y/n] ")
                if r.lower()=='n':
                    install = False
                    print("Can not proceed without installing required packages. Exiting ...")
                    sys.exit()

            if install:
                self.logIt("Installing packages")
                if not self.os_type == 'fedora':
                    sout, serr = self.run_command(update_command)
                self.run_command(install_command.format(" ".join(install_list)))



        self.run_command('pip install pyDes')

        if self.os_type in ('ubuntu', 'debian'):
            self.run_command('a2enmod ssl headers proxy proxy_http proxy_ajp')
            default_site = '/etc/apache2/sites-enabled/000-default.conf'
            if os.path.exists(default_site):
                os.remove(default_site)

    def loadTestData(self):
        
        self.logIt("Loading test ldif files")
        ox_auth_test_ldif = os.path.join(self.outputFolder, 'test/oxauth/data/oxauth-test-data.ldif')
        scim_test_ldif = os.path.join(self.outputFolder, 'test/scim-client/data/scim-test-data.ldif')    
        ldif_files = [ox_auth_test_ldif, scim_test_ldif]
        
        self.import_ldif_couchebase(ldif_files)


############################   Main Loop   #################################################

def print_help():
    print "\nUse setup.py to configure your Gluu Server and to add initial data required for"
    print "oxAuth and oxTrust to start. If setup.properties is found in this folder, these"
    print "properties will automatically be used instead of the interactive setup."
    print "Options:"
    print ""
    print "    -a   Install Asimba"
    print "    -r   Install oxAuth RP"
    print "    -p   Install Passport"
    print "    -d   specify the directory where community-edition-setup is located. Defaults to '.'"
    print "    -f   specify setup.properties file"
    print "    -h   Help"
    print "    -n   No interactive prompt before install starts. Run with -f"
    print "    -N   No apache httpd server"
    print "    -s   Install the Shibboleth IDP"
    print "    -u   Update hosts file with IP address / hostname"
    print "    -w   Get the development head war files"
#    print "    --allow_pre_released_applications"
    print "    --allow_deprecated_applications"
    print "    --import-ldif=custom-ldif-dir Render ldif templates from custom-ldif-dir and import them in LDAP"
    print "    --listen_all_interfaces"

def getOpts(argv, setupOptions):
    try:
        opts, args = getopt.getopt(argv, "adp:f:hNnsuwrev", ['allow_pre_released_applications', 'allow_deprecated_applications', 'import-ldif=', 'listen_all_interfaces'])
    except getopt.GetoptError:
        print_help()
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-a':
            setupOptions['installAsimba'] = True
        elif opt == '-d':
            if os.path.exists(arg):
                setupOptions['install_dir'] = arg
            else:
                print 'System folder %s does not exist. Installing in %s' % (arg, os.getcwd())
        elif opt == '-h':
            print_help()
            sys.exit()
        elif opt == "-f":
            try:
                if os.path.isfile(arg):
                    setupOptions['setup_properties'] = arg
                    print "Found setup properties %s\n" % arg
                else:
                    print "\nOoops... %s file not found for setup properties.\n" % arg
            except:
                print "\nOoops... %s file not found\n" % arg

        elif opt == "-n":
            setupOptions['noPrompt'] = True
        elif opt == "-N":
            setupOptions['installHTTPD'] = False
        elif opt == "-s":
            setupOptions['installSaml'] = True
        elif opt == "-u":
            pass  # TODO implement this option or remove it from help
        elif opt == "-w":
            setupOptions['downloadWars'] = True
        elif opt == '-r':
            setupOptions['installOxAuthRP'] = True
        elif opt == '-p':
            setupOptions['installPassport'] = True
        elif opt == "-t":
            setupOptions['loadTestData'] = True
        elif opt == '--allow_pre_released_applications':
            setupOptions['allowPreReleasedApplications'] = True
        elif opt == '--allow_deprecated_applications':
            setupOptions['allowDeprecatedApplications'] = True
        elif opt == '--listen_all_interfaces':
            setupOptions['listenAllInterfaces'] = True
        elif opt == '--import-ldif':
            if os.path.isdir(arg):
                setupOptions['importLDIFDir'] = arg
                print "Found setup LDIF import directory %s\n" % (arg)
            else:
                print 'The custom LDIF import directory %s does not exist. Exiting...' % (arg)
                sys.exit(2)
    return setupOptions

if __name__ == '__main__':

    setupOptions = {
        'install_dir': os.path.dirname(os.path.realpath(__file__)),
        'setup_properties': None,
        'noPrompt': False,
        'downloadWars': False,
        'installOxAuth': True,
        'installOxTrust': True,
        'installLDAP': True,
        'installHTTPD': True,
        'installSaml': False,
        'installAsimba': False,
        'installOxAuthRP': False,
        'installPassport': False,
        'loadTestData': False,
        'allowPreReleasedApplications': False,
        'allowDeprecatedApplications': False,
        'listenAllInterfaces': False
    }

    if len(sys.argv) > 1:
        setupOptions = getOpts(sys.argv[1:], setupOptions)

    installObject = Setup(setupOptions['install_dir'])

    if installObject.check_installed():
        print "\nThis instance already configured. If you need to install new one you should reinstall package first."
        sys.exit(2)

    installObject.downloadWars = setupOptions['downloadWars']

    installObject.installOxAuth = setupOptions['installOxAuth']
    installObject.installOxTrust = setupOptions['installOxTrust']
    installObject.installLdap = setupOptions['installLDAP']
    installObject.installHttpd = setupOptions['installHTTPD']
    installObject.installSaml = setupOptions['installSaml']
    installObject.installAsimba = setupOptions['installAsimba']
    installObject.installOxAuthRP = setupOptions['installOxAuthRP']
    installObject.installPassport = setupOptions['installPassport']
    installObject.allowPreReleasedApplications = setupOptions['allowPreReleasedApplications']
    installObject.allowDeprecatedApplications = setupOptions['allowDeprecatedApplications']
    installObject.listenAllInterfaces = setupOptions['listenAllInterfaces']

    # Get the OS type
    installObject.os_type, installObject.os_version = installObject.detect_os_type()
    # Get the init type
    installObject.os_initdaemon = installObject.detect_initd()
    
    installObject.check_and_install_packages()
    #it is time to import pyDes library
    from pyDes import *
    
    # Get apache version
    installObject.apache_version = installObject.determineApacheVersionForOS()


    print "\nInstalling Gluu Server..."
    print "Detected OS  :  %s" % installObject.os_type
    print "Detected init:  %s" % installObject.os_initdaemon
    print "Detected Apache:  %s" % installObject.apache_version

    print "\nInstalling Gluu Server...\n\nFor more info see:\n  %s  \n  %s\n" % (installObject.log, installObject.logError)
    print "\n** All clear text passwords contained in %s.\n" % installObject.savedProperties
    try:
        os.remove(installObject.log)
        installObject.logIt('Removed %s' % installObject.log)
    except:
        pass
    try:
        os.remove(installObject.logError)
        installObject.logIt('Removed %s' % installObject.logError)
    except:
        pass

    installObject.logIt("Installing Gluu Server", True)

    if setupOptions['setup_properties']:
        installObject.logIt('%s Properties found!\n' % setupOptions['setup_properties'])
        installObject.load_properties(setupOptions['setup_properties'])
    elif os.path.isfile(installObject.setup_properties_fn):
        installObject.logIt('%s Properties found!\n' % installObject.setup_properties_fn)
        installObject.load_properties(installObject.setup_properties_fn)
    else:
        installObject.logIt("%s Properties not found. Interactive setup commencing..." % installObject.setup_properties_fn)
        installObject.promptForProperties()

    # Validate Properties
    installObject.check_properties()

    if 'importLDIFDir' in setupOptions.keys():
        if os.path.isdir(installObject.openldapBaseFolder):
            installObject.logIt("Gluu server already installed. Setup will render and import templates and exit.", True)
            installObject.render_custom_templates(setupOptions['importLDIFDir'])
            installObject.import_custom_ldif(setupOptions['importLDIFDir'])
            installObject.logIt("Setup is exiting now after import of ldifs generated.", True)
            sys.exit(2)

    # Show to properties for approval
    print '\n%s\n' % `installObject`
    proceed = "NO"
    if not setupOptions['noPrompt']:
        proceed = raw_input('Proceed with these values [Y|n] ').lower().strip()
    if (setupOptions['noPrompt'] or not len(proceed) or (len(proceed) and (proceed[0] == 'y'))):
        try:
            installObject.pbar.progress("Initializing")
            installObject.initialize()
            installObject.pbar.progress("Configuring system")
            installObject.configureSystem()
            installObject.pbar.progress("Downloading War files")
            installObject.downloadWarFiles()
            installObject.pbar.progress("Calculating application memory")
            installObject.calculate_selected_aplications_memory()
            installObject.pbar.progress("Installing JRE")
            installObject.installJRE()
            installObject.pbar.progress("Installing Jetty")
            installObject.installJetty()
            installObject.pbar.progress("Installing Jython")
            installObject.installJython()
            installObject.pbar.progress("Installing Node")
            installObject.installNode()
            installObject.pbar.progress("Making salt")
            installObject.make_salt()
            installObject.pbar.progress("Making oxauth salt")
            installObject.make_oxauth_salt()
            installObject.pbar.progress("Copying scripts")
            installObject.copy_scripts()
            installObject.pbar.progress("Encoding passwords")
            installObject.encode_passwords()
            installObject.pbar.progress("Encoding test passwords")
            installObject.encode_test_passwords()
            installObject.pbar.progress("Installing Gluu base")
            installObject.install_gluu_base()
            installObject.pbar.progress("Preparing bas64 extention scripts")
            installObject.prepare_base64_extension_scripts()
            installObject.pbar.progress("Rendering templates")
            installObject.render_templates()
            installObject.pbar.progress("Generating crypto")
            installObject.generate_crypto()
            installObject.pbar.progress("Generating oxauth openid keys")
            installObject.generate_oxauth_openid_keys()
            installObject.pbar.progress("Generating base64 configuration")
            installObject.generate_base64_configuration()
            installObject.pbar.progress("Rendering configuratipn template")
            installObject.render_configuration_template()
            installObject.pbar.progress("Updating hostname")
            installObject.update_hostname()
            installObject.pbar.progress("Setting ulimits")
            installObject.set_ulimits()
            installObject.pbar.progress("Copying output")
            installObject.copy_output()
            installObject.pbar.progress("Setting up init scripts")
            installObject.setup_init_scripts()
            installObject.pbar.progress("Rendering node templates")
            installObject.render_node_templates()
            installObject.pbar.progress("Installing Gluu components")
            installObject.install_gluu_components()
            installObject.pbar.progress("Rendering test templates")
            installObject.render_test_templates()
            installObject.pbar.progress("Copying static")
            installObject.copy_static()
            installObject.pbar.progress("Setting ownerships")
            installObject.set_ownership()
            installObject.pbar.progress("Setting permissions")
            installObject.set_permissions()
            installObject.pbar.progress("Starting services")
            installObject.start_services()
            installObject.pbar.progress("Saving properties")
            installObject.save_properties()

            if setupOptions['loadTestData']:
                installObject.pbar.progress("Loading test data", False)
                installObject.loadTestData()

            if 'importLDIFDir' in setupOptions.keys():
                installObject.pbar.progress("Importing LDIF files")
                installObject.render_custom_templates(setupOptions['importLDIFDir'])
                installObject.import_custom_ldif(setupOptions['importLDIFDir'])
            
            installObject.pbar.complete("Completed")
            print
        except:
            installObject.logIt("***** Error caught in main loop *****", True)
            installObject.logIt(traceback.format_exc(), True)
        print "\n\n Gluu Server installation successful! Point your browser to https://%s\n\n" % installObject.hostname
    else:
        installObject.save_properties()
        print "Properties saved to %s. Change filename to %s if you want to re-use" % \
              (installObject.savedProperties, installObject.setup_properties_fn)

# END
