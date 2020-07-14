#!/usr/bin/python3

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
try:
    import warnings
    warnings.filterwarnings("ignore")
except:
    pass

import readline
import sys
import os
import os.path
import site
import shutil
import socket
import string
import time
import json
import traceback
import subprocess
import sys
import argparse
import hashlib
import re
import glob
import base64
import copy
import random
import ssl
import uuid
import multiprocessing
import io
import zipfile
import datetime
import urllib.request, urllib.error, urllib.parse
import locale

from collections import OrderedDict
from xml.etree import ElementTree
from urllib.parse import urlparse
from pathlib import Path

from pylib import gluu_utils
from pylib.jproperties import Properties
from pylib.printVersion import get_war_info
from pylib.ldif3.ldif3 import LDIFWriter
from pylib.schema import ObjectClass

cur_dir = os.path.dirname(os.path.realpath(__file__))

#copy pyDes to site for further use
site_libdir = site.getsitepackages()[0]
if not os.path.exists(site_libdir):
    os.makedirs(site_libdir)

shutil.copy(
        os.path.join(cur_dir, 'pylib/pyDes.py'),
        site_libdir
        )

from pyDes import *

os_type, os_version = gluu_utils.get_os_type()

if not os_version in gluu_utils.supportes_os_types.get(os_type, []):
    print("Gluu Server supports these OSes")
    for os_ in gluu_utils.supportes_os_types:
        if gluu_utils.supportes_os_types[os_]:
            print("{}: {}".format(
                    os_.title(), 
                    ', '.join(gluu_utils.supportes_os_types[os_]))
                )
    sys.exit("Exiting...\n")


#install types
NONE = 0
LOCAL = '1'
REMOTE = '2'

COMPLETED = -99
ERROR = -101

suggested_mem_size = 3.7 # in GB
suggested_number_of_cpu = 2
suggested_free_disk_space = 40 #in GB

re_split_host = re.compile(r'[^,\s,;]+')

thread_queue = None
terminal_size = shutil.get_terminal_size()

try:
    from pylib.cbm import CBM
except:
    pass


class ProgressBar:

    def __init__(self, cols, queue=None, max_steps=33):
        self.n = 0
        self.queue = queue
        self.max_steps = max_steps
        self.tty_columns = int(cols)

    def complete(self, msg):
        self.n = self.max_steps
        self.progress(msg, False)

    def progress(self, ptype, msg, incr=True):
        if incr and self.n < self.max_steps:
            self.n +=1

        time.sleep(0.2)

        if self.queue:
            if msg == 'Completed':
                self.queue.put((COMPLETED, ptype, msg))
            else:
                self.queue.put((self.n, ptype, msg))
        else:
            ft = '#' * self.n
            ft = ft.ljust(self.max_steps)
            msg =msg.ljust(40)

            if self.tty_columns < 88:
                msg = msg[:self.tty_columns-47]

            sys.stdout.write("\rInstalling [{0}] {1}".format(ft, msg))
            sys.stdout.flush()


class Setup(object):
    def __init__(self, install_dir=None):
        self.install_dir = install_dir
        self.thread_queue = None
        self.properties_password = None
        self.noPrompt = False

        self.distFolder = '/opt/dist'
        self.distAppFolder = '%s/app' % self.distFolder
        self.distGluuFolder = '%s/gluu' % self.distFolder
        self.distTmpFolder = '%s/tmp' % self.distFolder
        
        oxauth_info = get_war_info(os.path.join(self.distGluuFolder, 'oxauth.war'))

        self.oxVersion = oxauth_info['version']
        self.currentGluuVersion = re.search('([\d.]+)', oxauth_info['version']).group().strip('.')
        self.githubBranchName = oxauth_info['branch']

        # Used only if -w (get wars) options is given to setup.py
        self.oxauth_war = 'https://ox.gluu.org/maven/org/gluu/oxauth-server/%s/oxauth-server-%s.war' % (self.oxVersion, self.oxVersion)
        self.oxauth_rp_war = 'https://ox.gluu.org/maven/org/gluu/oxauth-rp/%s/oxauth-rp-%s.war' % (self.oxVersion, self.oxVersion)
        self.oxtrust_war = 'https://ox.gluu.org/maven/org/gluu/oxtrust-server/%s/oxtrust-server-%s.war' % (self.oxVersion, self.oxVersion)
        self.idp3_war = 'https://ox.gluu.org/maven/org/gluu/oxshibbolethIdp/%s/oxshibbolethIdp-%s.war' % (self.oxVersion, self.oxVersion)
        self.idp3_dist_jar = 'https://ox.gluu.org/maven/org/gluu/oxShibbolethStatic/%s/oxShibbolethStatic-%s.jar' % (self.oxVersion, self.oxVersion)
        self.idp3_cml_keygenerator = 'https://ox.gluu.org/maven/org/gluu/oxShibbolethKeyGenerator/%s/oxShibbolethKeyGenerator-%s.jar' % (self.oxVersion, self.oxVersion)
        self.ce_setup_zip = 'https://github.com/GluuFederation/community-edition-setup/archive/%s.zip' % self.githubBranchName

        self.downloadWars = None
        self.templateRenderingDict = {
                                        'oxauthClient_2_inum': 'AB77-1A2B',
                                        'oxauthClient_3_inum': '3E20',
                                        'oxauthClient_4_inum': 'FF81-2D39',
                                        'idp_attribute_resolver_ldap.search_filter': '(|(uid=$requestContext.principalName)(mail=$requestContext.principalName))',
                                        'oxd_port': '8443',
                                     }

        # OS commands
        self.cmd_ln = '/bin/ln'
        self.cmd_chmod = '/bin/chmod'
        self.cmd_chown = '/bin/chown'
        self.cmd_chgrp = '/bin/chgrp'
        self.cmd_mkdir = '/bin/mkdir'
        self.cmd_rpm = '/bin/rpm'
        self.cmd_dpkg = '/usr/bin/dpkg'
        self.opensslCommand = shutil.which('openssl')
        self.systemctl = shutil.which('systemctl')

        self.sysemProfile = "/etc/profile"

        # java commands
        self.jre_home = '/opt/jre'
        self.cmd_java = '%s/bin/java' % self.jre_home
        self.cmd_keytool = '%s/bin/keytool' % self.jre_home
        self.cmd_jar = '%s/bin/jar' % self.jre_home
        os.environ["OPENDJ_JAVA_HOME"] =  self.jre_home

        # Component ithversions
        self.apache_version = None
        self.opendj_version = None

        #passwords
        self.ldapPass = None
        self.oxtrust_admin_password = None
        self.encoded_admin_password = ''
        self.cb_password = None
        self.encoded_cb_password = ''

        #DB installation types
        self.wrends_install = LOCAL
        self.cb_install = NONE

        # Gluu components installation status
        self.loadData = True
        self.installOxAuth = True
        self.installOxTrust = True
        self.installHttpd = True
        self.installSaml = False
        self.installOxAuthRP = False
        self.installPassport = False
        self.installGluuRadius = False
        self.installScimServer = False
        self.installFido2 = False

        self.gluuPassportEnabled = 'false'
        self.gluuRadiusEnabled = 'false'
        self.gluuSamlEnabled = 'false'
        self.scimTestMode = 'false'
        self.gluuScimEnabled = 'false'
        
        self.enable_scim_access_policy = 'false'
        
        self.allowPreReleasedFeatures = False

        self.os_type = None
        self.os_initdaemon = None

        self.persistence_type = 'ldap'
        self.shibboleth_version = 'v3'

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
        
        self.gluu_properties_fn = '%s/gluu.properties' % self.configFolder
        self.gluu_hybrid_roperties = '%s/gluu-hybrid.properties' % self.configFolder

        self.oxBaseDataFolder = "/var/gluu"
        self.oxPhotosFolder = "/var/gluu/photos"
        self.oxTrustRemovedFolder = "/var/gluu/identity/removed"
        self.oxTrustCacheRefreshFolder = "/var/gluu/identity/cr-snapshots"
        self.cache_provider_type = 'NATIVE_PERSISTENCE'

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

        self.open_jdk_archive_link = 'https://github.com/AdoptOpenJDK/openjdk11-binaries/releases/download/jdk-11.0.4%2B11/OpenJDK11U-jdk_x64_linux_hotspot_11.0.4_11.tar.gz'
        self.java_type = 'jre'

        self.jetty_home = '/opt/jetty'
        self.jetty_base = '%s/jetty' % self.gluuOptFolder
        self.jetty_user_home = '/home/jetty'
        self.jetty_user_home_lib = '%s/lib' % self.jetty_user_home
        self.jetty_app_configuration = OrderedDict((
                ('oxauth', {'name' : 'oxauth',
                            'jetty' : {'modules' : 'server,deploy,annotations,resources,http,http-forwarded,threadpool,console-capture,jsp,websocket'},
                            'memory' : {'ratio' : 0.20, "jvm_heap_ration" : 0.7, "max_allowed_mb" : 2048, 'metaspace_mb': 128},
                            'installed' : False
                            }),
                ('identity', {'name' : 'identity',
                              'jetty' : {'modules' : 'server,deploy,annotations,resources,http,http-forwarded,threadpool,console-capture,jsp,websocket'},
                              'memory' : {'ratio' : 0.20, "jvm_heap_ration" : 0.7, "max_allowed_mb" : 2048, 'metaspace_mb': 128},
                              'installed' : False
                              }),
                ('idp', {'name' : 'idp',
                         'jetty' : {'modules' : 'server,deploy,annotations,resources,http,http-forwarded,threadpool,console-capture,jsp'},
                         'memory' : {'ratio' : 0.20, "jvm_heap_ration" : 0.7, "max_allowed_mb" : 2048, 'metaspace_mb': 128},
                         'installed' : False
                         }),

                ('oxauth-rp', {'name' : 'oxauth-rp',
                               'jetty' : {'modules' : 'server,deploy,annotations,resources,http,http-forwarded,threadpool,console-capture,jsp,websocket'},
                               'memory' : {'ratio' : 0.08, "jvm_heap_ration" : 0.85, "max_allowed_mb" : 384, 'metaspace_mb': 64},
                               'installed' : False
                               }),
                ('passport', {'name' : 'passport',
                              'node' : {},
                              'memory' : {'ratio' : 0.08, "max_allowed_mb" : 1024, 'metaspace_mb': 128},
                              'installed' : False
                               }),
                ('casa', {'name': 'casa',
                         'jetty': {'modules': 'server,deploy,resources,http,http-forwarded,console-capture,jsp'},
                         'memory': {'ratio': 0.08, "jvm_heap_ration": 0.7, "max_allowed_mb": 1024, 'metaspace_mb': 128},
                         'installed': False
                         }),
                ('fido2', {'name' : 'fido2',
                            'jetty' : {'modules' : 'server,deploy,resources,http,http-forwarded,threadpool,console-capture,jsp'},
                            'memory' : {'ratio' : 0.08, "jvm_heap_ration" : 0.7, "max_allowed_mb" : 512, 'metaspace_mb': 128},
                            'installed' : False
                            }),
                ('scim', {'name': 'scim',
                         'jetty': {'modules': 'server,deploy,resources,http,http-forwarded,console-capture,jsp'},
                         'memory': {'ratio': 0.08, "jvm_heap_ration": 0.7, "max_allowed_mb": 1024, 'metaspace_mb': 128},
                         'installed': False
                         }),
            ))

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
        self.couchbaseShibUserPassword = None

        self.hostname = None
        self.ip = None
        self.orgName = None
        self.countryCode = None
        self.city = None
        self.state = None
        self.admin_email = None
        self.encoded_ox_ldap_pw = None
        self.encoded_shib_jks_pw = None
        self.application_max_ram = int(current_mem_size * .83 * 1000) # 83% of physical memory
        self.encode_salt = None
        self.admin_inum = None

        self.ldapBaseFolderldapPass = None

        self.oxauth_client_id = None
        self.oxauthClient_pw = None
        self.oxauthClient_encoded_pw = None

        self.idp_client_id = None
        self.idpClient_pw = None
        self.idpClient_encoded_pw = None

        self.oxTrustConfigGeneration = None

        self.outputFolder = '%s/output' % self.install_dir
        self.templateFolder = '%s/templates' % self.install_dir
        self.staticFolder = '%s/static' % self.install_dir

        self.extensionFolder = '%s/extension' % self.staticFolder

        self.oxauth_error_json = '%s/oxauth/oxauth-errors.json' % self.staticFolder

        self.oxauth_openid_jwks_fn = "%s/oxauth-keys.json" % self.outputFolder
        self.oxauth_openid_jks_fn = "%s/oxauth-keys.jks" % self.certFolder
        self.oxauth_openid_jks_pass = None

        self.httpdKeyPass = None
        self.httpdKeyFn = '%s/httpd.key' % self.certFolder
        self.httpdCertFn = '%s/httpd.crt' % self.certFolder
        self.shibJksPass = None
        self.shibJksFn = '%s/shibIDP.jks' % self.certFolder

        self.ldapTrustStoreFn = None
        self.encoded_ldapTrustStorePass = None

        self.opendj_cert_fn = '%s/opendj.crt' % self.certFolder
        self.opendj_p12_fn = '%s/opendj.pkcs12' % self.certFolder
        self.opendj_p12_pass = None

        self.ldap_binddn = 'cn=directory manager'
        self.ldap_hostname = "localhost"
        self.couchbase_hostname = "localhost"
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

        self.passportSpKeyPass = None
        self.passportSpTLSCACert = '%s/passport-sp.pem' % self.certFolder
        self.passportSpTLSCert = '%s/passport-sp.crt' % self.certFolder
        self.passportSpTLSKey = '%s/passport-sp.key' % self.certFolder
        self.passportSpJksPass = None
        self.passportSpJksFn = '%s/passport-sp.jks' % self.certFolder


        # Stuff that gets rendered; filename is necessary. Full path should
        # reflect final path if the file must be copied after its rendered.
        self.passport_central_config_json = '%s/passport-central-config.json' % self.outputFolder
        self.oxauth_config_json = '%s/oxauth-config.json' % self.outputFolder
        self.oxtrust_config_json = '%s/oxtrust-config.json' % self.outputFolder
        self.oxtrust_cache_refresh_json = '%s/oxtrust-cache-refresh.json' % self.outputFolder
        self.oxtrust_import_person_json = '%s/oxtrust-import-person.json' % self.outputFolder
        self.oxidp_config_json = '%s/oxidp-config.json' % self.outputFolder
        self.gluu_python_base = '%s/python' % self.gluuOptFolder
        self.gluu_python_readme = '%s/libs/python.txt' % self.gluuOptPythonFolder
        self.ox_ldap_properties = '%s/gluu-ldap.properties' % self.configFolder
        self.oxauth_static_conf_json = '%s/oxauth-static-conf.json' % self.outputFolder
        self.oxTrust_log_rotation_configuration = "%s/conf/oxTrustLogRotationConfiguration.xml" % self.gluuBaseFolder
        self.apache2_conf = '%s/httpd.conf' % self.outputFolder
        self.apache2_ssl_conf = '%s/https_gluu.conf' % self.outputFolder
        self.apache2_24_conf = '%s/httpd_2.4.conf' % self.outputFolder
        self.apache2_ssl_24_conf = '%s/https_gluu.conf' % self.outputFolder
        self.ldif_base = '%s/base.ldif' % self.outputFolder
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
        self.ldif_scim_clients = '%s/scim_clients.ldif' % self.outputFolder
        
        self.fido2_dynamic_conf_json = '%s/fido2-dynamic-conf.json' % self.outputFolder
        self.fido2_static_conf_json = '%s/fido2-static-conf.json' % self.outputFolder
        self.ldif_fido2 = '%s/fido2.ldif' % self.outputFolder
        
        self.lidf_oxtrust_api = '%s/oxtrust_api.ldif' % self.outputFolder
        self.ldif_oxtrust_api_clients = '%s/oxtrust_api_clients.ldif' % self.outputFolder

        self.ldif_scripts_casa = '%s/scripts_casa.ldif' % self.outputFolder
        self.passport_config = '%s/passport-config.json' % self.configFolder
        self.encode_script = '%s/bin/encode.py' % self.gluuOptFolder
        self.network = "/etc/sysconfig/network"
        self.system_profile_update_init = '%s/system_profile_init' % self.outputFolder
        self.system_profile_update_systemd = '%s/system_profile_systemd' % self.outputFolder

        self.staticIDP3FolderConf = '%s/static/idp3/conf' % self.install_dir
        self.staticIDP3FolderMetadata = '%s/static/idp3/metadata' % self.install_dir
        self.idp3_configuration_properties = 'idp.properties'
        self.idp3_configuration_ldap_properties = 'ldap.properties'
        self.idp3_configuration_saml_nameid = 'saml-nameid.properties'
        self.idp3_configuration_services = 'services.properties'
        self.idp3_configuration_password_authn = 'authn/password-authn-config.xml'
        self.idp3_metadata = 'idp-metadata.xml'
        self.data_source_properties = 'datasource.properties'

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

        # oxTrust Api configuration
        self.api_rs_client_jks_fn = '%s/api-rs.jks' % self.certFolder
        self.api_rs_client_jks_pass = 'secret'
        self.api_rs_client_jwks = None
        self.api_rp_client_jks_fn = '%s/api-rp.jks' % self.certFolder
        self.api_rp_client_jks_pass = 'secret'
        self.api_rp_client_jwks = None

        self.oxtrust_resource_id = None
        self.oxtrust_requesting_party_client_id = None
        self.oxtrust_resource_server_client_id = None

        # oxPassport Configuration
        self.gluu_passport_base = '%s/passport' % self.node_base
        self.passport_oxtrust_config_fn = '%s/passport_oxtrust_config.son' % self.outputFolder
        self.ldif_passport_config = '%s/oxpassport-config.ldif' % self.outputFolder
        self.ldif_passport = '%s/passport.ldif' % self.outputFolder
        self.ldif_passport_clients = '%s/passport_clients.ldif' % self.outputFolder
        self.ldif_idp = '%s/oxidp.ldif' % self.outputFolder
        
        self.passport_rs_client_id = None
        self.passport_rs_client_jwks = None
        self.passport_rs_client_jks_fn = "%s/passport-rs.jks" % self.certFolder
        self.passport_rs_client_jks_pass = None
        self.passport_rs_client_jks_pass_encoded = None

        self.passport_rp_ii_client_id = None
        self.passport_rp_client_id = None
        self.passport_rp_client_jwks = None
        self.passport_rp_client_jks_fn = "%s/passport-rp.jks" % self.certFolder
        self.passport_rp_client_cert_alg = "RS512"
        self.passport_rp_client_cert_alias = None
        self.passport_rp_client_cert_fn = "%s/passport-rp.pem" % self.certFolder
        self.passport_rp_client_jks_pass = 'secret'
        self.passport_resource_id = None
        
        self.oxauth_legacyIdTokenClaims = 'false'
        self.oxauth_openidScopeBackwardCompatibility =  'false'
        self.enableRadiusScripts = 'false'
        self.gluu_radius_client_id = None
        self.gluu_ro_pw = None
        self.gluu_ro_encoded_pw = None
        self.ox_radius_client_id = None
        self.oxRadiusClientIpAddress = None
        self.oxRadiusClientName = None
        self.oxRadiusClientSecret = None
        self.radius_dir = os.path.join(self.gluuOptFolder, 'radius')

        #definitions for couchbase
        self.couchebaseInstallDir = '/opt/couchbase/'
        self.couchebaseClusterAdmin = 'admin'
        self.isCouchbaseUserAdmin = False
        self.couchbasePackageFolder = os.path.join(self.distFolder, 'couchbase')
        self.couchbaseTrustStoreFn = "%s/couchbase.pkcs12" % self.certFolder
        self.couchbaseTrustStorePass = 'newsecret'
        self.n1qlOutputFolder = os.path.join(self.outputFolder,'n1ql')
        self.couchbaseIndexJson = '%s/static/couchbase/index.json' % self.install_dir
        self.couchbaseInitScript = os.path.join(self.install_dir, 'static/system/initd/couchbase-server')
        self.couchebaseCert = os.path.join(self.certFolder, 'couchbase.pem')
        self.gluuCouchebaseProperties = os.path.join(self.configFolder, 'gluu-couchbase.properties')
        self.couchbaseBuckets = []
        self.cbm = None
        self.cb_query_node = 0
        self.cb_bucket_roles = ['bucket_admin', 'query_delete', 'query_select', 
                            'query_update', 'query_insert',
                            'query_manage_index']
        self.post_messages = []
        self.couchbase_bucket_prefix = 'gluu'

        #oxd install options
        self.installOxd = False
        self.oxd_package = ''
        self.oxd_use_gluu_storage = False

        #casa install options
        self.installCasa = False
        self.twilio_version = '7.17.0'
        self.jsmmp_version = '2.3.7'
        self.oxd_server_https = ''
        self.ldif_casa = os.path.join(self.outputFolder, 'casa.ldif')

        self.ldif_files = [self.ldif_base,
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
                           self.ldif_scim_clients,
                           self.ldif_idp,
                           self.lidf_oxtrust_api,
                           self.ldif_oxtrust_api_clients,
                           self.ldif_casa,
                           self.ldif_fido2,
                           ]


        self.ce_templates = {self.oxauth_config_json: False,
                             self.gluu_python_readme: True,
                             self.oxtrust_config_json: False,
                             self.oxtrust_cache_refresh_json: False,
                             self.oxtrust_import_person_json: False,
                             self.oxidp_config_json: False,
                             self.ox_ldap_properties: True,
                             self.oxauth_static_conf_json: False,
                             self.oxTrust_log_rotation_configuration: True,
                             self.ldap_setup_properties: False,
                             self.apache2_conf: False,
                             self.apache2_ssl_conf: False,
                             self.apache2_24_conf: False,
                             self.apache2_ssl_24_conf: False,
                             self.etc_hostname: False,
                             self.ldif_base: False,
                             self.ldif_attributes: False,
                             self.ldif_scopes: False,
                             self.ldif_clients: False,
                             self.ldif_people: False,
                             self.ldif_groups: False,
                             self.ldif_scripts: False,
                             self.ldif_scim: False,
                             self.ldif_scim_clients: False,
                             self.ldif_idp: False,
                             self.network: False,
                             self.ldif_scripts_casa: False,
                             self.lidf_oxtrust_api: False,
                             self.ldif_oxtrust_api_clients: False,
                             self.gluu_properties_fn: True,
                             self.data_source_properties: False,
                             self.ldif_casa: False,
                             self.fido2_dynamic_conf_json: False,
                             self.fido2_static_conf_json: False,
                             }

        self.service_requirements = {
                        'opendj': ['', 70],
                        'oxauth': ['opendj', 72],
                        'fido2': ['opendj', 73],
                        'identity': ['opendj oxauth', 74],
                        'scim': ['opendj oxauth', 75],
                        'idp': ['opendj oxauth', 76],
                        'casa': ['opendj oxauth', 78],
                        'oxd-server': ['opendj oxauth', 80],
                        'passport': ['opendj oxauth', 82],
                        'oxauth-rp': ['opendj oxauth', 84],
                        'gluu-radius': ['opendj oxauth', 86],
                        }

        self.install_time_ldap = None
        
        
        self.couchbaseBucketDict = OrderedDict((   
                        ('default', { 'ldif':[
                                            self.ldif_base, 
                                            self.ldif_attributes,
                                            self.ldif_scopes,
                                            self.ldif_scripts,
                                            self.ldif_configuration,
                                            self.ldif_scim,
                                            self.ldif_fido2,
                                            self.ldif_idp,
                                            self.lidf_oxtrust_api,
                                            self.ldif_clients,
                                            self.ldif_oxtrust_api_clients,
                                            self.ldif_scim_clients,
                                            self.ldif_metric,
                                            ],
                                      'memory_allocation': 100,
                                      'mapping': '',
                                      'document_key_prefix': []
                                    }),

                        ('user',     {   'ldif': [
                                            self.ldif_people, 
                                            self.ldif_groups
                                            ],
                                        'memory_allocation': 300,
                                        'mapping': 'people, groups, authorizations',
                                        'document_key_prefix': ['groups_', 'people_', 'authorizations_'],
                                    }),

                        ('cache',    {   'ldif': [],
                                        'memory_allocation': 300,
                                        'mapping': 'cache',
                                        'document_key_prefix': ['cache_'],
                                    }),

                        ('site',     {   'ldif': [self.ldif_site],
                                        'memory_allocation': 100,
                                        'mapping': 'cache-refresh',
                                        'document_key_prefix': ['site_', 'cache-refresh_'],
                                        
                                    }),

                        ('token',   { 'ldif': [],
                                      'memory_allocation': 300,
                                      'mapping': 'tokens, sessions',
                                      'document_key_prefix': ['tokens_'],
                                    }),

                    ))

        self.mappingLocations = { group: 'ldap' for group in self.couchbaseBucketDict }  #default locations are OpenDJ
        self.non_setup_properties = {
            'oxauth_client_jar_fn': os.path.join(self.distGluuFolder, 'oxauth-client-jar-with-dependencies.jar')
                }

        self.logIt("Determining oxd server package")
        oxd_package_list = glob.glob(os.path.join(self.distGluuFolder, 'oxd-server*.tgz'))

        if oxd_package_list:
            self.oxd_package = max(oxd_package_list)

        self.logIt("oxd server package was determined as " + self.oxd_package)


    def __repr__(self):
        try:
            txt = 'hostname'.ljust(30) + self.hostname.rjust(35) + "\n"
            txt += 'orgName'.ljust(30) + self.orgName.rjust(35) + "\n"
            txt += 'os'.ljust(30) + self.os_type.rjust(35) + "\n"
            txt += 'city'.ljust(30) + self.city.rjust(35) + "\n"
            txt += 'state'.ljust(30) + self.state.rjust(35) + "\n"
            txt += 'countryCode'.ljust(30) + self.countryCode.rjust(35) + "\n"
            txt += 'Applications max ram'.ljust(30) + str(self.application_max_ram).rjust(35) + "\n"
            txt += 'Install oxAuth'.ljust(30) + repr(self.installOxAuth).rjust(35) + "\n"
            txt += 'Install oxTrust'.ljust(30) + repr(self.installOxTrust).rjust(35) + "\n"

            bc = []
            if self.wrends_install:
                t_ = 'wrends'
                if self.wrends_install == REMOTE:
                    t_ += '[R]'
                bc.append(t_)
            if self.cb_install:
                t_ = 'couchbase'
                if self.cb_install == REMOTE:
                    t_ += '[R]'
                bc.append(t_)

            if bc:
                bct = ', '.join(bc)
                txt += 'Backends'.ljust(30) + bct.rjust(35) + "\n"

            txt += 'Java Type'.ljust(30) + self.java_type.rjust(35) + "\n"
            txt += 'Install Apache 2 web server'.ljust(30) + repr(self.installHttpd).rjust(35) + "\n"
            txt += 'Install Fido2 Server'.ljust(30) + repr(self.installFido2).rjust(35) + "\n"
            txt += 'Install Scim Server'.ljust(30) + repr(self.installScimServer).rjust(35) + "\n"
            txt += 'Install Shibboleth SAML IDP'.ljust(30) + repr(self.installSaml).rjust(35) + "\n"
            txt += 'Install oxAuth RP'.ljust(30) + repr(self.installOxAuthRP).rjust(35) + "\n"
            txt += 'Install Passport '.ljust(30) + repr(self.installPassport).rjust(35) + "\n"
            txt += 'Install Casa '.ljust(30) + repr(self.installCasa).rjust(35) + "\n"
            txt += 'Install Oxd '.ljust(30) + repr(self.installOxd).rjust(35) + "\n"
            txt += 'Install Gluu Radius '.ljust(30) + repr(self.installGluuRadius).rjust(35) + "\n"

            return txt
        except:
            s = ""
            for key in list(self.__dict__.keys()):
                val = self.__dict__[key]
                s = s + "%s\n%s\n%s\n\n" % (key, "-" * len(key), val)
            return s

    def initialize(self):
        self.install_time_ldap = time.strftime('%Y%m%d%H%M%SZ', time.gmtime(time.time()))
        if not os.path.exists(self.distFolder):
            print("Please ensure that you are running this script inside Gluu container.")
            sys.exit(1)

        #Download oxauth-client-jar-with-dependencies
        if not os.path.exists(self.non_setup_properties['oxauth_client_jar_fn']):
            oxauth_client_jar_url = 'https://ox.gluu.org/maven/org/gluu/oxauth-client/{0}/oxauth-client-{0}-jar-with-dependencies.jar'.format(self.oxVersion)
            self.logIt("Downloading {}".format(os.path.basename(oxauth_client_jar_url)))
            self.run(['wget', '-nv', oxauth_client_jar_url, '-O', self.non_setup_properties['oxauth_client_jar_fn']])

        self.logIt("Determining key generator path")
        oxauth_client_jar_zf = zipfile.ZipFile(self.non_setup_properties['oxauth_client_jar_fn'])

        for f in oxauth_client_jar_zf.namelist():
            if os.path.basename(f) == 'KeyGenerator.class':
                p, e = os.path.splitext(f)
                self.non_setup_properties['key_gen_path'] = p.replace(os.path.sep, '.')
            elif os.path.basename(f) == 'KeyExporter.class':
                p, e = os.path.splitext(f)
                self.non_setup_properties['key_export_path'] = p.replace(os.path.sep, '.')

        if (not 'key_gen_path' in self.non_setup_properties) or (not 'key_export_path' in self.non_setup_properties):
            self.logIt("Can't determine key generator and/or key exporter path form {}".format(self.non_setup_properties['oxauth_client_jar_fn']), True, True)

    def get_ssl_subject(self, ssl_fn):
        retDict = {}
        cmd = 'openssl x509  -noout -subject -nameopt RFC2253 -in {}'.format(ssl_fn)
        s = self.run(cmd, shell=True)
        s = s.strip() + ','

        for k in ('emailAddress', 'CN', 'O', 'L', 'ST', 'C'):
            rex = re.search('{}=(.*?),'.format(k), s)
            retDict[k] = rex.groups()[0] if rex else ''

        return retDict

    def set_ownership(self):
        self.logIt("Changing ownership")
        realCertFolder = os.path.realpath(self.certFolder)
        realConfigFolder = os.path.realpath(self.configFolder)
        realOptPythonFolderFolder = os.path.realpath(self.gluuOptPythonFolder)

        self.run([self.cmd_chown, '-R', 'root:gluu', realCertFolder])
        self.run([self.cmd_chown, '-R', 'root:gluu', realConfigFolder])
        self.run([self.cmd_chown, '-R', 'root:gluu', realOptPythonFolderFolder])
        self.run([self.cmd_chown, '-R', 'root:gluu', self.oxBaseDataFolder])

        # Set right permissions
        self.run([self.cmd_chmod, '-R', '440', realCertFolder])
        self.run([self.cmd_chmod, 'a+X', realCertFolder])

        if self.installOxAuth:
            self.run([self.cmd_chown, '-R', 'jetty:jetty', self.oxauth_openid_jks_fn])
            self.run([self.cmd_chmod, '660', self.oxauth_openid_jks_fn])

        if self.installSaml:
            realIdp3Folder = os.path.realpath(self.idp3Folder)
            self.run([self.cmd_chown, '-R', 'jetty:jetty', realIdp3Folder])

        for fn in (
                os.path.join(self.jetty_base, 'oxauth/webapps/oxauth.xml'),
                os.path.join(self.jetty_base, 'identity/webapps/identity.xml'),
                ):
            if os.path.exists(fn):
                cmd = [self.cmd_chown, 'jetty:jetty', fn]
                self.run(cmd)

        gluu_radius_jks_fn = os.path.join(self.certFolder, 'gluu-radius.jks')
        gluu_radius_pem_fn = os.path.join(self.certFolder, 'gluu-radius.private-key.pem')
        for fn in (gluu_radius_jks_fn, gluu_radius_pem_fn):
            if os.path.exists(fn):
                self.run([self.cmd_chown, 'radius:gluu', fn])
                self.run([self.cmd_chmod, '660', fn])

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

    def detect_ip(self):
        detectedIP = None

        try:
            testSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            detectedIP = [(testSocket.connect(('8.8.8.8', 80)),
                           testSocket.getsockname()[0],
                           testSocket.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]
        except:
            self.logIt("No detected IP address", True)
            self.logIt(traceback.format_exc(), True)

        return detectedIP

    def get_ip(self):
        testIP = None
        detectedIP = self.ip if self.ip else self.detect_ip()

        if self.noPrompt and detectedIP:
            return detectedIP

        while not testIP:
            if detectedIP:
                testIP = self.getPrompt("Enter IP Address", detectedIP)
            else:
                testIP = self.getPrompt("Enter IP Address")
            if not self.isIP(testIP):
                testIP = None
                print('ERROR: The IP Address is invalid. Try again\n')

        return testIP

    def check_installed(self):
        return os.path.exists(self.configFolder)

    def check_properties(self):
        self.logIt('Checking properties')
        while not self.hostname:
            testhost = input('Hostname of this server: ').strip()
            if len(testhost.split('.')) >= 3:
                self.hostname = testhost
            else:
                print('The hostname has to be at least three domain components. Try again\n')
        while not self.ip:
            self.ip = self.get_ip()
        while not self.orgName:
            self.orgName = input('Organization Name: ').strip()
        while not self.countryCode:
            testCode = input('2 Character Country Code: ').strip()
            if len(testCode) == 2:
                self.countryCode = testCode
            else:
                print('Country code should only be two characters. Try again\n')
        while not self.city:
            self.city = input('City: ').strip()
        while not self.state:
            self.state = input('State or Province: ').strip()
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
        if not self.opendj_p12_pass:
            self.opendj_p12_pass = self.getPW()
        if not self.passportSpKeyPass:
            self.passportSpKeyPass = self.getPW()
            self.passportSpJksPass = self.getPW()
        if not self.encode_salt:
            self.encode_salt= self.getPW() + self.getPW()
        if not self.oxauth_client_id:
            self.oxauth_client_id = '1001.'+ str(uuid.uuid4())
        if not self.idp_client_id:
            self.idp_client_id = '1101.'+ str(uuid.uuid4())
        if not self.scim_rs_client_id:
            self.scim_rs_client_id = '1201.' + str(uuid.uuid4())
        if not self.scim_rp_client_id:
            self.scim_rp_client_id = '1202.' + str(uuid.uuid4())
        if not self.scim_resource_oxid:
            self.scim_resource_oxid = '1203.' + str(uuid.uuid4())
        if not self.oxtrust_resource_server_client_id:
            self.oxtrust_resource_server_client_id = '1401.'  + str(uuid.uuid4())
        if not self.oxtrust_requesting_party_client_id:
            self.oxtrust_requesting_party_client_id = '1402.'  + str(uuid.uuid4())
        if not self.oxtrust_resource_id:
            self.oxtrust_resource_id = '1403.'  + str(uuid.uuid4())
        if not self.admin_inum:
            self.admin_inum = str(uuid.uuid4())

        if not self.application_max_ram:
            self.application_max_ram = int(current_mem_size * .83 * 1000) # 83% of physical memory

        if not self.couchbaseShibUserPassword:
            self.couchbaseShibUserPassword = self.getPW()

        if self.installCasa:
            if not self.ldif_casa in self.couchbaseBucketDict['default']['ldif']:
                self.couchbaseBucketDict['default']['ldif'].append(self.ldif_casa)
            if not self.ldif_scripts_casa in self.couchbaseBucketDict['default']['ldif']:
                self.couchbaseBucketDict['default']['ldif'].append(self.ldif_scripts_casa)

        if self.oxd_server_https:
            self.templateRenderingDict['oxd_hostname'], self.templateRenderingDict['oxd_port'] = self.parse_url(self.oxd_server_https)
            if not self.templateRenderingDict['oxd_port']: 
                self.templateRenderingDict['oxd_port'] = 8443
        else:
            self.templateRenderingDict['oxd_hostname'] = self.hostname


    def enable_service_at_start(self, serviceName, startSequence=None, stopSequence=None, action='enable'):
        # Enable service autoload on Gluu-Server startup
        if self.os_type in ['centos', 'fedora', 'red']:
            if self.os_initdaemon == 'systemd':
                self.run([self.systemctl, action, serviceName])
            else:
                self.run(["/sbin/chkconfig", serviceName, "on" if action=='enable' else 'off'])
                
        elif self.os_type+self.os_version in ('ubuntu20', 'ubuntu18','debian9','debian10'):
            self.run([self.systemctl, action, serviceName])
                
        elif self.os_type in ['ubuntu', 'debian']:
            cmd_list = ["/usr/sbin/update-rc.d", serviceName, 'defaults']
            
            if startSequence and stopSequence:
                cmd_list.append(str(startSequence))
                cmd_list.append(str(stopSequence))

            self.run(cmd_list)


    # = File system  =================================================================

    def readFile(self, inFilePath, logError=True, rmode='r'):
        inFilePathText = None

        try:
            f = open(inFilePath, rmode)
            inFilePathText = f.read()
            f.close()
        except:
            if logError:
                self.logIt("Error reading %s" % inFilePathText, True)
                self.logIt(traceback.format_exc(), True)

        return inFilePathText

    def writeFile(self, outFilePath, text):
        self.logIt("Writing file %s" % outFilePath)
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
        textLines = text.splitlines()

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
        fn = os.path.join(self.install_dir, 'os-changes.log')
        with open(fn,'a') as W:
            W.write(text+"\n")


    def backupFile(self, inFile, destFolder=None):

        if destFolder:
            if os.path.isfile(destFolder):
                destFile = destFolder
            else:
                inFolder, inName = os.path.split(inFile)
                destFile = os.path.join(destFolder, inName)
        else:
            destFile = inFile

        bc = 1
        while True:
            backupFile = destFile+'.gluu-{0}-{1}~'.format(self.currentGluuVersion, bc)
            if not os.path.exists(backupFile):
                break
            bc += 1

        if os.path.exists(destFile):
            self.run(['cp', '-f', destFile, backupFile])

        if not destFile.startswith('/opt'):
            self.logOSChanges("File %s was backed up as %s" % (destFile, backupFile))

    def copyFile(self, inFile, destFolder):
        self.backupFile(inFile, destFolder)
        self.logIt("Copying file {} to {}".format(inFile, destFolder))
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
                os.makedirs(name, 0o700)
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

    def logIt(self, msg, errorLog=False, fatal=False):
        if errorLog:
            f = open(self.logError, 'a')
            f.write('%s %s\n' % (time.strftime('%X %x'), msg))
            f.close()
        f = open(self.log, 'a')
        f.write('%s %s\n' % (time.strftime('%X %x'), msg))
        f.close()

        if fatal:
            print("FATAL:", errorLog)
            sys.exit(1)


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

    def decrypt_properties(self, fn, passwd):
        out_file = fn[:-4] + '.' + uuid.uuid4().hex[:8] + '-DEC~'
        cmd = ['openssl', 'enc', '-d', '-aes-256-cbc', '-in',  fn, '-out', out_file, '-k', passwd]
        self.logIt('Running: ' + ' '.join(cmd))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, err = p.communicate()
        
        if b'bad decrypt' in err:
            print("Can't decrypt {} with password {}\n Exiting ...".format(fn, passwd))
            self.run(['rm', '-f', out_file])
            sys.exit(False)

        return out_file

    def load_properties(self, fn, no_update=[]):
        self.logIt('Loading Properties %s' % fn)

        no_update += ['jre_version', 'node_version', 'jetty_version', 'jython_version', 'jreDestinationPath']

        cb_install = False
        map_db = []

        if fn.endswith('.enc'):
            if not self.properties_password:
                print("setup.properties password was not supplied. Please run with argument -properties-password")
                sys.exit(False)

            fn = self.decrypt_properties(fn, self.properties_password)

        try:
            p = gluu_utils.read_properties_file(fn)
        except:
            self.logIt("Error loading properties", True)
            self.logIt(traceback.format_exc(), True)

        if p.get('ldap_type') == 'openldap':
            self.logIt("ldap_type in setup.properties was changed from openldap to opendj")
            p['ldap_type'] = 'opendj'

        properties_list = list(p.keys())

        for prop in properties_list:
            if prop in no_update:
                continue
            try:
                self.__dict__[prop] = p[prop]
                if prop == 'mappingLocations':
                    mappingLocations = json.loads(p[prop])
                    self.__dict__[prop] = mappingLocations
                    for l in mappingLocations:
                        if not mappingLocations[l] in map_db:
                            map_db.append(mappingLocations[l])
                            
                if p[prop] == 'True':
                    self.__dict__[prop] = True
                elif p[prop] == 'False':
                    self.__dict__[prop] = False
            except:
                self.logIt("Error loading property %s" % prop)
                self.logIt(traceback.format_exc(), True)

        if fn.endswith('-DEC~'):
            self.run(['rm', '-f', fn])

        if not 'oxtrust_admin_password' in properties_list:
            self.oxtrust_admin_password = p['ldapPass']
            
        if p.get('ldap_hostname') != 'localhost':
            if p.get('remoteLdap','').lower() == 'true':
                self.wrends_install = REMOTE
            elif p.get('installLdap','').lower() == 'true':
                self.wrends_install = LOCAL
            elif p.get('wrends_install'):
                self.wrends_install = p['wrends_install']   
            else:
                self.wrends_install = NONE

        if map_db and not 'ldap' in map_db:
            self.wrends_install = NONE

        if 'couchbase' in map_db:
            if 'remoteCouchbase' in properties_list and p.get('remoteCouchbase','').lower() == 'true':
                self.cb_install = REMOTE
            elif p.get('cb_install'):
                self.cb_install = p['cb_install']
            elif 'persistence_type' in properties_list and p.get('persistence_type') in ('couchbase', 'hybrid'):
                self.cb_install = LOCAL
            else:
                self.cb_install = NONE

        if self.cb_install == LOCAL:
            available_backends = self.getBackendTypes()
            if not 'couchbase' in available_backends:
                print("Couchbase package is not available exiting.")
                sys.exit(1)


        if (not 'cb_password' in properties_list) and self.cb_install:
            self.cb_password = p.get('ldapPass')

        if self.cb_install == REMOTE:
            cbm_ = CBM(self.couchbase_hostname, self.couchebaseClusterAdmin, self.cb_password)
            if not cbm_.test_connection().ok:
                print("Can't connect to remote Couchbase Server with credentials found in setup.properties.")
                sys.exit(1)

        if self.wrends_install == REMOTE:
            conn_check = self.check_remote_ldap(self.ldap_hostname, self.ldap_binddn, self.ldapPass)
            if not conn_check['result']:
                print("Can't connect to remote LDAP Server with credentials found in setup.properties.")
                sys.exit(1)

        for si, se in ( 
                        ('installPassport', 'gluuPassportEnabled'),
                        ('installGluuRadius', 'gluuRadiusEnabled'),
                        ('installSaml', 'gluuSamlEnabled'),
                        ('installScimServer', 'gluuScimEnabled'),
                        ):
            if getattr(self, si):
                setattr(self, se, 'true')

        if not 'oxtrust_admin_password' in p:
            p['oxtrust_admin_password'] = p['ldapPass']


        return p

    def obscure(self, data=""):
        engine = triple_des(self.encode_salt, ECB, pad=None, padmode=PAD_PKCS5)
        data = data.encode('utf-8')
        en_data = engine.encrypt(data)
        encoded_pw = base64.b64encode(en_data)
        return encoded_pw.decode('utf-8')

    # ================================================================================

    def configure_httpd(self):
        # Detect apache service name
        apache_service_name = self.get_apache_service_name()

        self.run_service_command(apache_service_name, 'stop')

        # CentOS 7.* + systemd + apache 2.4
        if self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd' and self.apache_version == "2.4":
            self.copyFile(self.apache2_24_conf, '/etc/httpd/conf/httpd.conf')
            self.copyFile(self.apache2_ssl_24_conf, '/etc/httpd/conf.d/https_gluu.conf')

        if self.os_type in ['red', 'fedora'] and self.os_initdaemon == 'init':
            self.copyFile(self.apache2_conf, '/etc/httpd/conf/httpd.conf')
            self.copyFile(self.apache2_ssl_conf, '/etc/httpd/conf.d/https_gluu.conf')
        if self.os_type in ['debian', 'ubuntu']:
            self.copyFile(self.apache2_ssl_conf, '/etc/apache2/sites-available/https_gluu.conf')
            self.run([self.cmd_ln, '-s', '/etc/apache2/sites-available/https_gluu.conf',
                      '/etc/apache2/sites-enabled/https_gluu.conf'])

        self.writeFile('/var/www/html/index.html', 'OK')

        if self.os_type in ['centos', 'red', 'fedora']:
            icons_conf_fn = '/etc/httpd/conf.d/autoindex.conf'
        else:
            icons_conf_fn = '/etc/apache2/mods-available/alias.conf'

        with open(icons_conf_fn[:]) as f:
            icons_conf = f.readlines()

        for i, l in enumerate(icons_conf[:]):
            if l.strip().startswith('Alias') and ('/icons/' in l.strip().split()):
                icons_conf[i] =  l.replace('Alias', '#Alias')

        self.writeFile(icons_conf_fn, ''.join(icons_conf))

        error_templates = glob.glob(os.path.join(self.templateFolder,'apache/*'))

        for tmp_fn in error_templates:
            self.copyFile(tmp_fn, '/var/www/html')

        self.run_service_command(apache_service_name, 'start')

        # we only need these modules
        mods_enabled = ['env', 'proxy_http', 'access_compat', 'alias', 'authn_core', 'authz_core', 'authz_host', 'headers', 'mime', 'mpm_event', 'proxy', 'proxy_ajp', 'security2', 'reqtimeout', 'setenvif', 'socache_shmcb', 'ssl', 'unique_id']

        if self.os_type in ['centos', 'red', 'fedora']:

            for mod_load_fn in glob.glob('/etc/httpd/conf.modules.d/*'):

                with open(mod_load_fn) as f:
                    mod_load_content = f.readlines()

                modified = False
                
                for i, l in enumerate(mod_load_content[:]):
                    ls = l.strip()
                    
                    if ls and not ls.startswith('#'):
                        lsl = ls.split('/')
                        module =  lsl[-1][4:-3]
                        
                        if not module in mods_enabled:
                            mod_load_content[i] = l.replace('LoadModule', '#LoadModule')
                            modified = True

                if modified:
                    self.writeFile(mod_load_fn, ''.join(mod_load_content))
        else:

            for mod_load_fn in glob.glob('/etc/apache2/mods-enabled/*'):
                mod_load_base_name = os.path.basename(mod_load_fn)
                f_name, f_ext = os.path.splitext(mod_load_base_name)

                if not f_name in mods_enabled:
                    self.run(['unlink', mod_load_fn])

        self.enable_service_at_start(apache_service_name)

    def copy_output(self):
        self.logIt("Copying rendered templates to final destination")

        for dest_fn in list(self.ce_templates.keys()):
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
            
        if self.installFido2:
            # Fido2 authenticator certs
            self.copyFile("%s/static/auth/fido2//authenticator_cert/yubico-u2f-ca-cert.crt" % self.install_dir, "%s/%s" % (self.fido2ConfigFolder, '/authenticator_cert'))
            self.copyFile("%s/static/auth/fido2//authenticator_cert/HyperFIDO_CA_Cert_V1.pem" % self.install_dir, "%s/%s" % (self.fido2ConfigFolder, '/authenticator_cert'))
            self.copyFile("%s/static/auth/fido2//authenticator_cert/HyperFIDO_CA_Cert_V2.pem" % self.install_dir, "%s/%s" % (self.fido2ConfigFolder, '/authenticator_cert'))

            # Fido2 MDS TOC cert
            self.copyFile("%s/static/auth/fido2//mds_toc_cert/metadata-root-ca.cer" % self.install_dir, "%s/%s" % (self.fido2ConfigFolder, '/mds/cert'))

    # keep this for backward compatibility
    def detect_os_type(self):
        return os_type, os_version


    def detect_initd(self):
        return open(os.path.join('/proc/1/status'), 'r').read().split()[1]

    def determineApacheVersion(self, apache_cmd):
        cmd = "/usr/sbin/%s -v | egrep '^Server version'" % apache_cmd
        output = self.run(cmd, shell=True)
        apache_version = output.split(' ')[2].split('/')[1]

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

    def installJRE(self):

        jre_arch_list = glob.glob(os.path.join(self.distAppFolder, 'amazon-corretto-*.tar.gz'))

        if not jre_arch_list:
            self.logIt("JRE packgage not found in {}. Will download jdk".format(self.distAppFolder))
            self.java_type = 'jdk'
        else:
            self.java_type = 'jre'

        if self.java_type != 'jre':
            self.logIt("Downloading " + self.open_jdk_archive_link)
            jdk_fn = os.path.basename(self.open_jdk_archive_link)
            jreArchive = os.path.join(self.distAppFolder, jdk_fn)
            self.run(['wget', '-nv', self.open_jdk_archive_link, '-O', jreArchive])
        else:
            jreArchive = max(jre_arch_list)


        self.logIt("Installing server JRE {} ...".format(os.path.basename(jreArchive)))

        try:
            self.logIt("Extracting %s into /opt/" % os.path.basename(jreArchive))
            self.run(['tar', '-xzf', jreArchive, '-C', '/opt/', '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
        except:
            self.logIt("Error encountered while extracting archive %s" % jreArchive)
            self.logIt(traceback.format_exc(), True)

        if self.java_type == 'jdk':
            jreDestinationPath = max(glob.glob('/opt/jdk-11*'))
        else:
            jreDestinationPath = max(glob.glob('/opt/amazon-corretto-*'))

        self.run([self.cmd_ln, '-sf', jreDestinationPath, self.jre_home])
        self.run([self.cmd_chmod, '-R', "755", "%s/bin/" % jreDestinationPath])
        self.run([self.cmd_chown, '-R', 'root:root', jreDestinationPath])
        self.run([self.cmd_chown, '-h', 'root:root', self.jre_home])
        

        if not os.path.exists('/opt/jre/jre'):
            self.run([self.cmd_mkdir, '-p', '/opt/jre/jre'])
            self.run([self.cmd_ln, '-s', '/opt/jre/lib', '/opt/jre/jre/lib'])

        if self.java_type == 'jre':
            for jsfn in Path('/opt/jre').rglob('java.security'):
                self.run(['sed', '-i', '/^#crypto.policy=unlimited/s/^#//', jsfn._str])

    def extractOpenDJ(self):        

        openDJArchive = max(glob.glob(os.path.join(self.distFolder, 'app/opendj-server-*4*.zip')))

        try:
            self.logIt("Unzipping %s in /opt/" % openDJArchive)
            self.run(['unzip', '-n', '-q', '%s' % (openDJArchive), '-d', '/opt/' ])
        except:
            self.logIt("Error encountered while doing unzip %s -d /opt/" % (openDJArchive))
            self.logIt(traceback.format_exc(), True)

        realLdapBaseFolder = os.path.realpath(self.ldapBaseFolder)
        self.run([self.cmd_chown, '-R', 'ldap:ldap', realLdapBaseFolder])

        if self.wrends_install == REMOTE:
            self.run(['ln', '-s', '/opt/opendj/template/config/', '/opt/opendj/config'])

    def installJetty(self):
        self.logIt("Installing jetty %s...")

        jetty_archive_list = glob.glob(os.path.join(self.distAppFolder, 'jetty-distribution-*.tar.gz'))

        if not jetty_archive_list:
            self.logIt("Jetty archive not found in {}. Exiting...".format(self.distAppFolder), True, True)

        jettyArchive = max(jetty_archive_list)

        jettyArchive_fn = os.path.basename(jettyArchive)
        jetty_regex = re.search('jetty-distribution-(\d*\.\d*)', jettyArchive_fn)
        
        if not jetty_regex:
            self.logIt("Can't determine Jetty version", True, True)

        jetty_dist = '/opt/jetty-' + jetty_regex.groups()[0]
        self.templateRenderingDict['jetty_dist'] = jetty_dist
        jettyTemp = os.path.join(jetty_dist, 'temp')
        self.run([self.cmd_mkdir, '-p', jettyTemp])
        self.run([self.cmd_chown, '-R', 'jetty:jetty', jettyTemp])

        try:
            self.logIt("Extracting %s into /opt/jetty" % jettyArchive)
            self.run(['tar', '-xzf', jettyArchive, '-C', jetty_dist, '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
        except:
            self.logIt("Error encountered while extracting archive %s" % jettyArchive)
            self.logIt(traceback.format_exc(), True)


        jettyDestinationPath = max(glob.glob(os.path.join(jetty_dist, 'jetty-distribution-*')))

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

        self.run(['rm', '-rf', '/opt/jetty/bin/jetty.sh'])
        self.copyFile("%s/system/initd/jetty.sh" % self.staticFolder, "%s/bin/jetty.sh" % self.jetty_home)
        self.run([self.cmd_chown, '-R', 'jetty:jetty', "%s/bin/jetty.sh" % self.jetty_home])
        self.run([self.cmd_chmod, '-R', '755', "%s/bin/jetty.sh" % self.jetty_home])

    def installNode(self):
        self.logIt("Installing node %s..." )

        node_archieve_list = glob.glob(os.path.join(self.distAppFolder, 'node-*-linux-x64.tar.xz'))

        if not node_archieve_list:
            self.logIt("Can't find node archive", True, True)

        nodeArchive = max(node_archieve_list)

        try:
            self.logIt("Extracting %s into /opt" % nodeArchive)
            self.run(['tar', '-xJf', nodeArchive, '-C', '/opt/', '--no-xattrs', '--no-same-owner', '--no-same-permissions'])
        except:
            self.logIt("Error encountered while extracting archive %s" % nodeArchive)
            self.logIt(traceback.format_exc(), True)

        nodeDestinationPath = max(glob.glob('/opt/node-*-linux-x64'))

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

        couchbase_mappings = self.getMappingType('couchbase')

        if self.persistence_type == 'couchbase' or 'default' in couchbase_mappings:
            changeTo = 'couchbase-server'

        if self.wrends_install == REMOTE or self.cb_install == REMOTE:
            changeTo = ''

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

        if (self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd') or (self.os_type+self.os_version in ('ubuntu20', 'ubuntu18','debian9','debian10')):
            service_init_script_fn = os.path.join(self.distFolder, 'scripts', serviceName)
        else:
            service_init_script_fn = os.path.join('/etc/init.d', serviceName)

        with open(service_init_script_fn, 'w') as W:
            W.write(''.join(initscript))

        self.run([self.cmd_chmod, '+x', service_init_script_fn])

    def installJettyService(self, serviceConfiguration, supportCustomizations=False, supportOnlyPageCustomizations=False):
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
            self.run([self.cmd_mkdir, '-p', "%s/custom/pages" % jettyServiceBase])

            if not supportOnlyPageCustomizations:
                self.run([self.cmd_mkdir, '-p', "%s/custom/i18n" % jettyServiceBase])
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
            self.logIt("Error rendering service '%s' defaults" % serviceName, True)
            self.logIt(traceback.format_exc(), True)

        jettyServiceConfiguration = '%s/jetty/%s' % (self.outputFolder, serviceName)
        self.copyFile(jettyServiceConfiguration, self.osDefault)
        self.run([self.cmd_chown, 'root:root', os.path.join(self.osDefault, serviceName)])

        # Render web eources file
        try:
            web_resources = '%s_web_resources.xml' % serviceName
            if os.path.exists('%s/jetty/%s' % (self.templateFolder, web_resources)):
                self.renderTemplateInOut(web_resources, '%s/jetty' % self.templateFolder, '%s/jetty' % self.outputFolder)
                self.copyFile('%s/jetty/%s' % (self.outputFolder, web_resources), "%s/%s/webapps" % (self.jetty_base, serviceName))
        except:
            self.logIt("Error rendering service '%s' web_resources.xml" % serviceName, True)
            self.logIt(traceback.format_exc(), True)

        # Render web context file
        try:
            web_context = '%s.xml' % serviceName
            if os.path.exists('%s/jetty/%s' % (self.templateFolder, web_context)):
                self.renderTemplateInOut(web_context, '%s/jetty' % self.templateFolder, '%s/jetty' % self.outputFolder)
                self.copyFile('%s/jetty/%s' % (self.outputFolder, web_context), "%s/%s/webapps" % (self.jetty_base, serviceName))
        except:
            self.logIt("Error rendering service '%s' context xml" % serviceName, True)
            self.logIt(traceback.format_exc(), True)

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

        # don't send header to server
        self.set_jetty_param(serviceName, 'jetty.httpConfig.sendServerVersion', 'false')

    def installNodeService(self, serviceName):
        self.logIt("Installing node service %s..." % serviceName)

        nodeServiceConfiguration = '%s/node/%s' % (self.outputFolder, serviceName)
        self.copyFile(nodeServiceConfiguration, self.osDefault)
        self.run([self.cmd_chown, 'root:root', os.path.join(self.osDefault, serviceName)])

        if serviceName == 'passport':
            initscript_fn = os.path.join(self.gluuOptSystemFolder, serviceName)
            self.fix_init_scripts(serviceName, initscript_fn)
        else:
            self.run([self.cmd_ln, '-sf', '%s/node' % self.gluuOptSystemFolder, '/etc/init.d/%s' % serviceName])

    def installJython(self):
        self.logIt("Installing Jython")

        jython_installer_list = glob.glob(os.path.join(self.distAppFolder, 'jython-installer-*'))

        if not jython_installer_list:
            self.logIt("Jython installer not found in. Exiting...", True, True)

        jython_installer = max(jython_installer_list)
        jython_version_regex = re.search('jython-installer-(.*)\.jar', jython_installer)
        
        if not jython_version_regex:
            self.logIt("Jython installer not found in. Exiting...", True, True)

        jython_version = jython_version_regex.groups()[0]

        try:
            self.run(['rm', '-rf', '/opt*-%s' % jython_version])
            self.run([self.cmd_java, '-jar', jython_installer, '-v', '-s', '-d', '/opt/jython-%s' % jython_version, '-t', 'standard', '-e', 'ensurepip'])
        except:
            self.logIt("Error installing jython-installer-%s.jar" % jython_version)
            self.logIt(traceback.format_exc(), True)

        self.run([self.cmd_ln, '-sf', '/opt/jython-%s' % jython_version, self.jython_home])
        self.run([self.cmd_chown, '-R', 'root:root', '/opt/jython-%s' % jython_version])
        self.run([self.cmd_chown, '-h', 'root:root', self.jython_home])

    def downloadWarFiles(self):
        if self.downloadWars:
            self.pbar.progress("download", "Downloading oxAuth war file")
            
            self.run(['/usr/bin/wget', self.oxauth_war, '--no-verbose', '--retry-connrefused', '--tries=10', '-O', '%s/oxauth.war' % self.distGluuFolder])
            self.pbar.progress("download", "Downloading oxTrust war file", False)
            self.run(['/usr/bin/wget', self.oxtrust_war, '--no-verbose', '--retry-connrefused', '--tries=10', '-O', '%s/identity.war' % self.distGluuFolder])

        if self.installOxAuthRP:
            # oxAuth RP is not part of CE package. We need to download it if needed
            distOxAuthRpPath = '%s/%s' % (self.distGluuFolder, "oxauth-rp.war")
            if not os.path.exists(distOxAuthRpPath):
                self.pbar.progress("download", "Downloading oxAuth RP war file", False)
                self.run(['/usr/bin/wget', self.oxauth_rp_war, '--no-verbose', '--retry-connrefused', '--tries=10', '-O', '%s/oxauth-rp.war' % self.distGluuFolder])

        if self.downloadWars and self.installSaml:
            
            self.pbar.progress("download", "Downloading Shibboleth IDP v3 war file", False)
            self.run(['/usr/bin/wget', self.idp3_war, '--no-verbose', '-c', '--retry-connrefused', '--tries=10', '-O', '%s/idp.war' % self.distGluuFolder])
            self.pbar.progress("download", "Downloading Shibboleth IDP v3 keygenerator", False)
            self.run(['/usr/bin/wget', self.idp3_cml_keygenerator, '--no-verbose', '-c', '--retry-connrefused', '--tries=10', '-O', self.distGluuFolder + '/idp3_cml_keygenerator.jar'])
            self.pbar.progress("download", "Downloading Shibboleth IDP v3 binary distributive file", False)
            self.run(['/usr/bin/wget', self.idp3_dist_jar, '--no-verbose', '-c', '--retry-connrefused', '--tries=10', '-O', self.distGluuFolder + '/shibboleth-idp.jar'])


    def encode_passwords(self):
        self.logIt("Encoding passwords")
        try:
            self.encoded_oxtrust_admin_password = self.ldap_encode(self.oxtrust_admin_password)
            self.encoded_shib_jks_pw = self.obscure(self.shibJksPass)
            if self.ldapPass:
                self.encoded_ox_ldap_pw = self.obscure(self.ldapPass)
            if self.cb_password:
                self.encoded_cb_password = self.obscure(self.cb_password)
            self.encoded_opendj_p12_pass = self.obscure(self.opendj_p12_pass)

            self.oxauthClient_pw = self.getPW()
            self.oxauthClient_encoded_pw = self.obscure(self.oxauthClient_pw)

            self.idpClient_pw = self.getPW()
            self.idpClient_encoded_pw = self.obscure(self.idpClient_pw)

            self.encoded_couchbaseTrustStorePass = self.obscure(self.couchbaseTrustStorePass)
        except:
            self.logIt("Error encoding passwords", True)
            self.logIt(traceback.format_exc(), True)

    def encode_test_passwords(self):
        self.logIt("Encoding test passwords")
        hostname = self.hostname.split('.')[0]
        try:
            self.templateRenderingDict['oxauthClient_2_pw'] = self.templateRenderingDict['oxauthClient_2_inum'] + '-' + hostname
            self.templateRenderingDict['oxauthClient_2_encoded_pw'] = self.obscure(self.templateRenderingDict['oxauthClient_2_pw'])

            self.templateRenderingDict['oxauthClient_3_pw'] =  self.templateRenderingDict['oxauthClient_3_inum'] + '-' + hostname
            self.templateRenderingDict['oxauthClient_3_encoded_pw'] = self.obscure(self.templateRenderingDict['oxauthClient_3_pw'])

            self.templateRenderingDict['oxauthClient_4_pw'] = self.templateRenderingDict['oxauthClient_4_inum'] + '-' + hostname
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

            self.gen_cert('passport-sp', self.passportSpKeyPass, 'ldap', self.ldap_hostname)

            self.gen_keystore('shibIDP',
                              self.shibJksFn,
                              self.shibJksPass,
                              '%s/shibIDP.key' % self.certFolder,
                              '%s/shibIDP.crt' % self.certFolder,
                              'jetty')

            # permissions
            self.run([self.cmd_chown, '-R', 'jetty:jetty', self.certFolder])
            self.run([self.cmd_chmod, '-R', '500', self.certFolder])

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

    def gen_openid_jwks_jks_keys(self, jks_path, jks_pwd, jks_create=True, key_expiration=None, dn_name=None, key_algs=None, enc_keys=None):
        self.logIt("Generating oxAuth OpenID Connect keys")

        if dn_name == None:
            dn_name = self.default_openid_jks_dn_name

        if key_algs == None:
            key_algs = self.default_key_algs

        if key_expiration == None:
            key_expiration = self.default_key_expiration

        if not enc_keys:
            enc_keys = key_algs

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

        cmd = " ".join([self.cmd_java,
                        "-Dlog4j.defaultInitOverride=true",
                        "-cp", self.non_setup_properties['oxauth_client_jar_fn'], 
                        self.non_setup_properties['key_gen_path'],
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

        output = self.run(args)
        if output:
            return output.splitlines()

    def export_openid_key(self, jks_path, jks_pwd, cert_alias, cert_path):
        self.logIt("Exporting oxAuth OpenID Connect keys")

        cmd = " ".join([self.cmd_java,
                        "-Dlog4j.defaultInitOverride=true",
                        "-cp",
                        self.non_setup_properties['oxauth_client_jar_fn'], 
                        self.non_setup_properties['key_export_path'],
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
        jwks = self.gen_openid_jwks_jks_keys(self.oxauth_openid_jks_fn, self.oxauth_openid_jks_pass, key_expiration=2, key_algs=sig_keys, enc_keys=enc_keys)
        self.write_openid_keys(self.oxauth_openid_jwks_fn, jwks)

    def generate_base64_string(self, lines, num_spaces):
        if not lines:
            return None

        plain_text = ''.join(lines)
        plain_b64encoded_text = base64.encodestring(plain_text.encode('utf-8')).decode('utf-8').strip()

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


    def generate_oxtrust_api_configuration(self):
        self.api_rs_client_jks_pass_encoded = self.obscure(self.api_rs_client_jks_pass)
        self.api_rs_client_jwks = self.gen_openid_jwks_jks_keys(self.api_rs_client_jks_fn, self.api_rs_client_jks_pass)
        self.templateRenderingDict['api_rs_client_base64_jwks'] = self.generate_base64_string(self.api_rs_client_jwks, 1)

        self.api_rp_client_jks_pass_encoded = self.obscure(self.api_rp_client_jks_pass)
        self.api_rp_client_jwks = self.gen_openid_jwks_jks_keys(self.api_rp_client_jks_fn, self.api_rp_client_jks_pass)
        self.templateRenderingDict['api_rp_client_base64_jwks'] = self.generate_base64_string(self.api_rp_client_jwks, 1)


    def getDefaultOption(self, val):
        return 'Yes' if val else 'No'
        

    def getPrompt(self, prompt, defaultValue=None):
        try:
            if defaultValue:
                user_input = input("%s [%s] : " % (prompt, defaultValue)).strip()
                if user_input == '':
                    return defaultValue
                else:
                    return user_input
            else:
                while True:
                    user_input = input("%s : " % prompt).strip()
                    if user_input != '':
                        return user_input

        except KeyboardInterrupt:
            sys.exit()
        except:
            return None

    def getPW(self, size=12, chars=string.ascii_uppercase + string.digits + string.ascii_lowercase, special=''):
        
        if not special:
            random_password = [random.choice(chars) for _ in range(size)]
        else:
            ndigit = random.randint(1, 3)
            nspecial = random.randint(1, 2)


            ncletter = random.randint(2, 5)
            nsletter = size - ndigit - nspecial - ncletter
            
            random_password = []
            
            for n, rc in ((ndigit, string.digits), (nspecial, special),
                        (ncletter, string.ascii_uppercase),
                        (nsletter, string.ascii_lowercase)):
            
                random_password += [random.choice(rc) for _ in range(n)]
            
        random.shuffle(random_password)
                
        return ''.join(random_password)

    def install_gluu_base(self):
        self.logIt("Installing Gluu base...")
        self.generate_oxtrust_api_configuration()
        self.generate_scim_configuration()

        self.ldapCertFn = self.opendj_cert_fn
        self.ldapTrustStoreFn = self.opendj_p12_fn
        self.encoded_ldapTrustStorePass = self.encoded_opendj_p12_pass

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



    def set_jetty_param(self, jettyServiceName, jetty_param, jetty_val):

        self.logIt("Seeting jetty parameter {0}={1} for service {2}".format(jetty_param, jetty_val, jettyServiceName))

        service_fn = os.path.join(self.jetty_base, jettyServiceName, 'start.ini')
        start_ini = self.readFile(service_fn)
        start_ini_list = start_ini.splitlines()
        param_ln = jetty_param + '=' + jetty_val

        for i, l in enumerate(start_ini_list[:]):
            if jetty_param in l and l[0]=='#':
                start_ini_list[i] = param_ln 
                break
            elif l.strip().startswith(jetty_param):
                start_ini_list[i] = param_ln
                break
        else:
            start_ini_list.append(param_ln)

        self.writeFile(service_fn, '\n'.join(start_ini_list))


    def install_oxauth(self):
        self.logIt("Copying oxauth.war into jetty webapps folder...")

        jettyServiceName = 'oxauth'
        self.installJettyService(self.jetty_app_configuration[jettyServiceName], True)

        jettyServiceWebapps = '%s/%s/webapps' % (self.jetty_base, jettyServiceName)
        self.copyFile('%s/oxauth.war' % self.distGluuFolder, jettyServiceWebapps)

    def install_oxtrust(self):
        self.logIt("Copying identity.war into jetty webapps folder...")

        jettyServiceName = 'identity'
        self.installJettyService(self.jetty_app_configuration[jettyServiceName], True)

        jettyServiceWebapps = '%s/%s/webapps' % (self.jetty_base, jettyServiceName)
        self.copyFile('%s/identity.war' % self.distGluuFolder, jettyServiceWebapps)

        # don't send header to server
        self.set_jetty_param(jettyServiceName, 'jetty.httpConfig.sendServerVersion', 'false')

    def install_scim_server(self):
        self.logIt("Copying scim.war into jetty webapps folder...")

        jettyServiceName = 'scim'
        self.installJettyService(self.jetty_app_configuration[jettyServiceName], True)

        jettyServiceWebapps = '%s/%s/webapps' % (self.jetty_base, jettyServiceName)
        self.copyFile('%s/scim.war' % self.distGluuFolder, jettyServiceWebapps)

        # don't send header to server
        self.set_jetty_param(jettyServiceName, 'jetty.httpConfig.sendServerVersion', 'false')

    def install_fido2(self):
        self.logIt("Copying fido.war into jetty webapps folder...")

        jettyServiceName = 'fido2'
        self.installJettyService(self.jetty_app_configuration[jettyServiceName], True)

        jettyServiceWebapps = '%s/%s/webapps' % (self.jetty_base, jettyServiceName)
        self.copyFile('%s/fido2.war' % self.distGluuFolder, jettyServiceWebapps)

    def install_saml(self):
        if self.installSaml:
            self.logIt("Install SAML Shibboleth IDP v3...")

            # Put latest SAML templates
            identityWar = 'identity.war'

            self.createDirs('%s/conf/shibboleth3' % self.gluuBaseFolder)
            self.createDirs('%s/identity/conf/shibboleth3/idp' % self.jetty_base)
            self.createDirs('%s/identity/conf/shibboleth3/sp' % self.jetty_base)

            # unpack IDP3 JAR with static configs
            self.run([self.cmd_jar, 'xf', self.distGluuFolder + '/shibboleth-idp.jar'], '/opt')
            self.removeDirs('/opt/META-INF')

            if self.mappingLocations['user'] == 'couchbase':
                self.templateRenderingDict['idp_attribute_resolver_ldap.search_filter'] = '(&(|(lower(uid)=$requestContext.principalName)(mail=$requestContext.principalName))(objectClass=gluuPerson))'

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

            self.installJettyService(self.jetty_app_configuration[jettyIdpServiceName], True, True)
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


            if self.persistence_type == 'couchbase':
                self.saml_couchbase_settings()
            elif self.persistence_type == 'hybrid':
                couchbase_mappings = self.getMappingType('couchbase')
                if 'user' in couchbase_mappings:
                    self.saml_couchbase_settings()


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


    def saml_couchbase_settings(self):
        # Add couchbase bean to global.xml
        couchbase_bean_xml_fn = '%s/couchbase/couchbase_bean.xml' % self.staticFolder
        global_xml_fn = '%s/global.xml' % self.idp3ConfFolder
        couchbase_bean_xml = self.readFile(couchbase_bean_xml_fn)
        global_xml = self.readFile(global_xml_fn)
        global_xml = global_xml.replace('</beans>', couchbase_bean_xml+'\n\n</beans>')
        self.writeFile(global_xml_fn, global_xml)

        # Add datasource.properties to idp.properties
        idp3_configuration_properties_fn = os.path.join(self.idp3ConfFolder, self.idp3_configuration_properties)

        with open(idp3_configuration_properties_fn) as r:
            idp3_properties = r.readlines()

        for i,l in enumerate(idp3_properties[:]):
            if l.strip().startswith('idp.additionalProperties'):
                idp3_properties[i] = l.strip() + ', /conf/datasource.properties\n'

        new_idp3_props = ''.join(idp3_properties)
        self.writeFile(idp3_configuration_properties_fn, new_idp3_props)

        data_source_properties = os.path.join(self.outputFolder, self.data_source_properties)

        self.copyFile(data_source_properties, self.idp3ConfFolder)


    def install_oxauth_rp(self):
        oxAuthRPWar = 'oxauth-rp.war'
        distOxAuthRpPath = '%s/%s' % (self.distGluuFolder, oxAuthRPWar)

        self.logIt("Copying oxauth-rp.war into jetty webapps folder...")

        jettyServiceName = 'oxauth-rp'
        self.installJettyService(self.jetty_app_configuration[jettyServiceName])

        jettyServiceWebapps = '%s/%s/webapps' % (self.jetty_base, jettyServiceName)
        self.copyFile('%s/oxauth-rp.war' % self.distGluuFolder, jettyServiceWebapps)

    def generate_passport_configuration(self):
        self.passport_rs_client_jks_pass = self.getPW()
        self.passport_rs_client_jks_pass_encoded = self.obscure(self.passport_rs_client_jks_pass)

        if not self.passport_rs_client_id:
            self.passport_rs_client_id = '1501.' + str(uuid.uuid4())
        if not self.passport_rp_client_id:
            self.passport_rp_client_id = '1502.' + str(uuid.uuid4())
        if not self.passport_rp_ii_client_id:
            self.passport_rp_ii_client_id = '1503.'  + str(uuid.uuid4())
        if not self.passport_resource_id:
            self.passport_resource_id = '1504.'  + str(uuid.uuid4())

        self.renderTemplate(self.passport_oxtrust_config_fn)



    def install_passport(self):
        self.logIt("Installing Passport...")

        self.passport_rs_client_jwks = self.gen_openid_jwks_jks_keys(self.passport_rs_client_jks_fn, self.passport_rs_client_jks_pass)
        self.templateRenderingDict['passport_rs_client_base64_jwks'] = self.generate_base64_string(self.passport_rs_client_jwks, 1)

        self.passport_rp_client_jwks = self.gen_openid_jwks_jks_keys(self.passport_rp_client_jks_fn, self.passport_rp_client_jks_pass)
        self.templateRenderingDict['passport_rp_client_base64_jwks'] = self.generate_base64_string(self.passport_rp_client_jwks, 1)


        self.logIt("Rendering Passport templates")
        self.renderTemplate(self.passport_central_config_json)
        self.templateRenderingDict['passport_central_config_base64'] = self.generate_base64_ldap_file(self.passport_central_config_json)
        self.renderTemplate(self.ldif_passport_config)
        self.renderTemplate(self.ldif_passport)
        self.renderTemplate(self.ldif_passport_clients)

        if self.mappingLocations['default'] == 'ldap':
            self.import_ldif_opendj([self.ldif_passport, self.ldif_passport_config, self.ldif_passport_clients])
        else:
            self.import_ldif_couchebase([self.ldif_passport, self.ldif_passport_config, self.ldif_passport_clients])


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
        
        modules_target_dir = os.path.join(self.gluu_passport_base, 'node_modules')
        self.run([self.cmd_mkdir, '-p', modules_target_dir])

        node_modules_list = glob.glob(os.path.join(self.distGluuFolder,  'passport*node_modules*'))
        if node_modules_list:
            passport_modules_archive = max(node_modules_list)
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
        self.run([self.cmd_mkdir, '-p', os.path.join(self.gluu_passport_base,'logs')])
        
        #create empty log file
        log_file = os.path.join(self.gluu_passport_base, 'logs/start.log')
        open(log_file,'w').close()

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
        
        if self.wrends_install:
            self.pbar.progress("ldap", "Installing Gluu components: LDAP", False)
            self.install_ldap_server()

        if self.cb_install:
            self.pbar.progress("couchbase", "Installing Gluu components: Couchbase", False)
            self.install_couchbase_server()

        if self.installHttpd:
            self.pbar.progress("httpd", "Installing Gluu components: HTTPD", False)
            self.configure_httpd()

        if self.installOxAuth:
            self.pbar.progress("oxauth", "Installing Gluu components: OxAuth", False)
            self.install_oxauth()

        if self.installFido2:
            self.pbar.progress("fido2", "Installing Gluu components: Fido2", False)
            self.install_fido2()

        if self.installOxTrust:
            self.pbar.progress("oxtrust", "Installing Gluu components: oxTrust", False)
            self.install_oxtrust()

        if self.installScimServer:
            self.pbar.progress("scim", "Installing Gluu components: Scim Server", False)
            self.install_scim_server()

        if self.installSaml:
            self.pbar.progress("saml", "Installing Gluu components: saml", False)
            self.install_saml()

        if self.installOxAuthRP:
            self.pbar.progress("oxauthrp", "Installing Gluu components: OxAuthRP", False)
            self.install_oxauth_rp()

        if self.installPassport:
            self.pbar.progress("passport", "Installing Gluu components: Passport", False)
            self.install_passport()

        if self.installOxd:
            self.pbar.progress("oxd", "Installing Gluu components: oxd", False)
            self.install_oxd()

        if self.installCasa:
            self.pbar.progress("casa", "Installing Gluu components: Casa", False)
            self.install_casa()

        self.install_gluu_radius_base()


    def isIP(self, address):
        try:
            socket.inet_aton(address)
            return True
        except socket.error:
            return False

    def check_email(self, email):
        return re.match('^[_a-z0-9-]+(\.[_a-z0-9-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*(\.[a-z]{2,})$', email, re.IGNORECASE)

    def checkPassword(self, pwd):
        return re.search('^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*\W)[a-zA-Z0-9\S]{6,}$', pwd)

    def ldap_encode(self, password):
        salt = os.urandom(4)
        sha = hashlib.sha1(password.encode('utf-8'))
        sha.update(salt)
        digest_ = sha.digest()
        b64encoded = base64.b64encode(digest_+salt).decode('utf-8')
        encrypted_password = '{{SSHA}}{0}'.format(b64encoded)
        return encrypted_password

    def createUser(self, userName, homeDir, shell='/bin/bash'):
        
        try:
            useradd = '/usr/sbin/useradd'
            cmd = [useradd, '--system', '--user-group', '--shell', shell, userName]
            if homeDir:
                cmd.insert(-1, '--create-home')
                cmd.insert(-1, '--home-dir')
                cmd.insert(-1, homeDir)
            else:
                cmd.insert(-1, '--no-create-home')
            self.run(cmd)
            if homeDir:
                self.logOSChanges("User %s with homedir %s was created" % (userName, homeDir))
            else:
                self.logOSChanges("User %s without homedir was created" % (userName))
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
        self.createUser('radius', homeDir=self.radius_dir, shell='/bin/false')

        self.createGroup('gluu')

        self.addUserToGroup('gluu', 'ldap')
        self.addUserToGroup('gluu', 'jetty')
        self.addUserToGroup('gluu', 'node')
        self.addUserToGroup('gluu', 'radius')
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
            if self.installFido2:
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


    def getMappingType(self, mtype):
        location = []
        for group in self.mappingLocations:
            if group != 'default' and self.mappingLocations[group] == mtype:
                location.append(group)

        return location


    def writeHybridProperties(self):

        ldap_mappings = self.getMappingType('ldap')
        couchbase_mappings = self.getMappingType('couchbase')
        
        for group in self.mappingLocations:
            if group == 'default':
                default_mapping = self.mappingLocations[group]
                break

        storages = set(self.mappingLocations.values())
        
        gluu_hybrid_roperties = [
                        'storages: {0}'.format(', '.join(storages)),
                        'storage.default: {0}'.format(default_mapping),
                        ]

        if ldap_mappings:
            gluu_hybrid_roperties.append('storage.ldap.mapping: {0}'.format(', '.join(ldap_mappings)))
            ldap_map_list = []
            for m in ldap_mappings:
                if m != 'default':
                    ldap_map_list.append(self.couchbaseBucketDict[m]['mapping'])
            gluu_hybrid_roperties.append('storage.ldap.mapping: {0}'.format(', '.join(ldap_map_list)))

        if couchbase_mappings:
            cb_map_list = []
            for m in couchbase_mappings:
                if m != 'default':
                    cb_map_list.append(self.couchbaseBucketDict[m]['mapping'])
            cb_map_str = ', '.join(cb_map_list)
            gluu_hybrid_roperties.append('storage.couchbase.mapping: {0}'.format(cb_map_str))

        self.gluu_hybrid_roperties_content = '\n'.join(gluu_hybrid_roperties)

        self.writeFile(self.gluu_hybrid_roperties, self.gluu_hybrid_roperties_content)

    def configureSystem(self):
        self.customiseSystem()
        self.createUsers()
        self.makeFolders()

        if self.persistence_type == 'hybrid':
            self.writeHybridProperties()

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


    def getBackendTypes(self):

        if self.os_type in ('ubuntu', 'debian'):
            suffix = 'deb'

        elif self.os_type in ('centos', 'red', 'fedora'):
            suffix = 'rpm'

        backend_types = []

        if glob.glob(self.distFolder+'/app/opendj-server-*4*.zip'):
            backend_types.append('wrends')

        if glob.glob(self.distFolder+'/couchbase/couchbase-server-enterprise*.'+suffix):
            backend_types.append('couchbase')

        return backend_types

    def promptForBackendMappings(self):

        options = []
        options_text = []
        
        bucket_list = list(self.couchbaseBucketDict.keys())

        for i, m in enumerate(bucket_list):
            options_text.append('({0}) {1}'.format(i+1,m))
            options.append(str(i+1))

        options_text = 'Use WrenDS to store {}'.format(' '.join(options_text))

        re_pattern = '^[1-{0}]+$'.format(len(self.couchbaseBucketDict))

        while True:
            prompt = self.getPrompt(options_text)
            if re.match(re_pattern, prompt):
                break
            else:
                print("Please select one of {0}.".format(", ".join(options)))

        couchbase_mappings = bucket_list[:]

        for i in prompt:
            m = bucket_list[int(i)-1]
            couchbase_mappings.remove(m)

        for m in couchbase_mappings:
            self.mappingLocations[m] = 'couchbase'


    def detect_hostname(self):
        if not self.ip:
            self.ip = self.detect_ip()

        detectedHostname = None

        try:
            detectedHostname = socket.gethostbyaddr(self.ip)[0]
        except:
            try:
                detectedHostname = os.popen("/bin/hostname").read().strip()
            except:
                self.logIt("No detected hostname", True)
                self.logIt(traceback.format_exc(), True)

        return detectedHostname


    def test_cb_servers(self, couchbase_hostname):
        cb_hosts = re_split_host.findall(couchbase_hostname)

        cb_query_node = None
        retval = {'result': True, 'query_node': cb_query_node, 'reason': ''}

        for i, cb_host in enumerate(cb_hosts):

            cbm_ = CBM(cb_host, self.couchebaseClusterAdmin, self.cb_password)
            if not thread_queue:
                print("    Checking Couchbase connection for " + cb_host)

            cbm_result = cbm_.test_connection()
            if not cbm_result.ok:
                if not thread_queue:
                    print("    Can't establish connection to Couchbase server with given parameters.")
                    print("**", cbm_result.reason)
                retval['result'] = False
                retval['reason'] = cb_host + ': ' + cbm_result.reason
                return retval
                
            result = cbm_.get_services()
            if result.ok:
                data = result.json()
                for node in data.get('nodesExt', []):
                    if node.get('thisNode'):
                        if 'n1qlSSL' in node.get('services', []):
                            cb_query_node = i
        else:

            if cbm_result.ok and cb_query_node != None:
                if not thread_queue:
                    print("    Successfully connected to Couchbase server")
                cb_host_ = cb_hosts[self.cb_query_node]
                self.cbm = CBM(cb_host_, self.couchebaseClusterAdmin, self.cb_password)
                return retval
            if cb_query_node == None:
                if not thread_queue:
                    print("Can't find any query node")
                retval['result'] = False
                retval['reason'] = "Can't find any query node"

        return retval

    def prompt_remote_couchbase(self):
    
        while True:
            self.couchbase_hostname = self.getPrompt("    Couchbase hosts")
            self.couchebaseClusterAdmin = self.getPrompt("    Couchbase User")
            self.cb_password =self.getPrompt("    Couchbase Password")

            result = self.test_cb_servers(self.couchbase_hostname)

            if result['result']:
                self.cb_query_node = result['query_node']
                break

    def check_remote_ldap(self, ldap_host, ldap_binddn, ldap_password):
        
        result = {'result': True, 'reason': ''}
        
        ldap_server = Server(ldap_host, port=int(self.ldaps_port), use_ssl=True)
        conn = Connection(
            ldap_server,
            user=ldap_binddn,
            password=ldap_password,
            )

        try:
            conn.bind()
        except Exception as e:
            result['result'] = False
            result['reason'] = str(e)

        if not conn.bound:
            result['result'] = False
            result['reason'] = str(conn.last_error)
        
        return result

    def check_oxd_server(self, oxd_url, error_out=True, log_error=True):

        oxd_url = os.path.join(oxd_url, 'health-check')
        try:
            result = urllib.request.urlopen(
                        oxd_url,
                        timeout = 2,
                        context=ssl._create_unverified_context()
                    )
            if result.code == 200:
                oxd_status = json.loads(result.read())
                if oxd_status['status'] == 'running':
                    return True
        except Exception as e:
            msg = "Can't connect to oxd-server with url {}".format(oxd_url)
            err = str(e)
            self.logIt(msg + err, True)
            if log_error:
                if thread_queue:
                    return str(e)
                if error_out:
                    print(gluu_utils.colors.DANGER)
                    print(msg)
                    print("Reason: ", err)
                    print(gluu_utils.colors.ENDC)

    def check_oxd_ssl_cert(self, oxd_hostname, oxd_port):

        oxd_cert = ssl.get_server_certificate((oxd_hostname, oxd_port))
        oxd_crt_fn = '/tmp/oxd_{}.crt'.format(str(uuid.uuid4()))
        self.writeFile(oxd_crt_fn, oxd_cert)
        ssl_subjects = self.get_ssl_subject(oxd_crt_fn)
        
        if ssl_subjects['CN'] != oxd_hostname:
            return ssl_subjects

    def add_couchbase_post_messages(self):
        self.post_messages.append( 
                "Please note that you have to update your firewall configuration to\n"
                "allow connections to the following ports on Couchbase Server:\n"
                "4369, 28091 to 28094, 9100 to 9105, 9998, 9999, 11207, 11209 to 11211,\n"
                "11214, 11215, 18091 to 18093, and from 21100 to 21299."
            )
        (w, e) = ('', '') if thread_queue else (gluu_utils.colors.WARNING, gluu_utils.colors.ENDC)
        self.post_messages.append(
            w+"By using Couchbase Server you agree to the End User License Agreement.\n"
            "See /opt/couchbase/LICENSE.txt"+e
            )

    def promptForCasaInstallation(self, promptForCasa='n'):
        
        if promptForCasa == 'n':
            promptForCasa = self.getPrompt("Install Casa?", 
                                            self.getDefaultOption(self.installCasa)
                                            )[0].lower()
        if promptForCasa == 'y':
            self.installCasa = True
            self.couchbaseBucketDict['default']['ldif'].append(self.ldif_scripts_casa)
        else:
            self.installCasa = False

        if self.installCasa:
            print ("Please enter URL of oxd-server if you have one, for example: https://oxd.mygluu.org:8443")
            if self.oxd_package:
                print ("Else leave blank to install oxd server locally.")

            while True:
                oxd_server_https = input("oxd Server URL: ").lower()
                
                if (not oxd_server_https) and self.oxd_package:
                    self.oxd_server_https = 'https://{}:{}'.format(self.hostname, self.templateRenderingDict['oxd_port'])
                    self.installOxd = True
                    break

                print ("Checking oxd server ...")
                if self.check_oxd_server(oxd_server_https):
                    oxd_hostname, oxd_port = self.parse_url(oxd_server_https)
                    oxd_cert = ssl.get_server_certificate((oxd_hostname, oxd_port))
                    oxd_crt_fn = '/tmp/oxd_{}.crt'.format(str(uuid.uuid4()))
                    self.writeFile(oxd_crt_fn, oxd_cert)
                    ssl_subjects = self.get_ssl_subject(oxd_crt_fn)
                    
                    if not ssl_subjects['CN'] == oxd_hostname:
                        print (('Hostname of oxd ssl certificate is {0}{1}{2} '
                                'which does not match {0}{3}{2}, \ncasa won\'t start '
                                'properly').format(
                                        colors.DANGER,
                                        ssl_subjects['CN'],
                                        colors.ENDC,
                                        oxd_hostname
                                        ))
                    else:
                        self.oxd_server_https = oxd_server_https
                        break

    def promptForProperties(self):

        if self.noPrompt:
            return

        promptForMITLicense = self.getPrompt("Do you acknowledge that use of the Gluu Server is under the Apache-2.0 license?", "N|y")[0].lower()
        if promptForMITLicense != 'y':
            sys.exit(0)

        # IP address needed only for Apache2 and hosts file update
        if self.installHttpd:
            self.ip = self.get_ip()

        detectedHostname = self.detect_hostname()

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
                print("Hostname can't be \033[;1mlocalhost\033[0;0m")

        self.oxd_server_https = 'https://{}:{}'.format(self.hostname, self.templateRenderingDict['oxd_port'])

        # Get city and state|province code
        self.city = self.getPrompt("Enter your city or locality")
        self.state = self.getPrompt("Enter your state or province two letter code")

        # Get the Country Code
        long_enough = False
        while not long_enough:
            countryCode = self.getPrompt("Enter two letter Country Code")
            if len(countryCode) != 2:
                print("Country code must be two characters")
            else:
                self.countryCode = countryCode
                long_enough = True

        self.orgName = self.getPrompt("Enter Organization Name")

        while True:
            self.admin_email = self.getPrompt('Enter email address for support at your organization')
            if self.check_email(self.admin_email):
                break
            else:
                print("Please enter valid email address")
        
        self.application_max_ram = self.getPrompt("Enter maximum RAM for applications in MB", str(self.application_max_ram))

        oxtrust_admin_password = self.getPW(special='.*=!%&+/-')

        while True:
            oxtrust_admin_password = self.getPrompt("Enter oxTrust Admin Password", oxtrust_admin_password)
            if len(oxtrust_admin_password) > 5:
                break
            else:
                print("Password must be at least 6 characters")
        
        self.oxtrust_admin_password = oxtrust_admin_password


        available_backends = self.getBackendTypes()

        localWrendsOnly = False

        if (self.wrends_install != REMOTE) and (not self.cb_install) and (available_backends == ['wrends']):
            self.wrends_install = LOCAL
            
        elif self.wrends_install != REMOTE and (self.cb_install == REMOTE or 'couchbase' in available_backends):
            promptForLDAP = self.getPrompt("Install Local WrenDS Server?", "Yes")[0].lower()
            if promptForLDAP[0] == 'y':
                self.wrends_install = LOCAL
            else:
                self.wrends_install = NONE

        if self.wrends_install == LOCAL:

            ldapPass = self.ldapPass if self.ldapPass else self.oxtrust_admin_password

            while True:
                ldapPass = self.getPrompt("Enter Password for LDAP Admin ({})".format(self.ldap_binddn), self.oxtrust_admin_password)

                if self.checkPassword(ldapPass):
                    break
                else:
                    print("Password must be at least 6 characters and include one uppercase letter, one lowercase letter, one digit, and one special character.")

            self.ldapPass = ldapPass

        elif self.wrends_install == REMOTE:
            while True:
                ldapHost = self.getPrompt("    LDAP hostname")
                ldapPass = self.getPrompt("    Password for '{0}'".format(self.ldap_binddn))
                conn_check = self.check_remote_ldap(ldapHost, self.ldap_binddn, ldapPass)
                if conn_check['result']:
                    break
                else:
                    print("    {}Error connecting to LDAP server: {} {}".format(gluu_utils.colors.FAIL, conn_check['reason'], gluu_utils.colors.ENDC))

            self.ldapPass = ldapPass
            self.ldap_hostname = ldapHost

        if self.cb_install == REMOTE:
            self.prompt_remote_couchbase()

        elif 'couchbase' in available_backends:
            promptForCB = self.getPrompt("Install Local Couchbase Server?", "Yes")[0].lower()
            if promptForCB[0] == 'y':
                self.cb_install = LOCAL
                self.isCouchbaseUserAdmin = True

                while True:
                    cbPass = self.getPrompt("Enter Password for Couchbase {}admin{} user".format(gluu_utils.colors.BOLD, gluu_utils.colors.ENDC), self.oxtrust_admin_password)

                    if self.checkPassword(cbPass):
                        break
                    else:
                        print("Password must be at least 6 characters and include one uppercase letter, one lowercase letter, one digit, and one special character.")

                self.cb_password = cbPass
            self.cbm = CBM(self.couchbase_hostname, self.couchebaseClusterAdmin, self.cb_password)

        if not (self.wrends_install or self.cb_install):
            print("{}You must have at least one DB backend. Exiting...{}".format(gluu_utils.colors.WARNING, gluu_utils.colors.ENDC))
            sys.exit(False)

        if self.cb_install:
            self.cache_provider_type = 'NATIVE_PERSISTENCE'
            self.add_couchbase_post_messages()

        if not self.wrends_install and self.cb_install:
            self.mappingLocations = { group: 'couchbase' for group in self.couchbaseBucketDict }
            self.persistence_type = 'couchbase'

        elif self.wrends_install and self.cb_install:
            self.promptForBackendMappings()
            self.persistence_type = 'hybrid'

        if setupOptions['allowPreReleasedFeatures']:
            while True:
                java_type = self.getPrompt("Select Java type: 1.Jre-1.8   2.OpenJDK-11", '1')
                if not java_type:
                    java_type = 1
                    break
                if java_type in '12':
                    break
                else:
                    print("Please enter 1 or 2")

            if java_type == '1':
                self.java_type = 'jre'
            else:
                self.java_type = 'jdk'
                self.defaultTrustStoreFN = '%s/lib/security/cacerts' % self.jre_home
                
        promptForOxAuth = self.getPrompt("Install oxAuth OAuth2 Authorization Server?", 
                                        self.getDefaultOption(self.installOxAuth)
                                            )[0].lower()
        if promptForOxAuth == 'y':
            self.installOxAuth = True
        else:
            self.installOxAuth = False

        promptForOxTrust = self.getPrompt("Install oxTrust Admin UI?",
                                            self.getDefaultOption(self.installOxTrust)
                                            )[0].lower()
        if promptForOxTrust == 'y':
            self.installOxTrust = True
        else:
            self.installOxTrust = False

        couchbase_mappings_ = self.getMappingType('couchbase')
        buckets_ = [ 'gluu_{}'.format(b) for b in couchbase_mappings_ ]

        buckets_.append('gluu')

        if self.cb_install == REMOTE:

            isCBRoleOK = self.checkCBRoles(buckets_)

            if not isCBRoleOK[0]:
                print("{}Please check user {} has roles {} on bucket(s) {}{}".format(
                                gluu_utils.colors.DANGER,
                                self.cbm.auth.username,
                                ', '.join(self.cb_bucket_roles),
                                ', '.join(isCBRoleOK[1]),
                                gluu_utils.colors.ENDC
                                ))
                sys.exit(False)



        promptForHTTPD = self.getPrompt("Install Apache HTTPD Server", 
                                        self.getDefaultOption(self.installHTTPD)
                                        )[0].lower()
        if promptForHTTPD == 'y':
            self.installHttpd = True
        else:
            self.installHttpd = False

        promptForScimServer = self.getPrompt("Install Scim Server?",
                                            self.getDefaultOption(self.installScimServer)
                                            )[0].lower()
        if promptForScimServer == 'y':
            self.installScimServer = True
            self.gluuScimEnabled = 'true'
            self.enable_scim_access_policy = 'true'

        promptForFido2Server = self.getPrompt("Install Fido2 Server?",
                                            self.getDefaultOption(self.installFido2)
                                            )[0].lower()
        if promptForFido2Server == 'y':
            self.installFido2 = True


        promptForShibIDP = self.getPrompt("Install Shibboleth SAML IDP?",
                                            self.getDefaultOption(self.installSaml)
                                            )[0].lower()
        if promptForShibIDP == 'y':
            self.shibboleth_version = 'v3'
            self.installSaml = True
            self.gluuSamlEnabled = 'true'
            if self.persistence_type in ('couchbase','hybrid'):
                self.couchbaseShibUserPassword = self.getPW()
        else:
            self.installSaml = False

        promptForOxAuthRP = self.getPrompt("Install oxAuth RP?",
                                            self.getDefaultOption(self.installOxAuthRP)
                                            )[0].lower()
        if promptForOxAuthRP == 'y':
            self.installOxAuthRP = True
        else:
            self.installOxAuthRP = False

        promptForPassport = self.getPrompt("Install Passport?", 
                                            self.getDefaultOption(self.installPassport)
                                            )[0].lower()
        if promptForPassport == 'y':
            self.installPassport = True
            self.gluuPassportEnabled = 'true'
            self.enable_scim_access_policy = 'true'
        else:
            self.installPassport = False

        if os.path.exists(os.path.join(self.distGluuFolder, 'casa.war')):
            self.promptForCasaInstallation()

        if (not self.installOxd) and self.oxd_package:
            promptForOxd = self.getPrompt("Install Oxd?", 
                                                self.getDefaultOption(self.installOxd)
                                                )[0].lower()
            if promptForOxd == 'y':
                self.installOxd = True
            else:
                self.installOxd = False


        if self.installOxd:

            promptForOxdGluuStorage = self.getPrompt("  Use Gluu Storage for Oxd?",
                                                self.getDefaultOption(self.oxd_use_gluu_storage)
                                                )[0].lower()
            if promptForOxdGluuStorage == 'y':
                self.oxd_use_gluu_storage = True


        promptForGluuRadius = self.getPrompt("Install Gluu Radius?", 
                                            self.getDefaultOption(self.installGluuRadius)
                                            )[0].lower()
        if promptForGluuRadius == 'y':
            self.installGluuRadius = True
            self.oxauth_legacyIdTokenClaims = 'true'
            self.oxauth_openidScopeBackwardCompatibility =  'true'
            self.enableRadiusScripts = 'true'
            self.gluuRadiusEnabled = 'true'
        else:
            self.installGluuRadius = False


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
        fn = os.path.basename(filePath)
        in_fp = os.path.join(templateFolder, fn) 
        self.logIt("Rendering template %s" % in_fp)
        template_text = self.readFile(in_fp)

        # Create output folder if needed
        if not os.path.exists(outputFolder):
            os.makedirs(outputFolder)

        rendered_text = self.fomatWithDict(template_text, self.merge_dicts(self.__dict__, self.templateRenderingDict))
        out_fp = os.path.join(outputFolder, fn)
        self.writeFile(out_fp, rendered_text)

    def renderTemplate(self, filePath):
        self.renderTemplateInOut(filePath, self.templateFolder, self.outputFolder)

    def render_templates(self, templates=None):
        self.logIt("Rendering templates")

        if not templates:
            templates = self.ce_templates

        if self.persistence_type=='couchbase':
            self.ce_templates[self.ox_ldap_properties] = False

        for fullPath in templates:
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

        try:
            self.renderTemplate(self.ldif_configuration)
            self.renderTemplate(self.ldif_fido2)
        except:
            self.logIt("Error writing template", True)
            self.logIt(traceback.format_exc(), True)

    def render_templates_folder(self, templatesFolder):
        self.logIt("Rendering templates folder: %s" % templatesFolder)

        coucbase_dict = self.couchbaseDict()

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
                    newFn.write(template_text % self.merge_dicts(coucbase_dict, self.templateRenderingDict, self.__dict__))
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
                    extensionScriptName = extensionScriptName.lower()

                    self.templateRenderingDict[extensionScriptName] = base64ScriptFile
                    self.logIt("Loaded script %s with type %s into %s" % (scriptFile, extensionType, extensionScriptName))

        except:
            self.logIt("Error loading scripts from %s" % self.extensionFolder, True)
            self.logIt(traceback.format_exc(), True)

    def reindent(self, text, num_spaces):
        text = text.splitlines()
        text = [(num_spaces * ' ') + line.lstrip() for line in text]
        text = '\n'.join(text)

        return text

    def generate_base64_file(self, fn, num_spaces):
        self.logIt('Loading file %s' % fn)
        plain_file_b64encoded_text = None
        try:
            plain_file_text = self.readFile(fn, rmode='rb')
            plain_file_b64encoded_text = base64.b64encode(plain_file_text).decode('utf-8').strip()
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

        self.templateRenderingDict['fido2_dynamic_conf_base64'] = self.generate_base64_ldap_file(self.fido2_dynamic_conf_json)
        self.templateRenderingDict['fido2_static_conf_base64'] = self.generate_base64_ldap_file(self.fido2_static_conf_json)

        if self.installPassport:
            oxtrust_config = json.loads(self.readFile(self.oxtrust_config_json), object_pairs_hook=OrderedDict)
            passport_oxtrust_config = json.loads(self.readFile(self.passport_oxtrust_config_fn), object_pairs_hook=OrderedDict)
            oxtrust_config.update(passport_oxtrust_config)

            with open(self.oxtrust_config_json, 'w') as w:
                json.dump(oxtrust_config, w, indent=2)

        self.templateRenderingDict['oxtrust_config_base64'] = self.generate_base64_ldap_file(self.oxtrust_config_json);
        self.templateRenderingDict['oxtrust_cache_refresh_base64'] = self.generate_base64_ldap_file(self.oxtrust_cache_refresh_json)
        self.templateRenderingDict['oxtrust_import_person_base64'] = self.generate_base64_ldap_file(self.oxtrust_import_person_json)

        self.templateRenderingDict['oxidp_config_base64'] = self.generate_base64_ldap_file(self.oxidp_config_json)


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
    def run(self, args, cwd=None, env=None, useWait=False, shell=False, get_stderr=False):
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
                output = output.decode('utf-8')
                err = err.decode('utf-8')

                if output:
                    self.logIt(output)
                if err:
                    self.logIt(err, True)
        except:
            self.logIt("Error running command : %s" % " ".join(args), True)
            self.logIt(traceback.format_exc(), True)

        if get_stderr:
            return output, err

        return output

    def save_properties(self, prop_fn=None, obj=None):
        
        if not prop_fn:
            prop_fn = self.savedProperties
            
        if not obj:
            obj = self

        self.logIt('Saving properties to %s' % prop_fn)
        
        def getString(value):
            if isinstance(value, str):
                return value.strip()
            elif isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
                return str(value)
            else:
                return ''

        try:
            p = Properties()
            keys = list(obj.__dict__.keys())
            keys.sort()
            for key in keys:
                key = str(key)
                if key in ('couchbaseInstallOutput', 'post_messages', 'cb_bucket_roles', 'properties_password', 'non_setup_properties'):
                    continue
                if key == 'mappingLocations':
                    p[key] = json.dumps(obj.__dict__[key])
                else:
                    value = getString(obj.__dict__[key])
                    if value != '':
                        p[key] = value

            with open(prop_fn, 'wb') as f:
                p.store(f, encoding="utf-8")
            
            self.run(['openssl', 'enc', '-aes-256-cbc', '-in', prop_fn, '-out', prop_fn+'.enc', '-k', self.oxtrust_admin_password])
            
            self.post_messages.append(
                "Encrypted properties file saved to {0}.enc with password {1}\nDecrypt the file with the following command if you want to re-use:\nopenssl enc -d -aes-256-cbc -in {2}.enc -out {3}".format(
                prop_fn,  self.oxtrust_admin_password, os.path.basename(prop_fn), os.path.basename(self.setup_properties_fn)))
            
            self.run(['rm', '-f', prop_fn])
            
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
        if os.path.isfile(self.ldapPassFn):
            os.remove(self.ldapPassFn)

    def install_opendj(self):
        self.logIt("Running WrenDS Setup")

        # Copy opendj-setup.properties so user ldap can find it in /opt/opendj
        setupPropsFN = os.path.join(self.ldapBaseFolder, 'opendj-setup.properties')
        shutil.copy("%s/opendj-setup.properties" % self.outputFolder, setupPropsFN)
        self.set_ownership()
        self.run(['chown', 'ldap:ldap', setupPropsFN])

        try:
            ldapSetupCommand = '%s/setup' % self.ldapBaseFolder
            setupCmd = " ".join([ldapSetupCommand,
                                '--no-prompt',
                                '--cli',
                                '--propertiesFilePath',
                                setupPropsFN,
                                '--acceptLicense'])
            self.run(['/bin/su',
                      'ldap',
                      '-c',
                      setupCmd],
                      cwd='/opt/opendj',
                      )
        except:
            self.logIt("Error running LDAP setup script", True)
            self.logIt(traceback.format_exc(), True)

        #Append self.jre_home to OpenDj java.properties        
        opendj_java_properties_fn = os.path.join(self.ldapBaseFolder, 'config/java.properties')

        self.logIt("append self.jre_home to WrenDS %s" % opendj_java_properties_fn)
        with open(opendj_java_properties_fn,'a') as f:
            f.write('\ndefault.java-home={}\n'.format(self.jre_home))

        try:
            self.logIt('Stopping opendj server')
            cmd = os.path.join(self.ldapBaseFolder, 'bin/stop-ds')
            self.run(['/bin/su','ldap', '-c', cmd], cwd='/opt/opendj/bin')
        except:
            self.logIt("Error stopping opendj", True)
            self.logIt(traceback.format_exc(), True)

    def post_install_opendj(self):
        try:
            os.remove(os.path.join(self.ldapBaseFolder, 'opendj-setup.properties'))
        except:
            self.logIt("Error deleting WrenDS properties. Make sure %s/opendj-setup.properties is deleted" % self.ldapBaseFolder)
            self.logIt(traceback.format_exc(), True)

    def configure_opendj(self):
        self.logIt("Configuring WrenDS")

        opendj_prop_name = 'global-aci:\'(targetattr!="userPassword||authPassword||debugsearchindex||changes||changeNumber||changeType||changeTime||targetDN||newRDN||newSuperior||deleteOldRDN")(version 3.0; acl "Anonymous read access"; allow (read,search,compare) userdn="ldap:///anyone";)\''
        config_changes = [
                          ['set-backend-prop', '--backend-name', 'userRoot', '--set', 'db-cache-percent:70'],
                          ['set-global-configuration-prop', '--set', 'single-structural-objectclass-behavior:accept'],
                          ['set-password-policy-prop', '--policy-name', '"Default Password Policy"', '--set', 'allow-pre-encoded-passwords:true'],
                          ['set-log-publisher-prop', '--publisher-name', '"File-Based Audit Logger"', '--set', 'enabled:true'],
                          ['create-backend', '--backend-name', 'metric', '--set', 'base-dn:o=metric', '--type %s' % self.ldap_backend_type, '--set', 'enabled:true', '--set', 'db-cache-percent:20'],
                          ]
                          
        if self.mappingLocations['site'] == 'ldap':
            config_changes.append(['create-backend', '--backend-name', 'site', '--set', 'base-dn:o=site', '--type %s' % self.ldap_backend_type, '--set', 'enabled:true', '--set', 'db-cache-percent:20'])

        config_changes += [
                          ['set-connection-handler-prop', '--handler-name', '"LDAP Connection Handler"', '--set', 'enabled:false'],
                          ['set-connection-handler-prop', '--handler-name', '"JMX Connection Handler"', '--set', 'enabled:false'],
                          ['set-access-control-handler-prop', '--remove', '%s' % opendj_prop_name],
                          ['set-global-configuration-prop', '--set', 'reject-unauthenticated-requests:true'],
                          ['set-password-policy-prop', '--policy-name', '"Default Password Policy"', '--set', 'default-password-storage-scheme:"Salted SHA-512"'],
                          ['create-plugin', '--plugin-name', '"Unique mail address"', '--type', 'unique-attribute', '--set enabled:true',  '--set', 'base-dn:o=gluu', '--set', 'type:mail'],
                          ['create-plugin', '--plugin-name', '"Unique uid entry"', '--type', 'unique-attribute', '--set enabled:true',  '--set', 'base-dn:o=gluu', '--set', 'type:uid'],
                          ['set-password-policy-prop', '--policy-name', '"Default Password Policy"', '--set', 'default-password-storage-scheme:"Salted SHA-512"'],
                          ]


        if (not self.listenAllInterfaces) and (self.wrends_install == LOCAL):
            config_changes.append(['set-connection-handler-prop', '--handler-name', '"LDAPS Connection Handler"', '--set', 'enabled:true', '--set', 'listen-address:127.0.0.1'])
            config_changes.append(['set-administration-connector-prop', '--set', 'listen-address:127.0.0.1'])
                          
        for changes in config_changes:
            cwd = os.path.join(self.ldapBaseFolder, 'bin')
            dsconfigCmd = " ".join([
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
                      dsconfigCmd], cwd=cwd)

    def export_opendj_public_cert(self):
        # Load password to acces OpenDJ truststore
        self.logIt("Getting WrenDS certificate")

        opendj_cert = ssl.get_server_certificate((self.ldap_hostname, self.ldaps_port))
        with open(self.opendj_cert_fn,'w') as w:
            w.write(opendj_cert)

        # Convert OpenDJ certificate to PKCS12
        self.logIt("Importing WrenDS certificate to truststore")
        self.run([self.cmd_keytool,
                  '-importcert',
                  '-noprompt',
                  '-alias',
                  'server-cert',
                  '-file',
                  self.opendj_cert_fn,
                  '-keystore',
                  self.opendj_p12_fn,
                  '-storetype',
                  'PKCS12',
                  '-storepass',
                  self.opendj_p12_pass
                  ])

        # Import OpenDJ certificate into java truststore
        self.logIt("Import WrenDS certificate")

        self.run([self.cmd_keytool, "-import", "-trustcacerts", "-alias", "%s_opendj" % self.hostname, \
                  "-file", self.opendj_cert_fn, "-keystore", self.defaultTrustStoreFN, \
                  "-storepass", "changeit", "-noprompt"])

    def import_ldif_template_opendj(self, ldif):
        self.logIt("Importing LDIF file '%s' into WrenDS" % ldif)
        realInstallDir = os.path.realpath(self.outputFolder)

        ldif_file_fullpath = os.path.realpath(ldif)
        cwd = os.path.join(self.ldapBaseFolder, 'bin')
        importParams = [
                          self.loadLdifCommand,
                          '--hostname',
                          self.ldap_hostname,
                          '--port',
                          self.ldap_admin_port,
                          '--bindDN',
                          '"%s"' % self.ldap_binddn,
                          '-j',
                          self.ldapPassFn,
                          '--trustAll',
                          '--useSSL',
                          '--continueOnError',
                          '--filename',
                          ldif_file_fullpath,
                        ]

        importCmd = " ".join(importParams)
        
        # Check if there is no .pw file
        createPwFile = not os.path.exists(self.ldapPassFn)
        if createPwFile:
            self.createLdapPw()
        
        self.run(['/bin/su',
                  'ldap',
                  '-c',
                  '%s' % importCmd], cwd=cwd)

        if createPwFile:
            self.deleteLdapPw()

    def import_ldif_opendj(self, ldif_file_list=[]):

        #We won't load data to secondary cluster nodes
        if not self.loadData:
            return
        
        if not ldif_file_list:
            self.logIt("Importing userRoot LDIF data")
        else:
            self.logIt("Importing LDIF File(s): " + ' '.join(ldif_file_list))

        if not ldif_file_list:
            ldif_file_list = self.ldif_files
        
        for ldif_file_fn in ldif_file_list:
            ldif_file_fullpath = os.path.realpath(ldif_file_fn)
            cwd = os.path.join(self.ldapBaseFolder, 'bin')
            importParams = [
                              self.loadLdifCommand,
                              '--hostname',
                              self.ldap_hostname,
                              '--port',
                              self.ldap_admin_port,
                              '--bindDN',
                              '"%s"' % self.ldap_binddn,
                              '-j',
                              self.ldapPassFn,
                              '--trustAll',
                              '--useSSL',
                              '--continueOnError',
                              '--filename',
                              ldif_file_fullpath,
                            ]

            importCmd = " ".join(importParams)

            self.run(['/bin/su',
                      'ldap',
                      '-c',
                      '%s' % importCmd], cwd=cwd)

    def index_opendj_backend(self, backend):
        index_command = 'create-backend-index'
        cwd = os.path.join(self.ldapBaseFolder, 'bin')
        try:
            self.logIt("Running LDAP index creation commands for " + backend + " backend")
            # This json file contains a mapping of the required indexes.
            # [ { "attribute": "inum", "type": "string", "index": ["equality"] }, ...}

            with open(self.openDjIndexJson) as f:
                index_json = json.load(f)

            for attrDict in index_json:
                attr_name = attrDict['attribute']
                index_types = attrDict['index']

                index_type_list = [ '--set index-type:' + index_type for index_type in index_types ]
                index_type_str = ' '.join(index_type_list)
                backend_names = attrDict['backend']
                for backend_name in backend_names:
                    if (backend_name == backend):
                        self.logIt("Creating %s index for attribute %s" % (', '.join(index_types), attr_name))
                        indexCmd = " ".join([
                                             self.ldapDsconfigCommand,
                                             index_command,
                                             '--backend-name',
                                             backend,
                                             '--type',
                                             'generic',
                                             '--index-name',
                                             attr_name,
                                             index_type_str,
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
                                  indexCmd], cwd=cwd)

        except:
            self.logIt("Error occured during backend " + backend + " LDAP indexing", True)
            self.logIt(traceback.format_exc(), True)

    def index_opendj(self):
        self.index_opendj_backend('userRoot')
        if self.mappingLocations['site'] == 'ldap':
            self.index_opendj_backend('site')


    def prepare_opendj_schema(self):
        self.logIt("Copying WrenDS schema")
        for schemaFile in self.openDjschemaFiles:
            self.copyFile(schemaFile, self.openDjSchemaFolder)


        self.run([self.cmd_chmod, '-R', 'a+rX', self.ldapBaseFolder])
        self.run([self.cmd_chown, '-R', 'ldap:ldap', self.ldapBaseFolder])

    def setup_opendj_service(self):
        service_path = self.detect_service_path()
        init_script_fn = '/etc/init.d/opendj'
        if (self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd') or (self.os_type+self.os_version in ('ubuntu20', 'ubuntu18','debian9','debian10')):
            remove_init_script = True
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
            if os.path.exists(init_script_fn):
                self.run(['rm', '-f', init_script_fn])
        else:
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

            self.fix_init_scripts('opendj', init_script_fn)
            self.enable_service_at_start('opendj')

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

        if (self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd') or (self.os_type+self.os_version in ('ubuntu20', 'ubuntu18','debian9','debian10')):
            service_path = self.systemctl
            
        elif self.os_type in ['debian', 'ubuntu']:
            service_path = '/usr/sbin/service'

        return service_path

    def run_service_command(self, service, operation):
        service_path = self.detect_service_path()

        try:
            if (self.os_type in ['centos', 'red', 'fedora'] and self.os_initdaemon == 'systemd') or (self.os_type+self.os_version in ('ubuntu20', 'ubuntu18','debian9','debian10')):
                self.run([service_path, operation, service], None, None, True)
            else:
                self.run([service_path, service, operation], None, None, True)
        except:
            self.logIt("Error starting service '%s'" % operation)
            self.logIt(traceback.format_exc(), True)

    def get_apache_service_name(self):
        # Detect apache service name
        if self.os_type in ('centos', 'red', 'fedora') and self.os_initdaemon == 'systemd':
            return 'httpd'

        return 'apache2'

    def start_services(self):

        # Apache HTTPD
        if self.installHttpd:
            self.pbar.progress("gluu", "Starting httpd")
            self.run_service_command(self.get_apache_service_name(), 'restart')

        # LDAP services
        if self.wrends_install == LOCAL:
            self.pbar.progress("gluu", "Starting WrenDS")
            self.run_service_command('opendj', 'stop')
            self.run_service_command('opendj', 'start')

        # Jetty services
        # Iterate through all components and start installed
        for applicationName, applicationConfiguration in self.jetty_app_configuration.items():

            # we will start casa later, after importing oxd certificate
            if applicationName == 'casa':
                continue
                
            if applicationConfiguration['installed']:
                self.pbar.progress("gluu", "Starting Gluu Jetty {} Service".format(applicationName))
                self.run_service_command(applicationName, 'start')

        
        # Passport service
        if self.installPassport:
            self.pbar.progress("gluu", "Starting Passport Service")
            self.run_service_command('passport', 'start')

        # oxd service
        if self.installOxd:
            self.pbar.progress("gluu", "Starting oxd Service")
            self.run_service_command('oxd-server', 'start')

        # casa service
        if self.installCasa:
            # import_oxd_certificate2javatruststore:
            self.logIt("Importing oxd certificate")
            self.import_oxd_certificate()

            self.pbar.progress("gluu", "Starting Casa Service")
            self.run_service_command('casa', 'start')

        # Radius service
        if self.installGluuRadius:
            self.pbar.progress("gluu", "Starting Gluu Radius Service")
            self.run_service_command('gluu-radius', 'start')

    def import_oxd_certificate(self):

        # import_oxd_certificate2javatruststore:
        self.logIt("Importing oxd-server certificate")

        # check oxd status for 25 seconds:
        for i in range(5):
            self.logIt("Checking oxd-server status. Try {}".format(i+1))
            if self.check_oxd_server(self.oxd_server_https, log_error=False):
                self.logIt("oxd-server seems good")
                break
            time.sleep(5)
        else:
            self.logIt("oxd server at  {} did not repond in 25 seconds".format(self.oxd_server_https), True)

        try:

            oxd_hostname, oxd_port = self.parse_url(self.oxd_server_https)
            if not oxd_port: 
                oxd_port = self.templateRenderingDict['oxd_port']

            oxd_cert = ssl.get_server_certificate((oxd_hostname, oxd_port))
            oxd_alias = 'oxd_' + oxd_hostname.replace('.','_')
            oxd_cert_tmp_fn = '/tmp/{}.crt'.format(oxd_alias)

            with open(oxd_cert_tmp_fn,'w') as w:
                w.write(oxd_cert)

            self.run([self.cmd_keytool, '-import', '-trustcacerts', '-keystore', 
                            '/opt/jre/jre/lib/security/cacerts', '-storepass', 'changeit', 
                            '-noprompt', '-alias', oxd_alias, '-file', oxd_cert_tmp_fn])

        except:
            self.logIt(traceback.format_exc(), True)



    def update_hostname(self):
        self.logIt("Copying hosts and hostname to final destination")

        if self.os_initdaemon == 'systemd' and self.os_type in ['centos', 'red', 'fedora']:
            self.run(['/usr/bin/hostnamectl', 'set-hostname', self.hostname])
        else:
            if self.os_type in ['debian', 'ubuntu']:
                self.copyFile("%s/hostname" % self.outputFolder, self.etc_hostname)
                self.run(['/bin/chmod', '-f', '644', self.etc_hostname])

            if self.os_type in ['centos', 'red', 'fedora']:
                self.copyFile("%s/network" % self.outputFolder, self.network)

            self.run(['/bin/hostname', self.hostname])

        if not os.path.exists(self.etc_hosts):
            self.writeFile(self.etc_hosts, '{}\t{}\n'.format(self.ip, self.hostname))
        else:
            hostname_file_content = self.readFile(self.etc_hosts)
            with open(self.etc_hosts,'w') as w:
                for l in hostname_file_content.splitlines():
                    if not self.hostname in l.split():
                        w.write(l+'\n')

                w.write('{}\t{}\n'.format(self.ip, self.hostname))

        self.run(['/bin/chmod', '-R', '644', self.etc_hosts])


    def import_custom_ldif(self, fullPath):
        output_dir = os.path.join(fullPath, '.output')
        self.logIt("Importing Custom LDIF files")
        realInstallDir = os.path.realpath(self.install_dir)

        try:
            for ldif in self.get_filepaths(output_dir):
                custom_ldif = output_dir + '/' + ldif
                self.import_ldif_template_opendj(custom_ldif)
        except:
            self.logIt("Error importing custom ldif file %s" % ldif, True)
            self.logIt(traceback.format_exc(), True)

    def install_ldap_server(self):
        self.logIt("Running WrenDS Setup")
        
        self.pbar.progress("opendj", "Extracting WrenDS", False)
        self.extractOpenDJ()

        self.createLdapPw()
        
        try:
            self.pbar.progress("opendj", "WrenDS: installing", False)
            if self.wrends_install == LOCAL:
                self.install_opendj()

                self.pbar.progress("opendj", "WrenDS: preparing schema", False)
                self.prepare_opendj_schema()
                self.pbar.progress("opendj", "WrenDS: setting up service", False)
                self.setup_opendj_service()

            if self.wrends_install:
                self.pbar.progress("opendj", "WrenDS: configuring", False)
                self.configure_opendj()
                self.pbar.progress("opendj", "WrenDS:  exporting certificate", False)
                self.export_opendj_public_cert()
                self.pbar.progress("opendj", "WrenDS: creating indexes", False)
                self.index_opendj()
                self.pbar.progress("opendj", "WrenDS: importing Ldif files", False)
                
                ldif_files = []

                if self.mappingLocations['default'] == 'ldap':
                    ldif_files += self.couchbaseBucketDict['default']['ldif']

                ldap_mappings = self.getMappingType('ldap')
  
                for group in ldap_mappings:
                    ldif_files +=  self.couchbaseBucketDict[group]['ldif']
  
                if not self.ldif_base in ldif_files:
                    ldif_files.insert(0, self.ldif_base)

                self.import_ldif_opendj(ldif_files)
                
                self.pbar.progress("opendj", "WrenDS: post installation", False)
                if self.wrends_install == LOCAL:
                    self.post_install_opendj()
        except:
            self.logIt(traceback.format_exc(), True)


    def calculate_aplications_memory(self, application_max_ram, jetty_app_configuration, installedComponents):
        self.logIt("Calculating memory setting for applications")
        allowedApplicationsMemory = {}
        retVal = True
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
        for applicationName, applicationConfiguration in jetty_app_configuration.items():
            if applicationName in allowedApplicationsMemory:
                applicationMemory = allowedApplicationsMemory.get(applicationName)
            else:
                # We uses this dummy value to render template properly of not installed application
                applicationMemory = 256

            self.templateRenderingDict["%s_max_mem" % applicationName] = applicationMemory

            self.templateRenderingDict["%s_max_meta_mem" % applicationName] = applicationConfiguration['memory']['metaspace_mb']
            applicationMemory = applicationMemory - applicationConfiguration['memory']['metaspace_mb']

            if 'jvm_heap_ration' in applicationConfiguration['memory']:
                jvmHeapRation = applicationConfiguration['memory']['jvm_heap_ration']

                minHeapMem = 256
                maxHeapMem = int(applicationMemory * jvmHeapRation)
                if maxHeapMem < minHeapMem:
                    minHeapMem = maxHeapMem

                self.templateRenderingDict["%s_max_heap_mem" % applicationName] = maxHeapMem
                self.templateRenderingDict["%s_min_heap_mem" % applicationName] = minHeapMem

                if maxHeapMem < 256 and applicationName in allowedApplicationsMemory:    
                    retVal = False

        return retVal

    def calculate_selected_aplications_memory(self):
        installedComponents = []

        # Jetty apps
        if self.installOxAuth:
            installedComponents.append(self.jetty_app_configuration['oxauth'])
        if self.installOxTrust:
            installedComponents.append(self.jetty_app_configuration['identity'])
        if self.installSaml:
            installedComponents.append(self.jetty_app_configuration['idp'])
        if self.installOxAuthRP:
            installedComponents.append(self.jetty_app_configuration['oxauth-rp'])
        if self.installCasa:
            installedComponents.append(self.jetty_app_configuration['casa'])
        if self.installScimServer:
            installedComponents.append(self.jetty_app_configuration['scim'])
        if self.installFido2:
            installedComponents.append(self.jetty_app_configuration['fido2'])
        # Node apps
        if self.installPassport:
            installedComponents.append(self.jetty_app_configuration['passport'])
        
        return self.calculate_aplications_memory(self.application_max_ram, self.jetty_app_configuration, installedComponents)

    def merge_dicts(self, *dict_args):
        result = {}
        for dictionary in dict_args:
            result.update(dictionary)

        return result


    def get_install_commands(self):
        if self.os_type in ('ubuntu', 'debian'):
            install_command = 'DEBIAN_FRONTEND=noninteractive apt-get install -y {0}'
            update_command = 'DEBIAN_FRONTEND=noninteractive apt-get update -y'
            query_command = 'dpkg-query -W -f=\'${{Status}}\' {} 2>/dev/null | grep -c "ok installed"'
            check_text = '0'

        elif self.os_type in ('centos', 'red', 'fedora'):
            install_command = 'yum install -y {0}'
            update_command = 'yum install -y epel-release'
            query_command = 'rpm -q {0}'
            check_text = 'is not installed'
            
        return install_command, update_command, query_command, check_text

    def check_and_install_packages(self):

        install_command, update_command, query_command, check_text = self.get_install_commands()

        install_list = {'mondatory': [], 'optional': []}

        package_list = {
                'debian 10': {'mondatory': 'apache2 curl wget tar xz-utils unzip rsyslog python3-ldap3 python3-requests python3-ruamel.yaml bzip2', 'optional': ''},
                'debian 9': {'mondatory': 'apache2 curl wget tar xz-utils unzip rsyslog python3-ldap3 python3-requests python3-ruamel.yaml bzip2', 'optional': ''},
                'ubuntu 18': {'mondatory': 'apache2 curl wget xz-utils unzip rsyslog python3-ldap3 net-tools python3-requests python3-ruamel.yaml bzip2', 'optional': ''},
                'ubuntu 20': {'mondatory': 'apache2 curl wget xz-utils unzip rsyslog python3-ldap3 net-tools python3-requests python3-ruamel.yaml bzip2', 'optional': ''},
                'centos 7': {'mondatory': 'httpd mod_ssl curl wget tar xz unzip python3-ldap3 python3-ruamel-yaml rsyslog bzip2', 'optional': ''},
                'centos 8': {'mondatory': 'httpd mod_ssl curl wget tar xz unzip python3-ldap3 python3-ruamel-yaml rsyslog bzip2', 'optional': ''},
                'red 7': {'mondatory': 'httpd mod_ssl curl wget tar xz unzip rsyslog python3-ldap3 python3-requests python3-ruamel-yaml bzip2', 'optional': ''},
                'red 8': {'mondatory': 'httpd mod_ssl curl wget tar xz unzip rsyslog python3-ldap3 python3-requests python3-ruamel-yaml bzip2', 'optional': ''},
                'fedora 22': {'mondatory': 'httpd mod_ssl curl wget tar xz unzip rsyslog python3-ldap3 python3-requests python3-ruamel-yaml bzip2', 'optional': ''},
                }

        os_type_version = self.os_type+' '+self.os_version

        for install_type in install_list:
            for package in package_list[os_type_version][install_type].split():
                if os_type_version in ('centos 7', 'red 7') and package.startswith('python3-'):
                    package_query = package.replace('python3-', 'python36-')
                else:
                    package_query = package
                sout, serr = self.run(query_command.format(package_query), shell=True, get_stderr=True)
                if check_text in sout+serr:
                    self.logIt('Package {0} was not installed'.format(package_query))
                    install_list[install_type].append(package_query)
                else:
                    self.logIt('Package {0} was installed'.format(package_query))

        install = {'mondatory': True, 'optional': False}

        for install_type in install_list:
            if install_list[install_type]:
                packages = " ".join(install_list[install_type])

                if not setupOptions['noPrompt']:
                    if install_type == 'mondatory':
                        print("The following packages are required for Gluu Server")
                        print(packages)
                        r = input("Do you want to install these now? [Y/n] ")
                        if r and r.lower()=='n':
                            install[install_type] = False
                            if install_type == 'mondatory':
                                print("Can not proceed without installing required packages. Exiting ...")
                                sys.exit()

                    elif install_type == 'optional':
                        print("You may need the following packages")
                        print(packages)
                        r = input("Do you want to install these now? [y/N] ")
                        if r and r.lower()=='y':
                            install[install_type] = True

                if install[install_type]:
                    self.logIt("Installing packages " + packages)
                    print("Installing packages", packages)
                    if not self.os_type == 'fedora':
                        sout, serr = self.run(update_command, shell=True, get_stderr=True)
                    self.run(install_command.format(packages), shell=True)

        if self.os_type in ('ubuntu', 'debian'):
            self.run('a2enmod ssl headers proxy proxy_http proxy_ajp', shell=True)
            default_site = '/etc/apache2/sites-enabled/000-default.conf'
            if os.path.exists(default_site):
                os.remove(default_site)

    
    #Couchbase Functions

    def installPackage(self, packageName):
        if self.os_type in ['debian', 'ubuntu']:
            output = self.run([self.cmd_dpkg, '--install', packageName])
        else:
            output = self.run([self.cmd_rpm, '--install', '--verbose', '--hash', packageName])

        return output

    def couchbaseInstall(self):
        coucbase_package = None
        
        tmp = []

        for f in os.listdir(self.couchbasePackageFolder):
            if f.startswith('couchbase-server-enterprise'):
                tmp.append(f)

        if not tmp:
            err_msg = "Couchbase package not found at %s. Exiting with error..." % (self.couchbasePackageFolder)
            self.logIt(err_msg, True)
            sys.exit(2)

        packageName = os.path.join(self.couchbasePackageFolder, max(tmp))
        self.logIt("Found package '%s' for install" % packageName)
        installOutput = self.installPackage(packageName)
        self.post_messages.append(installOutput)

        if self.os_type == 'ubuntu' and self.os_version == '16':
            script_name = os.path.basename(self.couchbaseInitScript)
            target_file = os.path.join('/etc/init.d', script_name)
            self.copyFile(self.couchbaseInitScript, target_file)
            self.run([self.cmd_chmod, '+x', target_file])
            self.run(["/usr/sbin/update-rc.d", script_name, 'defaults'])
            self.run(["/usr/sbin/update-rc.d", script_name, 'enable'])
            self.run_service_command('couchbase-server', 'start')

    def couchebaseCreateCluster(self):
        
        self.logIt("Initializing Couchbase Node")
        result = self.cbm.initialize_node()
        if result.ok:
            self.logIt("Couchbase Node was initialized")
        else:
            self.logIt("Failed to initilize Couchbase Node, reason: "+ result.text, errorLog=True)
        
        #wait a while for node initialization completed
        time.sleep(2)
        
        self.logIt("Renaming Couchbase Node")
        result = self.cbm.rename_node()
        if not result.ok:
            time.sleep(2)
            result = self.cbm.rename_node()

        if result.ok:
            self.logIt("Couchbase Node was renamed")
        else:
            self.logIt("Failed to rename Couchbase Node, reason: "+ result.text, errorLog=True)


        self.logIt("Setting Couchbase index storage mode")
        result = self.cbm.set_index_storage_mode()
        if result.ok:
            self.logIt("Couchbase index storage mode was set")
        else:
            self.logIt("Failed to set Couchbase index storage mode, reason: "+ result.text, errorLog=True)


        self.logIt("Setting Couchbase indexer memory quota to 1GB")
        result = self.cbm.set_index_memory_quta()
        if result.ok:
            self.logIt("Couchbase indexer memory quota was set to 1GB")
        else:
            self.logIt("Failed to set Couchbase indexer memory quota, reason: "+ result.text, errorLog=True)


        self.logIt("Setting up Couchbase Services")
        result = self.cbm.setup_services()
        if result.ok:
            self.logIt("Couchbase services were set up")
        else:
            self.logIt("Failed to setup Couchbase services, reason: "+ result.text, errorLog=True)


        self.logIt("Setting Couchbase Admin password")
        result = self.cbm.set_admin_password()
        if result.ok:
            self.logIt("Couchbase admin password  was set")
        else:
            self.logIt("Failed to set Couchbase admin password, reason: "+ result.text, errorLog=True)
            

    def couchebaseCreateBucket(self, bucketName, bucketType='couchbase', bucketRamsize=1024):
        result = self.cbm.add_bucket(bucketName, bucketRamsize, bucketType)
        self.logIt("Creating bucket {0} with type {1} and ramsize {2}".format(bucketName, bucketType, bucketRamsize))
        if result.ok:
            self.logIt("Bucket {} successfully created".format(bucketName))
        else:
            self.logIt("Failed to create bucket {}, reason: {}".format(bucketName, result.text), errorLog=True)
        #wait 1 second 
        time.sleep(1)

    def exec_n1ql_query(self, query):
        result = self.cbm.exec_query(query)
        if result.ok:
            self.logIt("Query execution was successful: {}".format(query))
        else:
            self.logIt("Failed to execute query {}, reason:".format(query, result.text), errorLog=True)

    def couchbaseExecQuery(self, queryFile):
        self.logIt("Running Couchbase query from file " + queryFile)
        
        query_file = open(queryFile)
        
        for line in query_file:
            query = line.strip()
            if query:
                self.exec_n1ql_query(query)

    def couchbaseMakeIndex(self, bucket, ind):

        if isinstance(ind[0], list):
            attrquoted = []
            attribs = ind[0]
            wherec = ind[1]
            for a in attribs:
                if not '(' in a:
                    attrquoted.append('`{}`'.format(a))
                else:
                    attrquoted.append(a)

            attrquoteds = ', '.join(attrquoted)
            
            index_name = '{0}_static_{1}'.format(bucket, str(uuid.uuid4()).split('-')[1])
            cmd = 'CREATE INDEX `{0}` ON `{1}`({2}) WHERE ({3})'.format(index_name, bucket, attrquoteds, wherec)
        
        else:
            if '(' in ''.join(ind):
                attr_ = ind[0]
                index_name_ = ind[0].replace('(','_').replace(')','_').replace('`','').lower()
                if index_name_.endswith('_'):
                    index_name_ = index_name_[:-1]
                index_name = 'def_{0}_{1}'.format(bucket, index_name_)
            else:
                attr_ = ','.join(['`{}`'.format(a) for a in ind])
                index_name = 'def_{0}_{1}'.format(bucket, '_'.join(ind))

            cmd = 'CREATE INDEX %s ON `%s`(%s) USING GSI WITH {"defer_build":true}' % (index_name, bucket, attr_)

        return cmd, index_name


    def couchebaseCreateIndexes(self, bucket):
        
        self.couchbaseBuckets.append(bucket)
        couchbase_index_str = self.readFile(self.couchbaseIndexJson)
        couchbase_index_str = couchbase_index_str.replace('!bucket_prefix!', self.couchbase_bucket_prefix)
        couchbase_index = json.loads(couchbase_index_str)

        self.logIt("Running Couchbase index creation for " + bucket + " bucket")

        if not os.path.exists(self.n1qlOutputFolder):
            os.mkdir(self.n1qlOutputFolder)
        
        tmp_file = os.path.join(self.n1qlOutputFolder, 'index_%s.n1ql' % bucket)

        with open(tmp_file, 'w') as W:
            index_list = couchbase_index.get(bucket,{})

            index_names = []
            for ind in index_list['attributes']:
                cmd, index_name = self.couchbaseMakeIndex(bucket, ind)
                W.write(cmd+';\n')
                index_names.append(index_name)

            for ind in index_list['static']:
                cmd, index_name = self.couchbaseMakeIndex(bucket, ind)
                W.write(cmd+';\n')

            if index_names:
                W.write('BUILD INDEX ON `%s` (%s) USING GSI;\n' % (bucket, ', '.join(index_names)))

        self.couchbaseExecQuery(tmp_file)


    def checkIfAttributeExists(self, key, atribute,  documents):
        ka = key + '::' + atribute
        retVal = False

        if ka in self.processedKeys:
            return True
         
        for d in documents:
            if d[0] == key:
                if 'changetype' in d[1]:
                    continue
                if atribute in d[1]:
                    retVal = True
                else:
                    self.processedKeys.append(ka)
                    return True
                
        return retVal

    def checkCBRoles(self, buckets=[]):
        result = self.cbm.whoami()
        bc = buckets[:]
        bucket_roles = {}
        if 'roles' in result:
            
            for role in result['roles']:
                if role['role'] == 'admin':
                    self.isCouchbaseUserAdmin = True
                    return True, None

                if not role['bucket_name'] in bucket_roles:
                    bucket_roles[role['bucket_name']] = []

                bucket_roles[role['bucket_name']].append(role['role'])

        for b_ in bc[:]:
            for r_ in self.cb_bucket_roles:
                if not r_ in bucket_roles[b_]:
                    break
            else:
                bc.remove(b_)

        if bc:
            return False, bc

        return True, None

    def import_ldif_couchebase(self, ldif_file_list=[], bucket=None):
        
        self.processedKeys = []

        key_prefixes = {}
        for cb in self.couchbaseBucketDict:
            for prefix in self.couchbaseBucketDict[cb]['document_key_prefix']:
                key_prefixes[prefix] = cb

        if not ldif_file_list:
            ldif_file_list = self.ldif_files[:]
        
        for ldif in ldif_file_list:
            self.logIt("Importing ldif file %s to Couchebase bucket %s" % (ldif, bucket))
            documents = gluu_utils.get_documents_from_ldif(ldif)

            ldif_base_name = os.path.basename(ldif)
            name, ext = os.path.splitext(ldif_base_name)

            if not os.path.exists(self.n1qlOutputFolder):
                os.mkdir(self.n1qlOutputFolder)

            tmp_file = os.path.join(self.n1qlOutputFolder, name+'.n1ql')
            
            with open(tmp_file, 'w') as o:
                for e in documents:
                    if bucket:
                        cur_bucket = bucket
                    else:
                        n_ = e[0].find('_')
                        document_key_prefix = e[0][:n_+1]
                        cur_bucket = self.couchbase_bucket_prefix + '_' + key_prefixes[document_key_prefix] if document_key_prefix in key_prefixes else 'gluu'

                    query = ''

                    if 'changetype' in e[1]:
                        if 'replace' in e[1]:
                            query = 'UPDATE `%s` USE KEYS "%s" SET %s="%s";\n' % (cur_bucket, e[0], e[1]['replace'], e[1][e[1]['replace']])
                        elif 'add' in e[1]:
                            for m in e[1][e[1]['add']]:
                                if self.checkIfAttributeExists(e[0], e[1]['add'],  documents):
                                    query += 'UPDATE `%s` USE KEYS "%s" SET %s=["%s"];\n' % (cur_bucket, e[0], e[1]['add'], m)
                                else:
                                    query += 'UPDATE `%s` USE KEYS "%s" SET %s=ARRAY_APPEND(%s, "%s");\n' % (cur_bucket, e[0], e[1]['add'], e[1]['add'], m)
                    else:
                        query = 'UPSERT INTO `%s` (KEY, VALUE) VALUES ("%s", %s);\n' % (cur_bucket, e[0], json.dumps(e[1]))

                    o.write(query)

            self.couchbaseExecQuery(tmp_file)

    def checkIfGluuBucketReady(self):

        for i in range(12):
            self.logIt("Checking if gluu bucket is ready for N1QL query. Try %d ..." % (i+1))
            cbm_result = self.cbm.test_connection()
            if cbm_result.ok:
                return True
            else:
                time.sleep(5)
        print("Couchbase server was not ready. Giving up" + str(cbm_result.reason))
        sys.exit(1)

    def couchbaseSSL(self):
        self.logIt("Exporting Couchbase SSL certificate to " + self.couchebaseCert)
        
        for cb_host in re_split_host.findall(self.couchbase_hostname):

            cbm_ = CBM(cb_host.strip(), self.couchebaseClusterAdmin, self.cb_password)
            cert = cbm_.get_certificate()
            with open(self.couchebaseCert, 'w') as w:
                w.write(cert)

            cmd_args = [self.cmd_keytool, "-import", "-trustcacerts", "-alias", "%s_couchbase" % cb_host, \
                      "-file", self.couchebaseCert, "-keystore", self.couchbaseTrustStoreFn, \
                      "-storepass", self.couchbaseTrustStorePass, "-noprompt"]

            self.run(cmd_args)

    def couchbaseDict(self):
        prop_dict = {
                    'hostname': ','.join(re_split_host.findall(self.couchbase_hostname)),
                    'couchbase_server_user': self.couchebaseClusterAdmin,
                    'encoded_couchbase_server_pw': self.encoded_cb_password,
                    'couchbase_buckets': ', '.join(self.couchbaseBuckets),
                    'default_bucket': self.couchbase_bucket_prefix,
                    'encryption_method': 'SSHA-256',
                    'ssl_enabled': 'true',
                    'couchbaseTrustStoreFn': self.couchbaseTrustStoreFn,
                    'encoded_couchbaseTrustStorePass': self.encoded_couchbaseTrustStorePass,
                    'certFolder': self.certFolder,
                    'gluuOptPythonFolder': self.gluuOptPythonFolder
                    }

        couchbase_mappings = []

        for group in list(self.couchbaseBucketDict.keys())[1:]:
            bucket = self.couchbase_bucket_prefix if group == 'default' else self.couchbase_bucket_prefix + '_' + group
            if bucket in self.couchbaseBuckets:
                cb_key = 'couchbase_{}_mapping'.format(group)
                if self.mappingLocations[group] == 'couchbase':
                    if self.couchbaseBucketDict[group]['mapping']:
                        couchbase_mappings.append('bucket.{}_{}.mapping: {}'.format(self.couchbase_bucket_prefix, group, self.couchbaseBucketDict[group]['mapping']))
                        self.templateRenderingDict[cb_key] = self.couchbaseBucketDict[group]['mapping']
                    else:
                         self.templateRenderingDict[cb_key] = ''
                else:
                    self.templateRenderingDict[cb_key] = ''

        prop_dict['couchbase_mappings'] = '\n'.join(couchbase_mappings)
        couchbase_test_mappings = [ 'config.' + mapping for mapping in couchbase_mappings ]
        prop_dict['couchbase_test_mappings'] = '\n'.join(couchbase_test_mappings)

        return prop_dict
        
    def couchbaseProperties(self):
        prop_file = os.path.basename(self.gluuCouchebaseProperties)
        prop = open(os.path.join(self.templateFolder, prop_file)).read()

        prop_dict = self.couchbaseDict()

        prop = prop % prop_dict
        
        out_file = os.path.join(self.outputFolder, prop_file)
        self.writeFile(out_file, prop)
        self.writeFile(self.gluuCouchebaseProperties, prop)


    def create_couchbase_buckets(self):
        #Determine ram_size for buckets
        system_info = self.cbm.get_system_info()
        couchbaseClusterRamsize = (system_info['storageTotals']['ram']['quotaTotal'] - system_info['storageTotals']['ram']['quotaUsed']) / (1024*1024)

        couchbase_mappings = self.getMappingType('couchbase')

        min_cb_ram = 0
        
        for group in couchbase_mappings:
             min_cb_ram += self.couchbaseBucketDict[group]['memory_allocation']
        
        min_cb_ram += self.couchbaseBucketDict['default']['memory_allocation']

        if couchbaseClusterRamsize < min_cb_ram:
            print("Available quota on couchbase server is less than {} MB. Exiting installation".format(min_cb_ram))
            sys.exit(1)

        self.logIt("Ram size for Couchbase buckets was determined as {0} MB".format(couchbaseClusterRamsize))

        min_cb_ram *= 1.0

        existing_buckets = []
        r = self.cbm.get_buckets()

        if r.ok:
            b_ = r.json()
            existing_buckets = [ bucket['name'] for bucket in b_ ]

        if not self.couchbase_bucket_prefix in existing_buckets:

            if self.mappingLocations['default'] != 'couchbase':
                self.couchebaseCreateBucket(self.couchbase_bucket_prefix, bucketRamsize=100)
            else:
                bucketRamsize = int((self.couchbaseBucketDict['default']['memory_allocation']/min_cb_ram)*couchbaseClusterRamsize)
                self.couchebaseCreateBucket(self.couchbase_bucket_prefix, bucketRamsize=bucketRamsize)

        if self.mappingLocations['default'] == 'couchbase':
            self.couchebaseCreateIndexes(self.couchbase_bucket_prefix)


        for group in couchbase_mappings:
            bucket = '{}_{}'.format(self.couchbase_bucket_prefix, group)
            if not bucket in existing_buckets:
                bucketRamsize = int((self.couchbaseBucketDict[group]['memory_allocation']/min_cb_ram)*couchbaseClusterRamsize)
                self.couchebaseCreateBucket(bucket, bucketRamsize=bucketRamsize)
            else:
                self.logIt("Bucket {} already exists, not creating".format(bucket))

            self.couchebaseCreateIndexes(bucket)

        if self.installSaml:
            
            shib_user = 'couchbaseShibUser'
            shib_user_password = self.couchbaseShibUserPassword
            shib_user_roles = 'query_select[*]'
            if self.isCouchbaseUserAdmin:
                self.logIt("Creating couchbase readonly user for shib")
                self.cbm.create_user(shib_user, shib_user_password, 'Shibboleth IDP', shib_user_roles)
            else:
                user_role_msg = "Please create a user on Couchbase Server with the following credidentals and roles"
                if not thread_queue:
                    user_role_msg = gluu_utils.colors.WARNING + user_role_msg + gluu_utils.colors.ENDC
                self.post_messages.append(user_role_msg)
                self.post_messages.append('Username: {}'.format(shib_user))
                self.post_messages.append('Password: {}'.format(shib_user_password))
                self.post_messages.append('Roles: {}'.format(shib_user_roles))

    def install_couchbase_server(self):

        if not self.cbm:
             self.cbm = CBM(self.couchbase_hostname, self.couchebaseClusterAdmin, self.cb_password)

        if self.cb_install == LOCAL:
            self.couchbaseInstall()
            self.checkIfGluuBucketReady()
            self.couchebaseCreateCluster()

        self.couchbaseSSL()

        self.create_couchbase_buckets()

        couchbase_mappings = self.getMappingType('couchbase')

        if self.mappingLocations['default'] == 'couchbase':
            self.import_ldif_couchebase(self.couchbaseBucketDict['default']['ldif'], self.couchbase_bucket_prefix)

        for group in couchbase_mappings:
            bucket = '{}_{}'.format(self.couchbase_bucket_prefix, group)
            if self.couchbaseBucketDict[group]['ldif']:
                self.import_ldif_couchebase(self.couchbaseBucketDict[group]['ldif'], bucket)

        self.couchbaseProperties()

    def getLdapConnection(self):

        ldap_server = Server(self.ldap_hostname, port=int(self.ldaps_port), use_ssl=True)
        ldap_conn = Connection(
                    ldap_server,
                    user=self.ldap_binddn,
                    password=self.ldapPass,
                    )
        ldap_conn.bind()

        return ldap_conn


    def create_test_client_keystore(self):
        self.logIt("Creating client_keystore.jks")
        client_keystore_fn = os.path.join(self.outputFolder, 'test/oxauth/client/client_keystore.jks')
        keys_json_fn =  os.path.join(self.outputFolder, 'test/oxauth/client/keys_client_keystore.json')
        
        args = [self.cmd_keytool, '-genkey', '-alias', 'dummy', '-keystore', 
                    client_keystore_fn, '-storepass', 'secret', '-keypass', 
                    'secret', '-dname', 
                    "'{}'".format(self.default_openid_jks_dn_name)
                    ]

        self.run(' '.join(args), shell=True)

        args = [self.cmd_java, '-Dlog4j.defaultInitOverride=true',
                '-cp', self.non_setup_properties['oxauth_client_jar_fn'], self.non_setup_properties['key_gen_path'],
                '-keystore', client_keystore_fn,
                '-keypasswd', 'secret',
                '-sig_keys', self.default_key_algs,
                '-enc_keys', self.default_key_algs,
                '-dnname', "'{}'".format(self.default_openid_jks_dn_name),
                '-expiration', '365','>', keys_json_fn]

        cmd = ' '.join(args)
        
        self.run(cmd, shell=True)

        self.copyFile(client_keystore_fn, os.path.join(self.outputFolder, 'test/oxauth/server'))
        self.copyFile(keys_json_fn, os.path.join(self.outputFolder, 'test/oxauth/server'))

    def load_test_data(self):
        self.logIt("Loading test ldif files")

        if not self.installPassport:
            self.generate_passport_configuration()

        ox_auth_test_ldif = os.path.join(self.outputFolder, 'test/oxauth/data/oxauth-test-data.ldif')
        ox_auth_test_user_ldif = os.path.join(self.outputFolder, 'test/oxauth/data/oxauth-test-data-user.ldif')
        
        scim_test_ldif = os.path.join(self.outputFolder, 'test/scim-client/data/scim-test-data.ldif')
        scim_test_user_ldif = os.path.join(self.outputFolder, 'test/scim-client/data/scim-test-data-user.ldif')

        ldif_files = [ox_auth_test_ldif, scim_test_ldif]
        ldif_user_files = [ox_auth_test_user_ldif, scim_test_user_ldif]

        cb_hosts = re_split_host.findall(self.couchbase_hostname)

        if self.mappingLocations['default'] == 'ldap':
            self.import_ldif_opendj(ldif_files)
        else:
            cb_host = cb_hosts[int(self.cb_query_node)]
            self.cbm = CBM(cb_host, self.couchebaseClusterAdmin, self.cb_password)
            self.import_ldif_couchebase(ldif_files)

        if self.mappingLocations['user'] == 'ldap':
            self.import_ldif_opendj(ldif_user_files)
        else:
            cb_host = cb_hosts[int(self.cb_query_node)]
            self.cbm = CBM(cb_host, self.couchebaseClusterAdmin, self.cb_password)
            bucket = '{}_user'.format(self.couchbase_bucket_prefix)
            self.import_ldif_couchebase(ldif_user_files,  bucket='gluu_user')

        apache_user = 'www-data'
        if self.os_type in ('red', 'centos', 'fedora'):
            apache_user = 'apache'


        # Client keys deployment
        self.run(['wget', '--no-check-certificate', 'https://raw.githubusercontent.com/GluuFederation/oxAuth/master/Client/src/test/resources/oxauth_test_client_keys.zip', '-O', '/var/www/html/oxauth_test_client_keys.zip'])
        self.run(['unzip', '-o', '/var/www/html/oxauth_test_client_keys.zip', '-d', '/var/www/html/'])
        self.run(['rm', '-rf', 'oxauth_test_client_keys.zip'])
        self.run(['chown', '-R', 'root:'+apache_user, '/var/www/html/oxauth-client'])


        oxAuthConfDynamic_changes = (
                                    ('dynamicRegistrationCustomObjectClass', 'oxAuthClientCustomAttributes'),
                                    ('dynamicRegistrationCustomAttributes', [ "oxAuthTrustedClient", "myCustomAttr1", "myCustomAttr2", "oxIncludeClaimsInIdToken" ]),
                                    ('dynamicRegistrationExpirationTime', 86400),
                                    ('dynamicGrantTypeDefault', [ "authorization_code", "implicit", "password", "client_credentials", "refresh_token", "urn:ietf:params:oauth:grant-type:uma-ticket" ]),
                                    ('legacyIdTokenClaims', True),
                                    ('authenticationFiltersEnabled', True),
                                    ('clientAuthenticationFiltersEnabled', True),
                                    ('keyRegenerationEnabled',True),
                                    ('openidScopeBackwardCompatibility', False),
                                    )


        custom_scripts = ('2DAF-F995', '2DAF-F996', '4BBE-C6A8')
        
        config_servers = ['{0}:{1}'.format(self.hostname, self.ldaps_port)]
        

        if self.mappingLocations['default'] == 'ldap':
            # oxAuth config changes
            ldap_conn = self.getLdapConnection()

            dn = 'ou=oxauth,ou=configuration,o=gluu'
            ldap_conn.search(
                            search_base=dn,
                            search_scope=BASE,
                            search_filter='(objectclass=*)',
                            attributes=['oxAuthConfDynamic']
                        )

            oxAuthConfDynamic = json.loads(ldap_conn.response[0]['attributes']['oxAuthConfDynamic'][0])

            for k, v in oxAuthConfDynamic_changes:
                oxAuthConfDynamic[k] = v

            oxAuthConfDynamic_js = json.dumps(oxAuthConfDynamic, indent=2)
            ldap_conn.modify(dn, {'oxAuthConfDynamic': [MODIFY_REPLACE, oxAuthConfDynamic_js]})

            # Enable custom scripts
            for inum in custom_scripts:
                dn = 'inum={0},ou=scripts,o=gluu'.format(inum)
                ldap_conn.modify(dn, {'oxEnabled': [MODIFY_REPLACE, 'true']})



            # Update LDAP schema
            self.copyFile(os.path.join(self.outputFolder, 'test/oxauth/schema/102-oxauth_test.ldif'), '/opt/opendj/config/schema/')
            self.copyFile(os.path.join(self.outputFolder, 'test/scim-client/schema/103-scim_test.ldif'), '/opt/opendj/config/schema/')

            schema_fn = os.path.join(self.openDjSchemaFolder,'77-customAttributes.ldif')

            obcl_parser = gluu_utils.myLdifParser(schema_fn)
            obcl_parser.parse()

            for i, o in enumerate(obcl_parser.entries[0][1]['objectClasses']):
                objcl = ObjectClass(o)
                if 'gluuCustomPerson' in objcl.tokens['NAME']:
                    may_list = list(objcl.tokens['MAY'])
                    for a in ('scimCustomFirst','scimCustomSecond', 'scimCustomThird'):
                        if not a in may_list:
                            may_list.append(a)
                    
                    objcl.tokens['MAY'] = tuple(may_list)
                    obcl_parser.entries[0][1]['objectClasses'][i] = objcl.getstr()

            tmp_fn = '/tmp/77-customAttributes.ldif'
            with open(tmp_fn, 'wb') as w:
                ldif_writer = LDIFWriter(w)
                for dn, entry in obcl_parser.entries:                
                    ldif_writer.unparse(dn, entry)

            self.copyFile(tmp_fn, self.openDjSchemaFolder)
            cwd = os.path.join(self.ldapBaseFolder, 'bin')
            dsconfigCmd = (
                '{} --trustAll --no-prompt --hostname {} --port {} '
                '--bindDN "{}" --bindPasswordFile /home/ldap/.pw set-connection-handler-prop '
                '--handler-name "LDAPS Connection Handler" --set listen-address:0.0.0.0'
                    ).format(
                        self.ldapDsconfigCommand, 
                        self.ldap_hostname, 
                        self.ldap_admin_port,
                        self.ldap_binddn
                    )
            
            self.run(['/bin/su', 'ldap', '-c', dsconfigCmd], cwd=cwd)
            
            ldap_conn.unbind()
            
            self.run_service_command('opendj', 'restart')

            for atr in ('myCustomAttr1', 'myCustomAttr2'):
                cmd = (
                    'create-backend-index --backend-name userRoot --type generic '
                    '--index-name {} --set index-type:equality --set index-entry-limit:4000 '
                    '--hostName {} --port {} --bindDN "{}" -j /home/ldap/.pw '
                    '--trustAll --noPropertiesFile --no-prompt'
                    ).format(
                        atr, 
                        self.ldap_hostname,
                        self.ldap_admin_port, 
                        self.ldap_binddn
                    )
                
                dsconfigCmd = '{1} {2}'.format(self.ldapBaseFolder, self.ldapDsconfigCommand, cmd)
                self.run(['/bin/su', 'ldap', '-c', dsconfigCmd], cwd=cwd)
            
            
            ldap_conn = self.getLdapConnection()
            
            dn = 'ou=configuration,o=gluu'

            ldap_conn.search(
                search_base=dn,
                search_scope=BASE,
                search_filter='(objectclass=*)',
                attributes=['oxIDPAuthentication']
            )
            
            
            oxIDPAuthentication = json.loads(ldap_conn.response[0]['attributes']['oxIDPAuthentication'][0])
            oxIDPAuthentication['config']['servers'] = config_servers
            oxIDPAuthentication_js = json.dumps(oxIDPAuthentication, indent=2)
            ldap_conn.modify(dn, {'oxIDPAuthentication': [MODIFY_REPLACE, oxIDPAuthentication_js]})

            ldap_conn.unbind()
            
        else:
            
            for k, v in oxAuthConfDynamic_changes:
                query = 'UPDATE gluu USE KEYS "configuration_oxauth" set gluu.oxAuthConfDynamic.{0}={1}'.format(k, json.dumps(v))
                self.exec_n1ql_query(query)
 
            for inum in custom_scripts:
                query = 'UPDATE gluu USE KEYS "scripts_{0}" set gluu.oxEnabled=true'.format(inum)
                self.exec_n1ql_query(query)

            self.exec_n1ql_query('CREATE INDEX def_gluu_myCustomAttr1 ON `gluu`(myCustomAttr1) USING GSI WITH {"defer_build":true}')
            self.exec_n1ql_query('CREATE INDEX def_gluu_myCustomAttr2 ON `gluu`(myCustomAttr2) USING GSI WITH {"defer_build":true}')
            self.exec_n1ql_query('BUILD INDEX ON `gluu` (def_gluu_myCustomAttr1, def_gluu_myCustomAttr2)')

            #query = 'UPDATE gluu USE KEYS "configuration" set gluu.oxIDPAuthentication.config.servers = {0}'.format(json.dumps(config_servers))
            #self.exec_n1ql_query(query)


        self.create_test_client_keystore()

        # Disable token binding module
        if self.os_type+self.os_version in ('ubuntu20', 'ubuntu18'):
            self.run(['a2dismod', 'mod_token_binding'])
            self.run_service_command('apache2', 'restart')

        self.run_service_command('oxauth', 'restart')
        
        # Prepare for tests run
        #install_command, update_command, query_command, check_text = self.get_install_commands()
        #self.run_command(install_command.format('git'))
        #self.run([self.cmd_mkdir, '-p', 'oxAuth/Client/profiles/ce_test'])
        #self.run([self.cmd_mkdir, '-p', 'oxAuth/Server/profiles/ce_test'])
        # Todo: Download and unzip file test_data.zip from CE server.
        # Todo: Copy files from unziped folder test/oxauth/client/* into oxAuth/Client/profiles/ce_test
        # Todo: Copy files from unziped folder test/oxauth/server/* into oxAuth/Server/profiles/ce_test
        #self.run([self.cmd_keytool, '-import', '-alias', 'seed22.gluu.org_httpd', '-keystore', 'cacerts', '-file', '%s/httpd.crt' % self.certFolder, '-storepass', 'changeit', '-noprompt'])
        #self.run([self.cmd_keytool, '-import', '-alias', 'seed22.gluu.org_opendj', '-keystore', 'cacerts', '-file', '%s/opendj.crt' % self.certFolder, '-storepass', 'changeit', '-noprompt'])
 

    def load_test_data_exit(self):
        print("Loading test data")
        prop_file = os.path.join(self.install_dir, 'setup.properties.last')
        
        if not os.path.exists(prop_file):
            prop_file += '.enc'
            if not os.path.exists(prop_file):
                print("setup.properties.last or setup.properties.last.enc were not found, exiting.")
                sys.exit(1)

        self.load_properties(prop_file)
        self.createLdapPw()
        self.load_test_data()
        self.deleteLdapPw()
        print("Test data loaded. Exiting ...")
        sys.exit()

    def fix_systemd_script(self):
        oxauth_systemd_script_fn = '/lib/systemd/system/oxauth.service'
        if os.path.exists(oxauth_systemd_script_fn):
            oxauth_systemd_script = open(oxauth_systemd_script_fn).read()
            changed = False
            
            if self.cb_install == LOCAL:
                oxauth_systemd_script = oxauth_systemd_script.replace('After=opendj.service', 'After=couchbase-server.service')
                oxauth_systemd_script = oxauth_systemd_script.replace('Requires=opendj.service', 'Requires=couchbase-server.service')
                changed = True
            
            elif self.wrends_install != LOCAL:
                oxauth_systemd_script = oxauth_systemd_script.replace('After=opendj.service', '')
                oxauth_systemd_script = oxauth_systemd_script.replace('Requires=opendj.service', '')
                changed = True
                
            if changed:
                with open(oxauth_systemd_script_fn, 'w') as w:
                    w.write(oxauth_systemd_script)
                self.run(['rm', '-f', '/lib/systemd/system/opendj.service'])
                self.run([self.systemctl, 'daemon-reload'])


    def install_oxd(self):
        self.logIt("Installing oxd server...")
        oxd_root = '/opt/oxd-server/'
        oxd_server_yml_fn = os.path.join(oxd_root, 'conf/oxd-server.yml')
        
        self.run(['tar', '-zxf', self.oxd_package, '-C', '/opt'])
        self.run(['chown', '-R', 'jetty:jetty', oxd_root])
        
        service_file = os.path.join(oxd_root, 'oxd-server.service')
        if os.path.exists(service_file):
            self.run(['cp', service_file, '/lib/systemd/system'])
        else:
            self.run([self.cmd_ln, service_file, '/etc/init.d/oxd-server'])
            self.run(['update-rc.d', 'oxd-server', 'defaults'])

        self.run([
                'cp', 
                os.path.join(self.install_dir, 'static/oxd/oxd-server.default'), 
                os.path.join(self.osDefault, 'oxd-server')
                ])
        log_dir = '/var/log/oxd-server/'
        self.run(['mkdir', '-p', log_dir])
        log_file = os.path.join(log_dir, 'oxd-server.log')
        if not os.path.exists(log_file):
            open(log_file, 'w').close()

        self.run(['chown', '-R', 'jetty:jetty', log_dir])
        
        for fn in glob.glob(os.path.join(oxd_root,'bin/*')):
            self.run(['chmod', '+x', fn])


        yml_str = self.readFile(oxd_server_yml_fn)
        oxd_yaml = ruamel.yaml.load(yml_str, ruamel.yaml.RoundTripLoader)

        if 'bind_ip_addresses' in oxd_yaml:
            oxd_yaml['bind_ip_addresses'].append(self.ip)
        else:
            for i, k in enumerate(oxd_yaml):
                if k == 'storage':
                    break
            else:
                i = 1
            oxd_yaml.insert(i, 'bind_ip_addresses',  [self.ip])


        if self.oxd_use_gluu_storage:
            oxd_server_yml_fn = os.path.join(oxd_root, 'conf/oxd-server.yml')

            oxd_yaml['storage_configuration'].pop('dbFileLocation')

            oxd_yaml['storage'] = 'gluu_server_configuration'

            oxd_yaml['storage_configuration']['baseDn'] = 'o=gluu'
            oxd_yaml['storage_configuration']['type'] = self.gluu_properties_fn

            if self.persistence_type in ('ldap', 'hybrid'):
                oxd_yaml['storage_configuration']['connection'] = self.ox_ldap_properties
            else:
                oxd_yaml['storage_configuration']['connection'] = self.gluuCouchebaseProperties

            oxd_yaml['storage_configuration']['salt'] = os.path.join(self.configFolder, "salt")

        yml_str = ruamel.yaml.dump(oxd_yaml, Dumper=ruamel.yaml.RoundTripDumper)
        self.writeFile(oxd_server_yml_fn, yml_str)

        # generate oxd-server.keystore for the hostname
        self.run([
            self.opensslCommand,
            'req', '-x509', '-newkey', 'rsa:4096', '-nodes',
            '-out', '/tmp/oxd.crt',
            '-keyout', '/tmp/oxd.key',
            '-days', '3650',
            '-subj', '/C={}/ST={}/L={}/O={}/CN={}/emailAddress={}'.format(self.countryCode, self.state, self.city, self.orgName, self.hostname, self.admin_email),
            ])

        self.run([
            self.opensslCommand,
            'pkcs12', '-export',
            '-in', '/tmp/oxd.crt',
            '-inkey', '/tmp/oxd.key',
            '-out', '/tmp/oxd.p12',
            '-name', self.hostname,
            '-passout', 'pass:example'
            ])

        self.run([
            self.cmd_keytool,
            '-importkeystore',
            '-deststorepass', 'example',
            '-destkeypass', 'example',
            '-destkeystore', '/tmp/oxd.keystore',
            '-srckeystore', '/tmp/oxd.p12',
            '-srcstoretype', 'PKCS12',
            '-srcstorepass', 'example',
            '-alias', self.hostname,
            ])

        oxd_keystore_fn = os.path.join(oxd_root, 'conf/oxd-server.keystore')
        self.run(['cp', '-f', '/tmp/oxd.keystore', oxd_keystore_fn])
        self.run(['chown', 'jetty:jetty', oxd_keystore_fn])
        
        for f in ('/tmp/oxd.crt', '/tmp/oxd.key', '/tmp/oxd.p12', '/tmp/oxd.keystore'):
            self.run(['rm', '-f', f])


        self.enable_service_at_start('oxd-server')

    def install_casa(self):
        self.logIt("Installing Casa...")

        self.run(['chmod', 'g+w', '/opt/gluu/python/libs'])
        self.logIt("Copying casa.war into jetty webapps folder...")
        self.installJettyService(self.jetty_app_configuration['casa'])

        jettyServiceWebapps = os.path.join(self.jetty_base,
                                            'casa',
                                            'webapps'
                                            )

        self.copyFile(
                    os.path.join(self.distGluuFolder, 'casa.war'),
                    jettyServiceWebapps
                    )

        jettyServiceOxAuthCustomLibsPath = os.path.join(self.jetty_base,
                                                        "oxauth", 
                                                        "custom/libs"
                                                        )
        
        self.copyFile(
                os.path.join(self.distGluuFolder, 
                'twilio-{0}.jar'.format(self.twilio_version)), 
                jettyServiceOxAuthCustomLibsPath
                )
        
        self.copyFile(
                os.path.join(self.distGluuFolder, 'jsmpp-{}.jar'.format(self.jsmmp_version)), 
                jettyServiceOxAuthCustomLibsPath
                )
        
        self.run([self.cmd_chown, '-R', 'jetty:jetty', jettyServiceOxAuthCustomLibsPath])

        # Make necessary Directories for Casa
        for path in ('/opt/gluu/jetty/casa/static/', '/opt/gluu/jetty/casa/plugins'):
            if not os.path.exists(path):
                self.run(['mkdir', '-p', path])
                self.run(['chown', '-R', 'jetty:jetty', path])
        
        #Adding twilio jar path to oxauth.xml
        oxauth_xml_fn = '/opt/gluu/jetty/oxauth/webapps/oxauth.xml'
        if os.path.exists(oxauth_xml_fn):
            
            class CommentedTreeBuilder(ElementTree.TreeBuilder):
                def comment(self, data):
                    self.start(ElementTree.Comment, {})
                    self.data(data)
                    self.end(ElementTree.Comment)

            parser = ElementTree.XMLParser(target=CommentedTreeBuilder())
            tree = ElementTree.parse(oxauth_xml_fn, parser)
            root = tree.getroot()

            xml_headers = '<?xml version="1.0"  encoding="ISO-8859-1"?>\n<!DOCTYPE Configure PUBLIC "-//Jetty//Configure//EN" "http://www.eclipse.org/jetty/configure_9_0.dtd">\n\n'

            for element in root:
                if element.tag == 'Set' and element.attrib.get('name') == 'extraClasspath':
                    break
            else:
                element = ElementTree.SubElement(root, 'Set', name='extraClasspath')
                element.text = ''

            extraClasspath_list = element.text.split(',')

            for ecp in extraClasspath_list[:]:
                if (not ecp) or re.search('twilio-(.*)\.jar', ecp) or re.search('jsmpp-(.*)\.jar', ecp):
                    extraClasspath_list.remove(ecp)

            extraClasspath_list.append('./custom/libs/twilio-{}.jar'.format(self.twilio_version))
            extraClasspath_list.append('./custom/libs/jsmpp-{}.jar'.format(self.jsmmp_version))
            element.text = ','.join(extraClasspath_list)

            self.writeFile(oxauth_xml_fn, xml_headers+ElementTree.tostring(root).decode('utf-8'))

        pylib_folder = os.path.join(self.gluuOptPythonFolder, 'libs')
        for script_fn in glob.glob(os.path.join(self.staticFolder, 'casa/scripts/*.*')):
            self.run(['cp', script_fn, pylib_folder])

        self.enable_service_at_start('casa')

    def parse_url(self, url):
        o = urlparse(url)
        return o.hostname, o.port


    def install_gluu_radius_base(self):

        if not self.gluu_radius_client_id:
            self.gluu_radius_client_id = '1701.'  + str(uuid.uuid4())

        source_dir = os.path.join(self.staticFolder, 'radius')
        conf_dir = os.path.join(self.gluuBaseFolder, 'conf/radius/')
        self.createDirs(conf_dir)

        self.radius_jwt_pass = self.getPW()
        radius_jwt_pass = self.obscure(self.radius_jwt_pass)
        radius_jks_fn = os.path.join(self.certFolder, 'gluu-radius.jks')
        
        self.raidus_client_jwks = self.gen_openid_jwks_jks_keys(radius_jks_fn, self.radius_jwt_pass)

        raidus_client_jwks = ''.join(self.raidus_client_jwks).replace('\'','').replace(',,',',').replace('{,','{')
        
        raidus_client_jwks = json.loads(raidus_client_jwks)
        
        self.templateRenderingDict['radius_jwt_pass'] = radius_jwt_pass


        raidus_client_jwks_json = json.dumps(raidus_client_jwks, indent=2)
        
        self.templateRenderingDict['gluu_ro_client_base64_jwks'] = base64.encodestring(raidus_client_jwks_json.encode('utf-8')).decode('utf-8').replace(' ','').replace('\n','')

        for k in raidus_client_jwks['keys']:
            if k.get('alg') == 'RS512':
                self.templateRenderingDict['radius_jwt_keyId'] = k['kid']
        
        self.gluu_ro_pw = self.getPW()
        self.gluu_ro_encoded_pw = self.obscure(self.gluu_ro_pw)

        scripts_dir = os.path.join(source_dir,'scripts')

        for scriptFile, scriptName in ( ('super_gluu_ro_session.py', 'super_gluu_ro_session_script'),
                            ('super_gluu_ro.py','super_gluu_ro_script'),
                          ):
            
            scriptFilePath = os.path.join(scripts_dir, scriptFile)
            base64ScriptFile = self.generate_base64_file(scriptFilePath, 1)
            self.templateRenderingDict[scriptName] = base64ScriptFile

        for tmp_ in ('gluu_radius_base.ldif', 'gluu_radius_clients.ldif', 'gluu_radius_server.ldif'):
            tmp_fn = os.path.join(source_dir, 'templates', tmp_)
            self.renderTemplateInOut(tmp_fn, os.path.join(source_dir, 'templates'), self.outputFolder)
        
        self.renderTemplateInOut('gluu-radius.properties', os.path.join(source_dir, 'etc/gluu/conf/radius/'), conf_dir)


        ldif_file_clients = os.path.join(self.outputFolder, 'gluu_radius_clients.ldif')
        ldif_file_base = os.path.join(self.outputFolder, 'gluu_radius_base.ldif')

        if self.mappingLocations['default'] == 'ldap':
            self.import_ldif_opendj([ldif_file_base, ldif_file_clients])
        else:
            self.import_ldif_couchebase([ldif_file_base, ldif_file_clients])

        if self.installGluuRadius:
            self.install_gluu_radius()

    def install_gluu_radius(self):

        self.pbar.progress("radius", "Installing Gluu components: Radius", False)
        
        radius_libs = os.path.join(self.distGluuFolder, 'gluu-radius-libs.zip')
        radius_jar = os.path.join(self.distGluuFolder, 'super-gluu-radius-server.jar')
        conf_dir = os.path.join(self.gluuBaseFolder, 'conf/radius/')
        ldif_file_server = os.path.join(self.outputFolder, 'gluu_radius_server.ldif')
        source_dir = os.path.join(self.staticFolder, 'radius')
        logs_dir = os.path.join(self.radius_dir,'logs')

        if not os.path.exists(logs_dir):
            self.run([self.cmd_mkdir, '-p', logs_dir])

        self.run(['unzip', '-n', '-q', radius_libs, '-d', self.radius_dir ])
        self.copyFile(radius_jar, self.radius_dir)

        if self.mappingLocations['default'] == 'ldap':
            schema_ldif = os.path.join(source_dir, 'schema/98-radius.ldif')
            self.import_ldif_opendj([schema_ldif])
            self.import_ldif_opendj([ldif_file_server])
        else:
            self.import_ldif_couchebase([ldif_file_server])
        
        self.copyFile(os.path.join(source_dir, 'etc/default/gluu-radius'), self.osDefault)
        self.copyFile(os.path.join(source_dir, 'etc/gluu/conf/radius/gluu-radius-logging.xml'), conf_dir)
        self.copyFile(os.path.join(source_dir, 'scripts/gluu_common.py'), os.path.join(self.gluuOptPythonFolder, 'libs'))

        
        self.copyFile(os.path.join(source_dir, 'etc/init.d/gluu-radius'), '/etc/init.d')
        self.run([self.cmd_chmod, '+x', '/etc/init.d/gluu-radius'])
        
        if self.os_type+self.os_version == 'ubuntu16':
            self.run(['update-rc.d', 'gluu-radius', 'defaults'])
        else:
            self.copyFile(os.path.join(source_dir, 'systemd/gluu-radius.service'), '/usr/lib/systemd/system')
            self.run([self.systemctl, 'daemon-reload'])
        
        #create empty gluu-radius.private-key.pem
        gluu_radius_private_key_fn = os.path.join(self.certFolder, 'gluu-radius.private-key.pem')
        self.writeFile(gluu_radius_private_key_fn, '')
        
        self.run([self.cmd_chown, '-R', 'radius:gluu', self.radius_dir])
        self.run([self.cmd_chown, '-R', 'root:gluu', conf_dir])
        self.run([self.cmd_chown, 'root:gluu', os.path.join(self.gluuOptPythonFolder, 'libs/gluu_common.py')])

        self.run([self.cmd_chown, 'radius:gluu', os.path.join(self.certFolder, 'gluu-radius.jks')])
        self.run([self.cmd_chown, 'radius:gluu', os.path.join(self.certFolder, 'gluu-radius.private-key.pem')])

        self.run([self.cmd_chmod, '755', self.radius_dir])
        self.run([self.cmd_chmod, '660', os.path.join(self.certFolder, 'gluu-radius.jks')])
        self.run([self.cmd_chmod, '660', os.path.join(self.certFolder, 'gluu-radius.private-key.pem')])

        self.enable_service_at_start('gluu-radius')

    def post_install_tasks(self):
        super_gluu_lisence_renewer_fn = os.path.join(self.staticFolder, 'scripts', 'super_gluu_license_renewer.py')
        target_fn = '/etc/cron.daily/super_gluu_lisence_renewer'
        self.run(['cp', '-f', super_gluu_lisence_renewer_fn, target_fn])
        self.run(['chown', 'root:root', target_fn])
        self.run(['chmod', '+x', target_fn])
        cron_service = 'cron'

        if self.os_type in ['centos', 'red', 'fedora']:
            cron_service = 'crond'

        self.run_service_command(cron_service, 'restart')

        print_version_fn = os.path.join(self.install_dir, 'pylib', 'printVersion.py')
        show_version_fn = os.path.join(self.gluuOptBinFolder, 'show_version.py')
        self.run(['cp', '-f', print_version_fn, show_version_fn])
        self.run(['chmod', '+x', show_version_fn])


    def do_installation(self, queue=None):
        try:
            self.thread_queue = queue
            self.pbar = ProgressBar(cols=terminal_size.columns, queue=self.thread_queue)
            self.pbar.progress("gluu", "Configuring system")
            self.configureSystem()
            self.pbar.progress("download", "Downloading War files")
            self.downloadWarFiles()
            self.pbar.progress("gluu", "Calculating application memory")
            self.calculate_selected_aplications_memory()
            self.pbar.progress("java", "Installing JRE")
            self.installJRE()
            self.pbar.progress("jetty", "Installing Jetty")
            self.installJetty()
            self.pbar.progress("jython", "Installing Jython")
            self.installJython()
            self.pbar.progress("node", "Installing Node")
            self.installNode()
            self.pbar.progress("gluu", "Making salt")
            self.make_salt()
            self.pbar.progress("gluu", "Making oxauth salt")
            self.make_oxauth_salt()
            self.pbar.progress("scripts", "Copying scripts")
            self.copy_scripts()
            self.pbar.progress("gluu", "Encoding passwords")
            self.encode_passwords()
            self.pbar.progress("gluu", "Encoding test passwords")
            self.encode_test_passwords()
            
            if self.installPassport:
                self.generate_passport_configuration()
            
            self.pbar.progress("gluu", "Installing Gluu base")
            self.install_gluu_base()
            self.pbar.progress("gluu", "Preparing base64 extention scripts")
            self.prepare_base64_extension_scripts()
            self.pbar.progress("gluu", "Rendering templates")
            self.render_templates()
            self.pbar.progress("gluu", "Generating crypto")
            self.generate_crypto()
            self.pbar.progress("gluu","Generating oxauth openid keys")
            self.generate_oxauth_openid_keys()
            self.pbar.progress("gluu", "Generating base64 configuration")
            self.generate_base64_configuration()
            self.pbar.progress("gluu", "Rendering configuratipn template")
            self.render_configuration_template()
            self.pbar.progress("gluu", "Updating hostname")
            self.update_hostname()
            self.pbar.progress("gluu", "Setting ulimits")
            self.set_ulimits()
            self.pbar.progress("gluu", "Copying output")
            self.copy_output()
            self.pbar.progress("gluu", "Setting up init scripts")
            self.setup_init_scripts()
            self.pbar.progress("node", "Rendering node templates")
            self.render_node_templates()
            self.pbar.progress("gluu", "Installing Gluu components")
            self.install_gluu_components()
            self.pbar.progress("gluu", "Rendering test templates")
            self.render_test_templates()
            self.pbar.progress("gluu", "Copying static")
            self.copy_static()
            self.fix_systemd_script()
            self.pbar.progress("gluu", "Setting ownerships")
            self.set_ownership()
            self.pbar.progress("gluu", "Setting permissions")
            self.set_permissions()
            self.pbar.progress("gluu", "Starting services")
            self.start_services()
            self.pbar.progress("gluu", "Saving properties")
            self.save_properties()

            if setupOptions['loadTestData']:
                self.pbar.progress("gluu", "Loading test data", False)
                self.load_test_data()

            if 'importLDIFDir' in list(setupOptions.keys()):
                self.pbar.progress("gluu", "Importing LDIF files")
                self.render_custom_templates(setupOptions['importLDIFDir'])
                self.import_custom_ldif(setupOptions['importLDIFDir'])

            self.deleteLdapPw()

            self.post_install_tasks()

            self.pbar.progress("gluu", "Completed")
            if not self.thread_queue:
                print()
                self.print_post_messages()

        except:
            if self.thread_queue:
                self.thread_queue.put((ERROR, "", str(traceback.format_exc())))
            else:
                installObject.logIt("***** Error caught in main loop *****", True)
                installObject.logIt(traceback.format_exc(), True)
                print("***** Error caught in main loop *****")
                print(traceback.format_exc())

    def print_post_messages(self):
        print()
        for m in self.post_messages:
            print(m)

############################   Main Loop   #################################################




file_max = int(open("/proc/sys/fs/file-max").read().strip())

current_mem_bytes = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
current_mem_size = round(current_mem_bytes / (1024.**3), 1) #in GB

current_number_of_cpu = multiprocessing.cpu_count()

disk_st = os.statvfs('/')
available_disk_space = round(disk_st.f_bavail * disk_st.f_frsize / (1024 * 1024 *1024), 1)

def resource_checkings():

    if file_max < 64000:
        print(("{0}Maximum number of files that can be opened on this computer is "
                  "less than 64000. Please increase number of file-max on the "
                  "host system and re-run setup.py{1}".format(gluu_utils.colors.DANGER,
                                                                gluu_utils.colors.ENDC)))
        sys.exit(1)

    if current_mem_size < suggested_mem_size:
        print(("{0}Warning: RAM size was determined to be {1:0.1f} GB. This is less "
               "than the suggested RAM size of {2} GB.{3}").format(gluu_utils.colors.WARNING,
                                                        current_mem_size, 
                                                        suggested_mem_size,
                                                        gluu_utils.colors.ENDC))


        result = input("Proceed anyways? [Y|n] ")
        if result and result[0].lower() == 'n':
            sys.exit()

    if current_number_of_cpu < suggested_number_of_cpu:

        print(("{0}Warning: Available CPU Units found was {1}. "
            "This is less than the required amount of {2} CPU Units.{3}".format(
                                                        gluu_utils.colors.WARNING,
                                                        current_number_of_cpu, 
                                                        suggested_number_of_cpu,
                                                        gluu_utils.colors.ENDC)))
                                                        
        result = input("Proceed anyways? [Y|n] ")
        if result and result[0].lower() == 'n':
            sys.exit()



    if available_disk_space < suggested_free_disk_space:
        print(("{0}Warning: Available free disk space was determined to be {1} "
            "GB. This is less than the required disk space of {2} GB.{3}".format(
                                                        gluu_utils.colors.WARNING,
                                                        available_disk_space,
                                                        suggested_free_disk_space,
                                                        gluu_utils.colors.ENDC)))

        result = input("Proceed anyways? [Y|n] ")
        if result and result[0].lower() == 'n':
            sys.exit()


if __name__ == '__main__':

    cur_dir = os.path.dirname(os.path.realpath(__file__))

    thread_queue = None

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

    argsp = parser.parse_args()

    if (not argsp.c) and sys.stdout.isatty() and (int(terminal_size.lines) > 24) and (int(terminal_size.columns) > 79):
        try:
            import npyscreen
        except:
            print("Can't start TUI, continuing command line")
        else:
            from pylib import tui
            thread_queue = tui.queue
            from pylib.tui import *

    if not argsp.n and not thread_queue:
        resource_checkings()
    
    #key_shortcuter_rules = gluu_utils.get_key_shortcuter_rules()

    setupOptions = {
        'install_dir': cur_dir,
        'setup_properties': None,
        'noPrompt': False,
        'downloadWars': False,
        'installOxAuth': True,
        'installOxTrust': True,
        'wrends_install': LOCAL,
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
        'cb_install': NONE,
        'loadTestDataExit': False,
        'loadData': True,
    }


    if argsp.install_local_wrends:
        setupOptions['wrends_install'] = LOCAL
    
    if argsp.no_oxauth:
        setupOptions['installOxAuth'] = False
    
    if argsp.no_oxtrust:
        setupOptions['installOxTrust'] = False

    setupOptions['installGluuRadius'] = argsp.install_gluu_radius

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

    if argsp.d:
        if os.path.exists(argsp.d):
            setupOptions['install_dir'] = argsp.d
        else:
            print('System folder %s does not exist. Installing in %s' % (argsp.d, os.getcwd()))

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

    setupOptions['installSaml'] = argsp.install_shib
    setupOptions['downloadWars'] = argsp.w
    setupOptions['installOxAuthRP'] = argsp.install_oxauth_rp
    setupOptions['installPassport'] = argsp.install_passport
    setupOptions['loadTestData']  = argsp.t
    setupOptions['loadTestDataExit'] = argsp.x
    setupOptions['allowPreReleasedFeatures'] = argsp.allow_pre_released_features
    setupOptions['listenAllInterfaces'] = argsp.listen_all_interfaces
    setupOptions['installCasa'] = argsp.install_casa
    setupOptions['installOxd'] = argsp.install_oxd
    setupOptions['installScimServer'] = argsp.install_scim
    setupOptions['installFido2'] = argsp.install_fido2
    setupOptions['couchbase_bucket_prefix'] = argsp.couchbase_bucket_prefix

    if argsp.remote_ldap:
        setupOptions['wrends_install'] = REMOTE
    
    if argsp.remote_couchbase:
        setupOptions['cb_install'] = REMOTE

    if argsp.no_data:
        setupOptions['loadData'] = False
    
    if argsp.remote_ldap:
        setupOptions['listenAllInterfaces'] = True

    if argsp.oxd_use_gluu_storage:
        setupOptions['oxd_use_gluu_storage'] = True

    if argsp.import_ldif:
        if os.path.isdir(argsp.import_ldif):
            setupOptions['importLDIFDir'] = argsp.import_ldif
            print("Found setup LDIF import directory %s\n" % (argsp.import_ldif))
        else:
            print('The custom LDIF import directory %s does not exist. Exiting...' % (argsp.import_ldif))
            sys.exit(2)

    installObject = Setup(setupOptions['install_dir'])

    installObject.properties_password = argsp.properties_password

    installObject.downloadWars = setupOptions['downloadWars']

    for option in setupOptions:
        setattr(installObject, option, setupOptions[option])

    # Get the OS type
    installObject.os_type, installObject.os_version = installObject.detect_os_type()
    # Get the init type
    installObject.os_initdaemon = installObject.detect_initd()
    
    installObject.check_and_install_packages()
    #it is time to import pyDes library
    from pyDes import *
    from pylib.cbm import CBM
    import ruamel.yaml
    from ldap3 import Server, Connection, BASE, MODIFY_REPLACE
    from ldap3.utils import dn as dnutils
    gluu_utils.dnutils = dnutils

    if setupOptions['loadTestDataExit']:
        installObject.initialize()
        installObject.load_test_data_exit()

    if installObject.check_installed():
        print("\nThis instance already configured. If you need to install new one you should reinstall package first.")
        sys.exit(2)


    # Get apache version
    installObject.apache_version = installObject.determineApacheVersionForOS()

    print("\nInstalling Gluu Server...")
    print("Detected OS  :  %s" % installObject.os_type)
    print("Detected init:  %s" % installObject.os_initdaemon)
    print("Detected Apache:  %s" % installObject.apache_version)

    if installObject.os_type == 'debian':
        os.environ['LC_ALL'] = 'C'

    print("\nInstalling Gluu Server...\n\nFor more info see:\n  %s  \n  %s\n" % (installObject.log, installObject.logError))

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
    installObject.initialize()

    setup_loaded = None

    if setupOptions['setup_properties']:
        installObject.logIt('%s Properties found!\n' % setupOptions['setup_properties'])
        setup_loaded = installObject.load_properties(setupOptions['setup_properties'])
    elif os.path.isfile(installObject.setup_properties_fn):
        installObject.logIt('%s Properties found!\n' % installObject.setup_properties_fn)
        setup_loaded = installObject.load_properties(installObject.setup_properties_fn)
    elif os.path.isfile(installObject.setup_properties_fn+'.enc'):
        installObject.logIt('%s Properties found!\n' % installObject.setup_properties_fn+'.enc')
        setup_loaded = installObject.load_properties(installObject.setup_properties_fn+'.enc')

    if thread_queue:

        msg = tui.msg
        msg.storages = list(installObject.couchbaseBucketDict.keys())
        msg.installation_step_number = 33
        
        msg.os_type = installObject.os_type
        msg.os_version = installObject.os_version
        msg.os_initdaemon = installObject.os_initdaemon
        msg.apache_version = installObject.apache_version
        msg.current_mem_size = current_mem_size
        msg.current_number_of_cpu = current_number_of_cpu
        msg.current_free_disk_space = available_disk_space
        msg.current_file_max = file_max

        GSA = tui.GluuSetupApp()
        GSA.installObject = installObject

        GSA.run()
    else:

        if not setup_loaded:
            installObject.logIt("{0} or {0}.enc Properties not found. Interactive setup commencing...".format(installObject.setup_properties_fn))
            installObject.promptForProperties()

        # Validate Properties
        installObject.check_properties()

        proceed = True

        # Show to properties for approval
        print('\n%s\n' % repr(installObject))

        # check if we have enough memory
        if not installObject.calculate_selected_aplications_memory():
            print("{}WARINIG: You don't have enough memory to run Gluu CE properly{}\n".format(gluu_utils.colors.WARNING, gluu_utils.colors.ENDC))

        if not setupOptions['noPrompt']:
            proceed_prompt = input('Proceed with these values [Y|n] ').lower().strip()
            if proceed_prompt and proceed_prompt[0] !='y':
                proceed = False


        if setupOptions['noPrompt'] or proceed:
            installObject.do_installation()
            print("\n\n Gluu Server installation successful! Point your browser to https://%s\n\n" % installObject.hostname)
        else:
            installObject.save_properties()
    

# END
