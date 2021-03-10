#!/usr/bin/python3

import os
import sys
import json
import zipfile
import shutil
import site
import argparse



from urllib.request import urlretrieve

cur_dir = os.path.dirname(os.path.realpath(__file__))
gluu_app_dir = '/opt/dist/gluu'
app_dir = '/opt/dist/app'
ces_dir = '/install/community-edition-setup'
scripts_dir = '/opt/dist/scripts'
certs_dir = '/etc/crts'

if not os.path.exists(scripts_dir):
    os.makedirs(scripts_dir)

parser = argparse.ArgumentParser(description="This script downloads Gluu Server components and fires setup")
parser.add_argument('-u', help="Use downloaded components", action='store_true')
#parser.add_argument('-upgrade', help="Upgrade Gluu war and jar files", action='store_true')
parser.add_argument('-uninstall', help="Uninstall Jans server and removes all files", action='store_true')
parser.add_argument('--args', help="Arguments to be passed to setup.py")
parser.add_argument('--keep-downloads', help="Keep downloaded files", action='store_true')

argsp = parser.parse_args()

jetty_home = '/opt/gluu/jetty'
services = ['casa.service', 'identity.service', 'opendj.service', 'oxauth.service', 'passport.service', 'fido2.service', 'idp.service', 'oxauth-rp.service', 'oxd-server.service', 'scim.service']
app_versions = {
    "JETTY_VERSION": "9.4.31.v20200723", 
    "AMAZON_CORRETTO_VERSION": "11.0.8.10.1", 
    "OX_GITVERISON": "-SNAPSHOT", 
    "NODE_VERSION": "v12.19.0",
    "OX_VERSION": "4.3.0", 
    "JYTHON_VERSION": "2.7.2",
    "OPENDJ_VERSION": "4.0.0.gluu",
    "SETUP_BRANCH": "",
    "TWILIO_VERSION": "7.17.0",
    "JSMPP_VERSION": "2.3.7"
    }

def check_installation():
    if not (os.path.exists(jetty_home) and os.path.exists('/etc/gluu')):
        print("Gluu server seems not installed")
        sys.exit()

if argsp.uninstall:
    check_installation()
    print('\033[31m')
    print("This process is irreversible.")
    print("You will lose all data related to Janssen Server.")
    print('\033[0m')
    print()
    while True:
        print('\033[31m \033[1m')
        response = input("Are you sure to uninstall Gluu Server? [yes/N] ")
        print('\033[0m')
        if response.lower() in ('yes', 'n', 'no'):
            if not response.lower() == 'yes':
                sys.exit()
            else:
                break
        else:
            print("Please type \033[1m yes \033[0m to uninstall")

    print("Uninstalling Gluu Server...")

    print("Stopping OpenDj Server")
    os.system('/opt/opendj/bin/stop-ds')
    for uf in services:
        service,ext = os.path.splitext(uf)
        if os.path.exists(os.path.join(jetty_home, service)):
            default_fn = os.path.join('/etc/default/', service)
            if os.path.exists(default_fn):
                print("Removing", default_fn)
                os.remove(default_fn)
            print("Stopping", service)
            os.system('systemctl stop ' + service)
    os.system('systemctl stop oxd-server')
    remove_list = ['/etc/certs', '/etc/gluu', '/opt/gluu', '/opt/amazon-corretto*', '/opt/jre', '/opt/jetty*', '/opt/jython*', '/opt/opendj', '/opt/node*',  '/opt/oxd-server',  '/opt/shibboleth-idp']
    if not argsp.keep_downloads:
        remove_list.append('/opt/dist')

    for p in remove_list:
        cmd = 'rm -r -f ' + p
        print("Executing", cmd)
        os.system('rm -r -f ' + p)

    sys.exit()

def download(url, target_fn):
    dst = os.path.join(app_dir, target_fn)
    pardir, fn = os.path.split(dst)
    if not os.path.exists(pardir):
        os.makedirs(pardir)
    print("Downloading", url, "to", dst)
    urlretrieve(url, dst)

def package_oxd():
    oxd_tgz_fn = os.path.join(gluu_app_dir, 'oxd-server.tgz')
    oxd_zip_fn = os.path.join(gluu_app_dir, 'oxd-server.zip')
    oxd_tmp_root = '/tmp/{}'.format(os.urandom(5).hex())
    oxd_tmp_dir = os.path.join(oxd_tmp_root, 'oxd-server')
    download('https://ox.gluu.org/maven/org/gluu/oxd-server/{0}{1}/oxd-server-{0}{1}-distribution.zip'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), oxd_zip_fn)
    os.makedirs(oxd_tmp_dir)
    cmd = 'unzip -qqo {} -d {}'.format(oxd_zip_fn, oxd_tmp_dir)
    print("Excuting", cmd)
    os.system(cmd)
    cmd = 'mkdir ' + os.path.join(oxd_tmp_dir, 'data')
    shutil.copy(os.path.join(gluu_app_dir, 'oxd-server-start.sh'), os.path.join(oxd_tmp_dir, 'bin/oxd-server'))
    os.chmod(os.path.join(oxd_tmp_dir, 'bin/oxd-server'), 33261)
    print("Excuting", cmd)
    os.system(cmd)
    cmd = 'cd {}; tar -zcf {} oxd-server'.format(oxd_tmp_root, oxd_tgz_fn)
    print("Excuting", cmd)
    os.system(cmd)
    os.remove(oxd_zip_fn)
    shutil.rmtree(oxd_tmp_root)

if not argsp.u:
    download('https://corretto.aws/downloads/resources/{0}/amazon-corretto-{0}-linux-x64.tar.gz'.format(app_versions['AMAZON_CORRETTO_VERSION']), os.path.join(app_dir, 'amazon-corretto-{0}-linux-x64.tar.gz'.format(app_versions['AMAZON_CORRETTO_VERSION'])))
    download('https://repo1.maven.org/maven2/org/eclipse/jetty/jetty-distribution/{0}/jetty-distribution-{0}.tar.gz'.format(app_versions['JETTY_VERSION']), os.path.join(app_dir,'jetty-distribution-{0}.tar.gz'.format(app_versions['JETTY_VERSION'])))
    download('https://repo1.maven.org/maven2/org/python/jython-installer/{0}/jython-installer-{0}.jar'.format(app_versions['JYTHON_VERSION']), os.path.join(app_dir, 'jython-installer-{0}.jar'.format(app_versions['JYTHON_VERSION'])))
    download('https://nodejs.org/dist/{0}/node-{0}-linux-x64.tar.xz'.format(app_versions['NODE_VERSION']), os.path.join(app_dir, 'node-{0}-linux-x64.tar.xz'.format(app_versions['NODE_VERSION'])))
    download('https://github.com/npcole/npyscreen/archive/master.zip', os.path.join(app_dir, 'npyscreen-master.zip'))
    download('https://ox.gluu.org/maven/org/gluufederation/opendj/opendj-server-legacy/{0}/opendj-server-legacy-{0}.zip'.format(app_versions['OPENDJ_VERSION']), os.path.join(app_dir,'opendj-server-{0}.zip'.format(app_versions['OPENDJ_VERSION'])))
    download('https://ox.gluu.org/maven/org/gluu/oxauth-server/{0}{1}/oxauth-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'oxauth.war'))
    download('https://ox.gluu.org/maven/org/gluu/oxtrust-server/{0}{1}/oxtrust-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'identity.war'))
    download('https://ox.gluu.org/maven/org/gluu/oxauth-client/{0}{1}/oxauth-client-{0}{1}-jar-with-dependencies.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'oxauth-client-jar-with-dependencies.jar'))
    download('https://ox.gluu.org/maven/org/gluu/casa/{0}{1}/casa-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'casa.war'))
    download('https://repo1.maven.org/maven2/com/twilio/sdk/twilio/{0}/twilio-{0}.jar'.format(app_versions['TWILIO_VERSION']), os.path.join(gluu_app_dir,'twilio-{0}.jar'.format(app_versions['TWILIO_VERSION'])))
    download('https://repo1.maven.org/maven2/org/jsmpp/jsmpp/{0}/jsmpp-{0}.jar'.format(app_versions['JSMPP_VERSION']), os.path.join(gluu_app_dir,'jsmpp-{0}.jar'.format(app_versions['JSMPP_VERSION'])))
    download('https://github.com/GluuFederation/casa/raw/version_{}/extras/casa.pub'.format(app_versions['OX_VERSION']), os.path.join(gluu_app_dir,'casa.pub'))
    download('https://raw.githubusercontent.com/GluuFederation/casa/master/plugins/account-linking/extras/login.xhtml', os.path.join(gluu_app_dir,'login.xhtml'))
    download('https://raw.githubusercontent.com/GluuFederation/casa/master/plugins/account-linking/extras/casa.py', os.path.join(gluu_app_dir,'casa.py'))
    download('https://raw.githubusercontent.com/GluuFederation/gluu-snap/master/facter/facter', os.path.join(gluu_app_dir,'facter'))
    download('https://ox.gluu.org/maven/org/gluu/scim-server/{0}{1}/scim-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'scim.war'))
    download('https://ox.gluu.org/maven/org/gluu/fido2-server/{0}{1}/fido2-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'fido2.war'))
    download('https://raw.githubusercontent.com/GluuFederation/oxd/master/debian/oxd-server', os.path.join(gluu_app_dir,'oxd-server-start.sh'))
    download('https://github.com/GluuFederation/community-edition-setup/archive/version_{}.zip'.format(app_versions['OX_VERSION']), os.path.join(gluu_app_dir,'community-edition-setup.zip'))
    download('https://ox.gluu.org/npm/passport/passport-{}.tgz'.format(app_versions['OX_VERSION']), os.path.join(gluu_app_dir,'passport.tgz'))
    download('https://ox.gluu.org/npm/passport/passport-version_{}-node_modules.tar.gz'.format(app_versions['OX_VERSION']), os.path.join(gluu_app_dir,'passport-version_{}-node_modules.tar.gz'.format(app_versions['OX_VERSION'])))
    download('https://ox.gluu.org/maven/org/gluu/oxshibbolethIdp/{0}{1}/oxshibbolethIdp-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'shibboleth-idp.jar'))
    download('https://ox.gluu.org/maven/org/gluu/oxshibbolethIdp/{0}{1}/oxshibbolethIdp-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'idp.war'))
    download('https://ox.gluu.org/maven/org/gluu/super-gluu-radius-server/{0}{1}/super-gluu-radius-server-{0}{1}.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'super-gluu-radius-server.jar'))
    download('https://ox.gluu.org/maven/org/gluu/super-gluu-radius-server/{0}{1}/super-gluu-radius-server-{0}{1}-distribution.zip'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'gluu-radius-libs.zip'))
    download('https://ox.gluu.org/maven/org/gluu/oxShibbolethKeyGenerator/{0}{1}/oxShibbolethKeyGenerator-{0}{1}.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'idp3_cml_keygenerator.jar'))

    for uf in services:
        download('https://raw.githubusercontent.com/GluuFederation/community-edition-package/master/package/systemd/{}'.format(uf), os.path.join('/etc/systemd/system', uf))
    package_oxd()


# we need some files form community-edition-setup.zip
ces = os.path.join(gluu_app_dir, 'community-edition-setup.zip')
ces_zip = zipfile.ZipFile(ces)
ces_par_dir = ces_zip.namelist()[0]

def extract_from_ces(src, target_fn):
    dst = os.path.join(app_dir, target_fn)
    print("Extracting {} from community-edition-setup.zip to {}".format(src, dst))
    content = ces_zip.read(os.path.join(ces_par_dir, src))
    p, f = os.path.split(dst)
    if not os.path.exists(p):
        os.makedirs(p)
    with open(dst, 'wb') as w:
        w.write(content)

extract_from_ces('templates/jetty.conf.tmpfiles.d', 'jetty.conf')
shutil.copy(os.path.join(gluu_app_dir, 'facter'), '/usr/bin')
os.chmod('/usr/bin/facter', 33261)

npyscreen_package = os.path.join(app_dir, 'npyscreen-master.zip')

site_libdir = site.getsitepackages()[0]
dest_dir = os.path.join(site_libdir, 'npyscreen')

if not os.path.exists(dest_dir):
    print("Extracting npyscreen to", dest_dir)
    npyzip = zipfile.ZipFile(npyscreen_package)
    parent_dir = npyzip.filelist[0].filename
    target_dir = '/tmp/npyscreen_tmp'
    npyzip.extractall(target_dir)
    npyzip.close()

    shutil.copytree(
        os.path.join(target_dir, parent_dir, 'npyscreen'),
        dest_dir
        )

    shutil.rmtree(target_dir)


target_dir = '/tmp/{}/ces_tmp'.format(os.urandom(5).hex())

if os.path.exists(ces_dir):
    shutil.rmtree(ces_dir)

ces_zip.extractall(target_dir)

for gdir in (ces_dir, certs_dir):
    if not os.path.exists(gdir):
        os.makedirs(gdir)

shutil.copy(os.path.join(gluu_app_dir, 'casa.pub'), certs_dir)


print("Extracting community-edition-setup package")
source_dir = os.path.join(target_dir, ces_par_dir)
ces_zip.close()

cmd = 'cp -r -f {}* /install/community-edition-setup'.format(source_dir)
os.system(cmd)

shutil.rmtree(target_dir)

os.chmod('/install/community-edition-setup/setup.py', 33261)



print("Launcing Gluu Setup")
setup_cmd = 'python3 {}/setup.py'.format(ces_dir)
os.system(setup_cmd)
