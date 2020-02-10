#!/usr/bin/python
import os
import argparse
import sys
import subprocess
import json
import zipfile

cur_dir = os.path.dirname(os.path.realpath(__file__))

if not os.path.exists('setup.py'):
    print "This script should be run from /install/community-edition-setup/"
    sys.exit()
    
if not os.path.exists('/install/community-edition-setup/setup.properties.last'):
    print "setup.properties.last is missing can't continue"
    sys.exit()

parser = argparse.ArgumentParser()
parser.add_argument("-addshib", help="Install Shibboleth SAML IDP", action="store_true")
parser.add_argument("-addpassport", help="Install Passport", action="store_true")
parser.add_argument("-addoxd", help="Install Oxd Server", action="store_true")
parser.add_argument("-addcasa", help="Install Gluu Casa", action="store_true")

args = parser.parse_args()

if  len(sys.argv)<2:
    parser.print_help()
    parser.exit(1)

def get_properties(prop_fn):
    p = Properties.Properties()
    with open(prop_fn) as file_object:
        p.load(file_object)
    return p

oxVersion = 0
setup_properties_fn = '/install/community-edition-setup/setup.properties.last'
install_dir = '.'

#Determine setup version
with open(setup_properties_fn) as f:
    for l in f:
        ls = l.strip()
        if ls.startswith('oxVersion'):
            n = ls.find('=')
            oxVersion_setup = ls[n+1:].strip()

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

if oxVersion == gluu_version:
    setupObj.cbm = CBM(setupObj.couchbase_hostname, setupObj.couchebaseClusterAdmin, setupObj.ldapPass)


if not hasattr(setupObj, 'ldap_type'):
    setupObj.ldap_type = 'open_ldap'

if setupObj.ldap_type == 'opendj':
    setupObj.ldapCertFn = setupObj.opendj_cert_fn
else:
    setupObj.ldapCertFn = setupObj.openldapTLSCert

setupObj.ldapCertFn = setupObj.opendj_cert_fn


# Determine persistence type
gluu_prop = get_properties(setupObj.gluu_properties_fn)
persistence_type = gluu_prop['persistence.type']

if persistence_type == 'hybrid':
    hybrid_prop = get_properties(setupObj.gluu_hybrid_roperties)    
    persistence_type = hybrid_prop['storage.default']

if persistence_type == 'couchbase':
    gluu_cb_prop = get_properties(setupObj.gluuCouchebaseProperties)
    cb_serevr = gluu_cb_prop['servers'].split(',')[0].strip()
    cb_admin = gluu_cb_prop['auth.userName']
    encoded_cb_password = gluu_cb_prop['auth.userPassword']
    cb_passwd = os.popen('/opt/gluu/bin/encode.py -D ' + encoded_cb_password).read().strip()

    from ces_current.pylib.cbm import CBM
    setupObj.cbm = CBM(cb_serevr, cb_admin, cb_passwd)


def installSaml():

    if os.path.exists('/opt//shibboleth-idp'):
        print "SAML is already installed on this system"
        return

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

    print "Shibboleth installation done"


    
def installPassport():
    
    if os.path.exists('/opt/gluu/node/passport'):
        print "Passport is already installed on this system"
        return

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
    
    setupObj.generate_passport_configuration()
    setupObj.install_passport()
    
    
    print "Passport installation done"

def installOxd():
    
    if os.path.exists('/opt/oxd-server'):
        print "Oxd server was already installed"
        return
    
    print "Installing Oxd Server"
    
    if oxVersion != gluu_version:

        oxd_url = 'https://ox.gluu.org/maven/org/gluu/oxd-server/{0}/oxd-server-{0}-distribution.zip'.format(oxVersion_current)

        print "Downloading {} and preparing package".format(os.path.basename(oxd_url))
        oxd_zip_fn = '/tmp/oxd-server.zip'
        oxd_tmp_dir = '/tmp/oxd-server'

        setupObj.run(['wget', '-nv', oxd_url, '-O', oxd_zip_fn])
        setupObj.run(['unzip', '-qqo', '/tmp/oxd-server.zip', '-d', oxd_tmp_dir])
        setupObj.run(['mkdir', os.path.join(oxd_tmp_dir,'data')])

        if setupObj.os_type + setupObj.os_version in ('ubuntu18','debian9'):
            default_url = 'https://raw.githubusercontent.com/GluuFederation/oxd/version_{}/debian/oxd-server-default'.format(ces_version)
            setupObj.run(['wget', '-nv', default_url, '-O', os.path.join(oxd_tmp_dir, 'oxd-server-default')])

        service_file = 'oxd-server.init.d' if setupObj.os_type + setupObj.os_version in ('ubuntu18','debian9') else 'oxd-server.service'
        service_url = 'https://raw.githubusercontent.com/GluuFederation/oxd/version_{}/debian/{}.file'.format(ces_version, service_file)
        setupObj.run(['wget', '-nv', service_url, '-O', os.path.join(oxd_tmp_dir, service_file)])

        oxd_server_sh_url = 'https://raw.githubusercontent.com/GluuFederation/oxd/version_{}/debian/oxd-server.sh'.format(ces_version)
        setupObj.run(['wget', '-nv', oxd_server_sh_url, '-O', os.path.join(oxd_tmp_dir, 'bin/oxd-server.sh')])

        setupObj.run(['tar', '-zcf', os.path.join(setupObj.distGluuFolder, 'oxd-server.tgz'), 'oxd-server'], cwd='/tmp')
    

    setupObj.oxd_package = os.path.join(setupObj.distGluuFolder, 'oxd-server.tgz')
    setupObj.install_oxd()

def installCasa():

    if os.path.exists('/opt/gluu/jetty/casa'):
        print "Casa is already installed on this system"
        return

    print "Installing Gluu Casa"


    setupObj.promptForCasaInstallation(promptForCasa='y')
    if not setupObj.installCasa:
        print "Casa installation cancelled"

    setupObj.prepare_base64_extension_scripts()

    casa_script_fn = os.path.basename(setupObj.ldif_scripts_casa)
    casa_script_fp = os.path.join(cur_dir, 'ces_current/output', casa_script_fn)
    
    setupObj.renderTemplateInOut(
                    os.path.join(cur_dir, 'ces_current/templates/', casa_script_fn),
                    os.path.join(cur_dir, 'ces_current/templates'),
                    os.path.join(cur_dir, 'ces_current/output'),
                    )

    if persistence_type == 'ldap':
        setupObj.createLdapPw()
        setupObj.import_ldif_template_opendj(casa_script_fp)
        setupObj.deleteLdapPw()
    else:
        setupObj.import_ldif_couchebase(ldif_file_list=[casa_script_fp], bucket='gluu')

    if setupObj.installOxd:
        installOxd()
        setupObj.run_service_command('oxd-server', 'restart')

    setupObj.import_oxd_certificate()

    setupObj.renderTemplateInOut(
                    os.path.join(cur_dir, 'ces_current/templates/casa.json'),
                    os.path.join(cur_dir, 'ces_current/templates'),
                    os.path.join(cur_dir, 'ces_current/output'),
                    )
    setupObj.calculate_selected_aplications_memory()
    setupObj.install_casa()

if args.addshib:
    installSaml()

if args.addpassport:
    installPassport()

if args.addoxd:
    installOxd()

if args.addcasa:
    installCasa()

print "Please exit container and restart Gluu Server"
