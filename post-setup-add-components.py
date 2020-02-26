#!/usr/bin/python
import os
import argparse
import sys
import subprocess
import json
import zipfile
from pylib.Properties import Properties as JProperties

cur_dir = os.path.dirname(os.path.realpath(__file__))

if not os.path.exists('setup.py'):
    print "This script should be run from /install/community-edition-setup/"
    sys.exit()
    
if not os.path.exists('/install/community-edition-setup/setup.properties.last'):
    print "setup.properties.last is missing can't continue"
    sys.exit()

f=open('setup.py').readlines()

for l in f:
    if l.startswith('from pyDes import *'):
        break
else:
    f.insert(1, 'from pyDes import *\n')
    with open('setup.py','w') as w:
        w.write(''.join(f))

parser = argparse.ArgumentParser()
parser.add_argument("-addshib", help="Install Shibboleth SAML IDP", action="store_true")
parser.add_argument("-addpassport", help="Install Passport", action="store_true")
args = parser.parse_args()

if  len(sys.argv)<2:
    parser.print_help()
    parser.exit(1)


def get_properties(prop_fn):
    jprop = JProperties()
    with open(prop_fn) as f:
        jprop.load(f)

    return jprop

oxVersion = 0
setup_properties_fn = '/install/community-edition-setup/setup.properties.last'
install_dir = '.'

#Determine setup version
setup_prop = get_properties(setup_properties_fn)
oxVersion_setup = setup_prop['oxVersion']

run_oxauth_war_fn = '/opt/gluu/jetty/oxauth/webapps/oxauth.war'

os.system('cp -f {} /opt/dist/gluu'.format(run_oxauth_war_fn))

#Determine gluu version
war_zip = zipfile.ZipFile(run_oxauth_war_fn, 'r')
menifest = war_zip.read('META-INF/MANIFEST.MF')

for l in menifest.splitlines():
    ls = l.strip()
    n = ls.find(':')

    if ls[:n].strip() == 'Implementation-Version':
        oxVersion_current = ls[n+1:].strip()
        gluu_version_list = oxVersion_current.split('.')
        if not gluu_version_list[-1].isdigit():
            gluu_version_list.pop(-1)

        gluu_version = '.'.join(gluu_version_list)

print "Current Gluu Version", gluu_version

ces_version_l = []
for ci in oxVersion_current.split('.'):
    if ci.lower() == 'final' or ci.lower().startswith('sp') or ci.lower().startswith('patch'):
        continue
    ces_version_l.append(ci)
    
ces_version = '.'.join(ces_version_l)

if os.path.exists('ces_current.back'):
    os.system('rm -r -f ces_current.back')

if os.path.exists('ces_current'):
    os.system('mv ces_current ces_current.back')

ces_url = 'https://github.com/GluuFederation/community-edition-setup/archive/version_{}.zip'.format(ces_version)

print "Downloading Community Edition Setup {}".format(ces_version)

os.system('wget -nv {} -O version_{}.zip'.format(ces_url, ces_version))
print "Extracting package"
os.system('unzip -o -qq version_{}.zip'.format(ces_version))
os.system('mv community-edition-setup-version_{} ces_current'.format(ces_version))

open('ces_current/__init__.py','w').close()

sys.path.append('ces_current')

from ces_current.setup import *
install_dir = 'ces_current'

setupObj = Setup(install_dir)

setupObj.setup = setupObj

setupObj.os_type, setupObj.os_version = setupObj.detect_os_type()
setupObj.os_initdaemon = setupObj.detect_initd()


if oxVersion != gluu_version:

    keep_keys = ['idp3_war', 'idp3_cml_keygenerator', 'idp3_dist_jar', 'idp3Folder',
                'idp3MetadataFolder', 'idp3MetadataCredentialsFolder', 'idp3LogsFolder',
                'idp3LibFolder', 'idp3ConfFolder', 'idp3ConfAuthnFolder', 
                'idp3CredentialsFolder', 'idp3WebappFolder', 'oxVersion',
                'templateFolder', 'outputFolder',
                'ldif_passport_config', 'ldif_passport', 'ldif_passport_clients',
                ]
    keep_dict = {}

    for k in keep_keys:
        v = getattr(setupObj, k)
        if v:
            keep_dict[k] = v

setupObj.load_properties('/install/community-edition-setup/setup.properties.last')

if oxVersion != gluu_version:
    for k in keep_dict:
        setattr(setupObj, k, keep_dict[k])


setupObj.githubBranchName = oxVersion

setupObj.log = os.path.join(setupObj.install_dir, 'post_setup.log')
setupObj.logError = os.path.join(setupObj.install_dir, 'post_setup_error.log')

print "Log Files:", setupObj.log, setupObj.logError

attribDataTypes.startup(install_dir)


gluu_cb_prop_fn = '/etc/gluu/conf/gluu-couchbase.properties'

if os.path.exists(gluu_cb_prop_fn):
    gluu_cb_prop = get_properties(gluu_cb_prop_fn)

    cb_hostname = gluu_cb_prop['servers'].split(',')[0].strip()
    cb_userName = gluu_cb_prop['auth.userName']
    cb_userPassword_e = gluu_cb_prop['auth.userPassword']
    cb_bindPassword = os.popen('/opt/gluu/bin/encode.py -D ' + cb_userPassword_e).read().strip()

    setupObj.cbm = CBM(cb_hostname, cb_userName, cb_bindPassword)
else:
    setupObj.cbm = None

if not hasattr(setupObj, 'ldap_type'):
    setupObj.ldap_type = 'open_ldap'

if setupObj.ldap_type == 'opendj':
    setupObj.ldapCertFn = setupObj.opendj_cert_fn
else:
    setupObj.ldapCertFn = setupObj.openldapTLSCert

setupObj.ldapCertFn = setupObj.opendj_cert_fn

def installSaml():

    setupObj.run(['cp', '-f', os.path.join(setupObj.gluuOptFolder, 'jetty/identity/webapps/identity.war'), 
                setupObj.distGluuFolder])

    if not os.path.exists(setupObj.idp3Folder):
        os.mkdir(setupObj.idp3Folder)

    if setupObj.idp3_metadata[0] == '/':
        setupObj.idp3_metadata = setupObj.idp3_metadata[1:]

    metadata_file = os.path.join(setupObj.idp3MetadataFolder, setupObj.idp3_metadata)

    setupObj.run(['cp', '-f', './ces_current/templates/jetty.conf.tmpfiles.d',
                            setupObj.templateFolder])

    if os.path.exists(metadata_file):
        print "Shibboleth is already installed on this system"
        sys.exit()

    print "Installing Shibboleth ..."
    setupObj.oxTrustConfigGeneration = "true"

    if not setupObj.application_max_ram:
        setupObj.application_max_ram = setupObj.getPrompt("Enter maximum RAM for applications in MB", '3072')

    if not setupObj.hostname:
        setupObj.hostname = setupObj.getPrompt("Hostname", '')

    if not setupObj.orgName:
        setupObj.orgName = setupObj.getPrompt("Organization Name", '')

    if not setupObj.shibJksPass:
        setupObj.shibJksPass = setupObj.getPW()
        setupObj.gen_cert('shibIDP', setupObj.shibJksPass, 'jetty')


    setupObj.calculate_selected_aplications_memory()
    realIdp3Folder = os.path.realpath(setupObj.idp3Folder)
    setupObj.run([setupObj.cmd_chown, '-R', 'jetty:jetty', realIdp3Folder])
    realIdp3BinFolder = "%s/bin" % realIdp3Folder

    if os.path.exists(realIdp3BinFolder):
        setupObj.run(['find', realIdp3BinFolder, '-name', '*.sh', '-exec', 'chmod', "755", '{}',  ';'])
    
    setupObj.run([setupObj.cmd_mkdir, '-p', setupObj.idp3Folder])
    setupObj.run([setupObj.cmd_mkdir, '-p', setupObj.idp3MetadataFolder])
    setupObj.run([setupObj.cmd_mkdir, '-p', setupObj.idp3MetadataCredentialsFolder])
    setupObj.run([setupObj.cmd_mkdir, '-p', setupObj.idp3LogsFolder])
    setupObj.run([setupObj.cmd_mkdir, '-p', setupObj.idp3LibFolder])
    setupObj.run([setupObj.cmd_mkdir, '-p', setupObj.idp3ConfFolder])
    setupObj.run([setupObj.cmd_mkdir, '-p', setupObj.idp3ConfAuthnFolder])
    setupObj.run([setupObj.cmd_mkdir, '-p', setupObj.idp3CredentialsFolder])
    setupObj.run([setupObj.cmd_mkdir, '-p', setupObj.idp3WebappFolder])
    

    setupObj.run(['/usr/bin/wget', setupObj.idp3_war, '--no-verbose', '-c', '--retry-connrefused', '--tries=10', '-O', '%s/idp.war' % setupObj.distGluuFolder])
    setupObj.run(['/usr/bin/wget', setupObj.idp3_cml_keygenerator, '--no-verbose', '-c', '--retry-connrefused', '--tries=10', '-O', setupObj.distGluuFolder + '/idp3_cml_keygenerator.jar'])
    setupObj.run(['/usr/bin/wget', setupObj.idp3_dist_jar, '--no-verbose', '-c', '--retry-connrefused', '--tries=10', '-O', setupObj.distGluuFolder + '/shibboleth-idp.jar'])
    setupObj.installSaml = True
    setupObj.install_saml()
    
    setupObj.run([setupObj.cmd_chown, '-h', 'root:gluu', '/etc/certs/idp-signing.crt'])
    setupObj.run([setupObj.cmd_chown, '-h', 'root:gluu', '/etc/certs/idp-signing.key'])

    metadata = open(metadata_file).read()
    metadata = metadata.replace('md:ArtifactResolutionService', 'ArtifactResolutionService')
    with open(metadata_file,'w') as F:
        F.write(metadata)
    
    setupObj.run([setupObj.cmd_chown, '-R', 'jetty:jetty', setupObj.idp3Folder])
    if not os.path.exists('/var/run/jetty'):
        os.mkdir('/var/run/jetty')
    setupObj.run([setupObj.cmd_chown, '-R', 'jetty:jetty', '/var/run/jetty'])
    setupObj.enable_service_at_start('idp')


    default_storage = 'ldap'

    gluu_hybrid_prop_fn = '/etc/gluu/conf/gluu-hybrid.properties'

    if os.path.exists(gluu_hybrid_prop_fn):
        gluu_hybrid_prop = get_properties(gluu_hybrid_prop_fn)
        default_storage = gluu_hybrid_prop['storage.default']
    elif setupObj.cbm:
        default_storage = 'couchbase'

    gluu_prop = get_properties('/etc/gluu/conf/gluu.properties')

    if default_storage == 'ldap':
        ox_ldap_prop = get_properties('/etc/gluu/conf/gluu-ldap.properties')

        bindDN = ox_ldap_prop['bindDN']
        bindPassword_e = ox_ldap_prop['bindPassword']
        cmd = '/opt/gluu/bin/encode.py -D ' + bindPassword_e    
        bindPassword = os.popen(cmd).read().strip()
        ldap_host_port = ox_ldap_prop['servers'].split(',')[0].strip()

        ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_ALLOW)
        ldap_conn = ldap.initialize('ldaps://'+ldap_host_port)
        ldap_conn.simple_bind_s(bindDN, bindPassword)

        result = ldap_conn.search_s(
                        'o=gluu',
                        ldap.SCOPE_SUBTREE,
                        '(objectClass=oxTrustConfiguration)',
                        ['oxTrustConfApplication']
                        )

        dn = result[0][0]
        oxTrustConfApplication = json.loads(result[0][1]['oxTrustConfApplication'][0])
        
        oxTrustConfApplication['configGeneration'] = True
        oxTrustConfApplication_js = json.dumps(oxTrustConfApplication, indent=2)

        ldap_conn.modify_s(
                        dn,
                        [( ldap.MOD_REPLACE, 'oxTrustConfApplication',  oxTrustConfApplication_js)]
                    )

    else:
        bucket = gluu_cb_prop['bucket.default']
        setupObj.cbm.exec_query('UPDATE `{}` USE KEYS "configuration_oxtrust" SET configGeneration=true'.format(bucket))

    print "Shibboleth installation done"


    
def installPassport():
    
    if os.path.exists('/opt/gluu/node/passport'):
        print "Passport is already installed on this system"
        sys.exit()

    if oxVersion != gluu_version:

        node_url = 'https://nodejs.org/dist/v{0}/node-v{0}-linux-x64.tar.xz'.format(setupObj.node_version)
        nod_archive_fn = os.path.basename(node_url)

        print "Downloading {}".format(nod_archive_fn)
        setupObj.run(['wget', '-nv', node_url, '-O', os.path.join(setupObj.distAppFolder, nod_archive_fn)])
        cur_node_dir = os.readlink('/opt/node')
        setupObj.run(['unlink', '/opt/node'])
        setupObj.run(['mv', cur_node_dir, cur_node_dir+'.back'])

        print "Installing", nod_archive_fn
        setupObj.installNode()

        passport_url = 'https://ox.gluu.org/npm/passport/passport-{}.tgz'.format(gluu_version)
        passport_modules_url = 'https://ox.gluu.org/npm/passport/passport-version_{}-node_modules.tar.gz'.format(gluu_version)
        passport_fn = os.path.basename(passport_url)
        passport_modules_fn = os.path.basename(passport_modules_url)

        print "Downloading {}".format(passport_fn)
        setupObj.run(['wget', '-nv', passport_url, '-O', os.path.join(setupObj.distGluuFolder, 'passport.tgz')])

        print "Downloading {}".format(passport_modules_fn)
        setupObj.run(['wget', '-nv', passport_modules_url, '-O', os.path.join(setupObj.distGluuFolder, 'passport-node_modules.tar.gz')])

        if setupObj.os_initdaemon == 'systemd':
            passport_syatemd_url = 'https://raw.githubusercontent.com/GluuFederation/community-edition-package/master/package/systemd/passport.service'
            passport_syatemd_fn = os.path.basename(passport_syatemd_url)
            
            print "Downloading {}".format(passport_syatemd_fn)
            setupObj.run(['wget', '-nv', passport_syatemd_url, '-O', '/usr/lib/systemd/system/passport.service'])



    setupObj.installPassport = True
    setupObj.calculate_selected_aplications_memory()
    
    setupObj.renderTemplateInOut(
                    os.path.join(cur_dir, 'ces_current/templates/node/passport'),
                    os.path.join(cur_dir, 'ces_current/templates/node'),
                    os.path.join(cur_dir, 'ces_current/output/node')
                    )


    print "Installing Passport ..."

    if not os.path.exists(os.path.join(setupObj.configFolder, 'passport-inbound-idp-initiated.json')) and os.path.exists('ces_current/templates/passport-inbound-idp-initiated.json'):
        setupObj.run(['cp', 'ces_current/templates/passport-inbound-idp-initiated.json', setupObj.configFolder])

    proc = subprocess.Popen('echo "" | /opt/jre/bin/keytool -list -v -keystore /etc/certs/passport-rp.jks', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    alias_l=''
    
    setupObj.generate_passport_configuration()
    setupObj.install_passport()
    
    
    print "Passport installation done"


if args.addshib:
    installSaml()

if args.addpassport:
    installPassport()

print "Please exit container and restart Gluu Server"
