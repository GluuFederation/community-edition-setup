#!/usr/bin/python3

import os
import sys
import json
import zipfile
import tarfile
import shutil
import site
import argparse
import csv
import locale
import re
from urllib import request
from urllib.parse import urljoin


parser = argparse.ArgumentParser(description="This script downloads Gluu Server components and fires setup")
parser.add_argument('-a', help=argparse.SUPPRESS, action='store_true')
parser.add_argument('-u', help="Use downloaded components", action='store_true')
parser.add_argument('-upgrade', help="Upgrade Gluu war and jar files", action='store_true')
parser.add_argument('-uninstall', help="Uninstall Gluu server and removes all files", action='store_true')
parser.add_argument('--args', help="Arguments to be passed to setup.py")
parser.add_argument('--keep-downloads', help="Keep downloaded files", action='store_true')
if '-a' in sys.argv:
    parser.add_argument('--jetty-version', help="Jetty verison. For example 11.0.6")
parser.add_argument('-n', help="No prompt", action='store_true')
parser.add_argument('--no-setup', help="Do not launch setup", action='store_true')
parser.add_argument('--dist-server-base', help="Download server", default='https://ox.gluu.org/maven')


argsp = parser.parse_args()

maven_base = argsp.dist_server_base.rstrip('/')

cur_dir = os.path.dirname(os.path.realpath(__file__))
gluu_app_dir = '/opt/dist/gluu'
app_dir = '/opt/dist/app'
ces_dir = '/install/community-edition-setup'
scripts_dir = '/opt/dist/scripts'
certs_dir = '/etc/certs'

os_type, os_version = '', ''

os_release_fn = '/usr/lib/os-release'
if not os.path.exists(os_release_fn):
    os_release_fn = '/etc/os-release'

with open(os_release_fn) as f:
    reader = csv.reader(f, delimiter="=")
    for row in reader:
        if row:
            if row[0] == 'ID':
                os_type = row[1].lower()
                if os_type in ('rhel', 'redhat'):
                    os_type = 'red'
                elif 'ubuntu-core' in os_type:
                    os_type = 'ubuntu'
            elif row[0] == 'VERSION_ID':
                os_version = row[1].split('.')[0]
cmdline = False

try:
    locale.setlocale(locale.LC_ALL, '')
except:
    cmdline = True

missing_packages = []

try:
    import ldap3
except:
    missing_packages.append('python3-ldap3')

try:
    import six
except:
    missing_packages.append('python3-six')

try:
    import ruamel.yaml
except:
    if os_type in ('red', 'centos'):
        missing_packages.append('python3-ruamel-yaml')
    else:
        missing_packages.append('python3-ruamel.yaml')

try:
    from distutils import dist
except:
    missing_packages.append('python3-distutils')

try:
    import pymysql
except:
    if os_type in ('red', 'centos'):
        missing_packages.append('python3-PyMySQL')
    else:
        missing_packages.append('python3-pymysql')


if not shutil.which('unzip'):
    missing_packages.append('unzip')

if not shutil.which('tar'):
    missing_packages.append('tar')

rpm_clone = shutil.which('rpm')

if missing_packages:
    packages_str = ' '.join(missing_packages)
    if not argsp.n:
        result = input("Missing package(s): {0}. Install now? (Y|n): ".format(packages_str))
        if result.strip() and result.strip().lower()[0] == 'n':
            sys.exit("Can't continue without installing these packages. Exiting ...")

    if rpm_clone:
        cmd = 'yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-{}.noarch.rpm'.format(os_version)
        os.system(cmd)
        cmd = 'yum clean all'
        os.system(cmd)
        cmd = "yum install -y {0}".format(packages_str)
    else:
        os.system('apt-get update')
        cmd = "apt-get install -y {0}".format(packages_str)

    print ("Installing package(s) with command: "+ cmd)
    if os_type+os_version == 'centos7':
        cmd = cmd.replace('python3-six', 'python36-six')

    os.system(cmd)


if not os.path.exists(scripts_dir):
    os.makedirs(scripts_dir)


jetty_home = '/opt/gluu/jetty'
services = ['casa.service', 'identity.service', 'opendj.service', 'oxauth.service', 'passport.service', 'fido2.service', 'idp.service', 'oxd-server.service', 'scim.service']
app_versions = {
    "JETTY_VERSION": "9.4.43.v20210629", 
    "AMAZON_CORRETTO_VERSION": "11.0.8.10.1", 
    "OX_GITVERISON": "-SNAPSHOT", 
    "NODE_VERSION": "v14.16.1",
    "OX_VERSION": "4.3.1", 
    "JYTHON_VERSION": "2.7.2",
    "OPENDJ_VERSION": "4.4.12",
    "SETUP_BRANCH": "version_4.3.1",
    "TWILIO_VERSION": "7.17.0",
    "JSMPP_VERSION": "2.3.7"
    }

jetty_dist_string = 'jetty-distribution'
if getattr(argsp, 'jetty_version', None):
    result = re.findall('(\d*).', argsp.jetty_version)
    if result and result[0] and result[0].isdigit():
        if int(result[0]) > 9:
            jetty_dist_string = 'jetty-home'
            app_versions['JETTY_VERSION'] = argsp.jetty_version
    else:
        print("Can't determine Jetty Version. Continuing with version {}".format(app_versions['JETTY_VERSION']))

def check_installation():
    if not (os.path.exists(jetty_home) and os.path.exists('/etc/gluu')):
        print("Gluu server seems not installed")
        sys.exit()

if argsp.uninstall:
    check_installation()
    print('\033[31m')
    print("This process is irreversible.")
    print("You will lose all data related to Gluu Server.")
    print('\033[0m')
    print()
    if not argsp.n:
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
    request.urlretrieve(url, dst)


def download_gcs():
    if not os.path.exists(os.path.join(app_dir, 'gcs')):
        print("Downloading Spanner modules")
        gcs_download_url = 'http://162.243.99.240/icrby8xcvbcv/spanner/gcs.tgz'
        tmp_dir = '/tmp/' + os.urandom(5).hex()
        target_fn = os.path.join(tmp_dir, 'gcs.tgz')
        download(gcs_download_url, target_fn)
        shutil.unpack_archive(target_fn, app_dir)

        req = request.urlopen('https://pypi.org/pypi/grpcio/1.37.0/json')
        data_s = req.read()
        data = json.loads(data_s)

        pyversion = 'cp{0}{1}'.format(sys.version_info.major, sys.version_info.minor)

        package = {}

        for package_ in data['urls']:

            if package_['python_version'] == pyversion and 'manylinux' in package_['filename'] and package_['filename'].endswith('x86_64.whl'):
                if package_['upload_time'] > package.get('upload_time',''):
                    package = package_

        if package.get('url'):
            target_whl_fn = os.path.join(tmp_dir, os.path.basename(package['url']))
            download(package['url'], target_whl_fn)
            whl_zip = zipfile.ZipFile(target_whl_fn)

            for member in  whl_zip.filelist:
                fn = os.path.basename(member.filename)
                if fn.startswith('cygrpc.cpython') and fn.endswith('x86_64-linux-gnu.so'):
                    whl_zip.extract(member, os.path.join(app_dir, 'gcs'))

            whl_zip.close()

        shutil.rmtree(tmp_dir)


def package_oxd():
    oxd_tgz_fn = os.path.join(gluu_app_dir, 'oxd-server.tgz')
    oxd_zip_fn = os.path.join(gluu_app_dir, 'oxd-server.zip')
    oxd_tmp_root = '/tmp/{}'.format(os.urandom(5).hex())
    oxd_tmp_dir = os.path.join(oxd_tmp_root, 'oxd-server')
    download(maven_base + '/org/gluu/oxd-server/{0}{1}/oxd-server-{0}{1}-distribution.zip'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), oxd_zip_fn)
    download('https://raw.githubusercontent.com/GluuFederation/community-edition-package/master/package/systemd/oxd-server.service', os.path.join(oxd_tmp_dir, 'oxd-server.service'))
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
    download('https://repo1.maven.org/maven2/org/eclipse/jetty/{1}/{0}/{1}-{0}.tar.gz'.format(app_versions['JETTY_VERSION'], jetty_dist_string), os.path.join(app_dir,'{1}-{0}.tar.gz'.format(app_versions['JETTY_VERSION'], jetty_dist_string)))
    download('https://repo1.maven.org/maven2/org/python/jython-installer/{0}/jython-installer-{0}.jar'.format(app_versions['JYTHON_VERSION']), os.path.join(app_dir, 'jython-installer-{0}.jar'.format(app_versions['JYTHON_VERSION'])))
    download('https://nodejs.org/dist/{0}/node-{0}-linux-x64.tar.xz'.format(app_versions['NODE_VERSION']), os.path.join(app_dir, 'node-{0}-linux-x64.tar.xz'.format(app_versions['NODE_VERSION'])))
    download('https://github.com/npcole/npyscreen/archive/master.zip', os.path.join(app_dir, 'npyscreen-master.zip'))
    download(maven_base + '/org/gluufederation/opendj/opendj-server-legacy/{0}/opendj-server-legacy-{0}.zip'.format(app_versions['OPENDJ_VERSION']), os.path.join(app_dir,'opendj-server-{0}.zip'.format(app_versions['OPENDJ_VERSION'])))
    download(maven_base + '/org/gluu/oxauth-server/{0}{1}/oxauth-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'oxauth.war'))
    download(maven_base + '/org/gluu/oxtrust-server/{0}{1}/oxtrust-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'identity.war'))
    download(maven_base + '/org/gluu/oxauth-client/{0}{1}/oxauth-client-{0}{1}-jar-with-dependencies.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'oxauth-client-jar-with-dependencies.jar'))
    download(maven_base + '/org/gluu/casa/{0}{1}/casa-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'casa.war'))
    download('https://repo1.maven.org/maven2/com/twilio/sdk/twilio/{0}/twilio-{0}.jar'.format(app_versions['TWILIO_VERSION']), os.path.join(gluu_app_dir,'twilio-{0}.jar'.format(app_versions['TWILIO_VERSION'])))
    download('https://repo1.maven.org/maven2/org/jsmpp/jsmpp/{0}/jsmpp-{0}.jar'.format(app_versions['JSMPP_VERSION']), os.path.join(gluu_app_dir,'jsmpp-{0}.jar'.format(app_versions['JSMPP_VERSION'])))
    download('https://github.com/GluuFederation/casa/raw/version_{}/extras/casa.pub'.format(app_versions['OX_VERSION']), os.path.join(gluu_app_dir,'casa.pub'))
    download('https://raw.githubusercontent.com/GluuFederation/casa/master/plugins/account-linking/extras/login.xhtml', os.path.join(gluu_app_dir,'login.xhtml'))
    download('https://raw.githubusercontent.com/GluuFederation/casa/master/plugins/account-linking/extras/casa.py', os.path.join(gluu_app_dir,'casa.py'))
    download('https://raw.githubusercontent.com/GluuFederation/gluu-snap/master/facter/facter', os.path.join(gluu_app_dir,'facter'))
    download(maven_base + '/org/gluu/scim-server/{0}{1}/scim-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'scim.war'))
    download(maven_base + '/org/gluu/fido2-server/{0}{1}/fido2-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'fido2.war'))
    download('https://raw.githubusercontent.com/GluuFederation/oxd/master/debian/oxd-server', os.path.join(gluu_app_dir,'oxd-server-start.sh'))
    download('https://github.com/GluuFederation/community-edition-setup/archive/{}.zip'.format(app_versions['SETUP_BRANCH']), os.path.join(gluu_app_dir,'community-edition-setup.zip'))
    download('https://ox.gluu.org/npm/passport/passport-{}.tgz'.format(app_versions['OX_VERSION']), os.path.join(gluu_app_dir,'passport.tgz'))
    download('https://ox.gluu.org/npm/passport/passport-version_{}-node_modules.tar.gz'.format(app_versions['OX_VERSION']), os.path.join(gluu_app_dir,'passport-version_{}-node_modules.tar.gz'.format(app_versions['OX_VERSION'])))
    download(maven_base + '/org/gluu/oxShibbolethStatic/{0}{1}/oxShibbolethStatic-{0}{1}.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'shibboleth-idp.jar'))
    download(maven_base + '/org/gluu/oxshibbolethIdp/{0}{1}/oxshibbolethIdp-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'idp.war'))
    download(maven_base + '/org/gluu/super-gluu-radius-server/{0}{1}/super-gluu-radius-server-{0}{1}.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'super-gluu-radius-server.jar'))
    download(maven_base + '/org/gluu/super-gluu-radius-server/{0}{1}/super-gluu-radius-server-{0}{1}-distribution.zip'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'gluu-radius-libs.zip'))
    download(maven_base + '/org/gluu/oxShibbolethKeyGenerator/{0}{1}/oxShibbolethKeyGenerator-{0}{1}.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'idp3_cml_keygenerator.jar'))
    download('https://github.com/sqlalchemy/sqlalchemy/archive/rel_1_3_23.zip', os.path.join(app_dir, 'sqlalchemy.zip'))
    download('https://www.apple.com/certificateauthority/Apple_WebAuthn_Root_CA.pem', os.path.join(app_dir, 'Apple_WebAuthn_Root_CA.pem'))

    if not argsp.upgrade:
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

if not argsp.upgrade and os.path.exists(ces_dir):
    shutil.rmtree(ces_dir)

ces_zip.extractall(target_dir)

for gdir in (ces_dir, certs_dir):
    if not os.path.exists(gdir):
        os.makedirs(gdir)

shutil.copy(os.path.join(gluu_app_dir, 'casa.pub'), certs_dir)


if argsp.upgrade:

    check_installation()

    for service in os.listdir(jetty_home):
        source_fn = os.path.join(gluu_app_dir, service +'.war')
        target_fn = os.path.join(jetty_home, service, 'webapps', service +'.war' )
        print("Updating", target_fn)
        shutil.copy(source_fn, target_fn)
        print("Restarting", service)
        os.system('systemctl restart ' + service)

    if os.path.exists('/opt/oxd-server'):
        print("Updating oxd-server")
        oxd_tar = tarfile.open('/opt/dist/gluu/oxd-server.tgz')

        for member in oxd_tar.getmembers():
            if member.isfile() and member.path.startswith('oxd-server/lib'):
                oxd_tar.extract(member, '/opt')

        print("Restarting oxd-server")
        os.system('systemctl restart oxd-server')


else:
    print("Extracting community-edition-setup package")
    source_dir = os.path.join(target_dir, ces_par_dir)
    ces_zip.close()

    cmd = 'cp -r -f {}* /install/community-edition-setup'.format(source_dir)
    os.system(cmd)

    shutil.rmtree(target_dir)

    download_gcs()

    sqlalchemy_zfn = os.path.join(app_dir, 'sqlalchemy.zip')
    sqlalchemy_zip = zipfile.ZipFile(sqlalchemy_zfn, "r")
    sqlalchemy_par_dir = sqlalchemy_zip.namelist()[0]
    tmp_dir = os.path.join('/tmp', os.urandom(2).hex())
    sqlalchemy_zip.extractall(tmp_dir)
    shutil.copytree(
            os.path.join(tmp_dir, sqlalchemy_par_dir, 'lib/sqlalchemy'), 
            os.path.join(ces_dir, 'setup_app/pylib/sqlalchemy')
            )
    shutil.rmtree(tmp_dir)

    os.chmod('/install/community-edition-setup/setup.py', 33261)

    gluu_install = '/install/community-edition-setup/gluu_install.py'
    if os.path.exists(gluu_install):
        os.remove(gluu_install)

    if not argsp.no_setup:
        print("Launching Gluu Setup")
        setup_cmd = 'python3 {}/setup.py'.format(ces_dir)
        if argsp.args:
            setup_cmd += ' ' + argsp.args

        os.system(setup_cmd)
