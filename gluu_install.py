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
import shlex
import subprocess
from pathlib import Path
from urllib import request
from urllib.parse import urljoin
from tempfile import TemporaryDirectory

sys.path.append('/usr/lib/python{}.{}/gluu-packaged'.format(sys.version_info.major, sys.version_info.minor))

sys.path.append('/usr/lib/python{}.{}/gluu-packaged'.format(sys.version_info.major, sys.version_info.minor))

parser = argparse.ArgumentParser(description="This script downloads Gluu Server components and fires setup")
parser.add_argument('-a', help=argparse.SUPPRESS, action='store_true')
parser.add_argument('-u', help="Use downloaded components", action='store_true')
parser.add_argument('-upgrade', help="Upgrade Gluu war and jar files", action='store_true')
parser.add_argument('-uninstall', help="Uninstall Gluu server and removes all files", action='store_true')
parser.add_argument('--args', help="Arguments to be passed to setup.py")
parser.add_argument('--keep-downloads', help="Keep downloaded files", action='store_true')

if '-a' in sys.argv:
    parser.add_argument('--jetty-version', help="Jetty verison. For example 11.0.6")
    parser.add_argument('-k', help="Don't validate the server's certificate", action='store_true')

if '-uninstall' not in sys.argv:
    parser.add_argument('-maven-user', help="Maven username", required=True)
    parser.add_argument('-maven-password', help="Maven password", required=True)

parser.add_argument('-n', help="No prompt", action='store_true')
parser.add_argument('--no-setup', help="Do not launch setup", action='store_true')
parser.add_argument('--dist-server-base', help="Download server", default='https://maven.gluu.org/maven')
parser.add_argument('-profile', help="Setup profile", choices=['CE', 'DISA-STIG'], default='CE')
parser.add_argument('--setup-branch', help="Gluu CE setup github branch", default="version_4.5.5")
parser.add_argument('-c', help="Don't download files that exists on disk", action='store_true')

argsp = parser.parse_args()

if '-a' in sys.argv and argsp.k:
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context

maven_base = argsp.dist_server_base.rstrip('/')
maven_root = '/'.join(maven_base.split('/')[:-1]).rstrip('/')


cur_dir = os.path.dirname(os.path.realpath(__file__))
opt_dist_dir = '/var/gluu/dist' if argsp.profile == 'DISA-STIG' else '/opt/dist/'
gluu_app_dir = os.path.join(opt_dist_dir, 'gluu')
app_dir = os.path.join(opt_dist_dir, 'app')
ces_dir = '/install/community-edition-setup'
scripts_dir = os.path.join(opt_dist_dir, 'scripts')
certs_dir = '/etc/certs'
pylib_dir = os.path.join(ces_dir, 'setup_app/pylib/')

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
                elif 'sles' in os_type or 'suse' in os_type:
                    os_type = 'suse'
            elif row[0] == 'VERSION_ID':
                os_version = row[1].split('.')[0]

cmdline = False

if os_type in ('red', 'centos'):
    package_installer = 'yum'
elif os_type in ('ubuntu', 'debian'):
    package_installer = 'apt'
elif os_type in ('suse'):
    package_installer = 'zypper'
else:
    print("Unsopported OS. Exiting ...")
    sys.exit()

if os_type == 'debian':
    path_list = [ '/usr/local/sbin', '/usr/sbin', '/sbin', '/usr/local/bin', '/usr/bin', '/bin' ]
    os.environ['PATH'] = os.pathsep.join(path_list) + os.pathsep + os.environ['PATH']

print("OS type was determined as {}.".format(os_type))

try:
    locale.setlocale(locale.LC_ALL, '')
except:
    cmdline = True

missing_packages = []

if not argsp.uninstall:

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
        if os_type in ('red', 'centos', 'suse'):
            missing_packages.append('python3-PyMySQL')
        else:
            missing_packages.append('python3-pymysql')

    try:
        import psycopg2
    except:
        missing_packages.append('python3-psycopg2')

    if not shutil.which('unzip'):
        missing_packages.append('unzip')

    if not shutil.which('tar'):
        missing_packages.append('tar')

    rpm_clone = shutil.which('rpm')
    deb_clone = shutil.which('deb')

    if missing_packages:
        packages_str = ' '.join(missing_packages)
        if os_type+os_version in ('centos9'):
            packages_str = packages_str.replace('python3-', 'python-')
        if not argsp.n:
            result = input("Missing package(s): {0}. Install now? (Y|n): ".format(packages_str))
            if result.strip() and result.strip().lower()[0] == 'n':
                sys.exit("Can't continue without installing these packages. Exiting ...")

        if os_type in ('red', 'centos'):
            print("Installing epel-release")
            cmd = '{} install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-{}.noarch.rpm'.format(package_installer, os_version)
            os.system(cmd)
            cmd = '{} clean all'
            os.system(cmd)
            print("Enabling CRB repository")
            os.system('/usr/bin/crb enable')

        elif deb_clone:
            subprocess.run(shlex.split('{} update'.format(package_installer)))

        cmd = "{} install -y {}".format(package_installer, packages_str)

        if os_type+os_version == 'centos7':
            cmd = cmd.replace('python3-six', 'python36-six')
            cmd = cmd.replace('python3-ruamel-yaml', 'python36-ruamel-yaml')

        os.system(cmd)


if not os.path.exists(scripts_dir):
    os.makedirs(scripts_dir)

oxauth_war_fn = os.path.join(gluu_app_dir, 'oxauth.war')
jetty_home = '/opt/gluu/jetty'
services = ['casa.service', 'identity.service', 'opendj.service', 'oxauth.service', 'passport.service', 'fido2.service', 'idp.service', 'oxd-server.service', 'scim.service']
app_versions = {
    "JETTY_VERSION": "10.0.18",
    "AMAZON_CORRETTO_VERSION": "11.0.24.8.1",
    "OX_GITVERISON": "-SNAPSHOT",
    "NODE_VERSION": "v16.16.0",
    "OX_VERSION": "4.5.6", 
    "PASSPORT_VERSION": "4.5.6",
    "JYTHON_VERSION": "2.7.3",
    "OPENDJ_VERSION": "4.5.3",
    "SETUP_BRANCH": argsp.setup_branch,
    "TWILIO_VERSION": "7.17.0",
    "JSMPP_VERSION": "2.3.7",
    "APPS_GIT_BRANCH": "master",
    }

jetty_dist_string = 'jetty-distribution'
if hasattr(argsp, 'jetty_version'):
    app_versions['JETTY_VERSION'] = argsp.jetty_version

result = re.findall('(\d*).', app_versions['JETTY_VERSION'])

if result and result[0] and result[0].isdigit() and int(result[0]) > 9:
    jetty_dist_string = 'jetty-home'


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

    if os.path.exists('/opt/opendj/bin/stop-ds'):
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
    remove_list = ['/etc/certs', '/etc/gluu', '/opt/gluu', '/opt/amazon-corretto*', '/opt/jre', '/opt/jetty*', '/opt/jython*', '/opt/opendj', '/opt/node*',  '/opt/oxd-server',  '/opt/shibboleth-idp', '/var/gluu/identity/cr-snapshots/*']
    if not argsp.keep_downloads:
        remove_list.append('/opt/dist')

    for p in remove_list:
        cmd = 'rm -r -f ' + p
        print("Executing", cmd)
        os.system('rm -r -f ' + p)

    apache_conf_fn_list = []

    if shutil.which('zypper'):
        apache_conf_fn_list = ['/etc/apache2/vhosts.d/_https_gluu.conf']
    elif shutil.which('yum') or shutil.which('dnf'):
        apache_conf_fn_list = ['/etc/httpd/conf.d/https_gluu.conf']
    elif shutil.which('apt'):
        apache_conf_fn_list = ['/etc/apache2/sites-enabled/https_gluu.conf', '/etc/apache2/sites-available/https_gluu.conf']

    for fn in apache_conf_fn_list:
        if os.path.exists(fn):
            print("Removing", fn)
            os.unlink(fn)

    sys.exit()


passman = request.HTTPPasswordMgrWithDefaultRealm()
passman.add_password(None, maven_root, argsp.maven_user, argsp.maven_password)
authhandler = request.HTTPBasicAuthHandler(passman)
opener = request.build_opener(authhandler)
request.install_opener(opener)


def download(url, target_fn):
    dst = os.path.join(app_dir, target_fn)
    pardir, fn = os.path.split(dst)
    if not os.path.exists(pardir):
        os.makedirs(pardir)

    print("Opening url", url)


    with request.urlopen(url) as resp:
        if argsp.c and os.path.exists(dst) and resp.length == os.stat(dst).st_size:
            print("File", dst, "exists. Passing")
            return

        print("Downloading", url, "to", dst)
        with open(dst, 'wb') as out_file :
            shutil.copyfileobj(resp, out_file)


def extract_subdir(zip_fn, sub_dir, target_dir, par_dir=None):
    target_fp = os.path.join(target_dir, os.path.basename(sub_dir))
    if os.path.exists(target_fp):
        return

    zip_obj = zipfile.ZipFile(zip_fn, "r")
    if par_dir is None:
        par_dir = zip_obj.namelist()[0]

    with TemporaryDirectory() as unpack_dir:
        zip_obj.extractall(unpack_dir)
        shutil.copytree(
            os.path.join(unpack_dir, par_dir, sub_dir),
            target_fp
            )
    zip_obj.close()


def package_oxd():
    oxd_tgz_fn = os.path.join(gluu_app_dir, 'oxd-server.tgz')
    oxd_zip_fn = os.path.join(gluu_app_dir, 'oxd-server.zip')
    oxd_tmp_root = '/tmp/{}'.format(os.urandom(5).hex())
    oxd_tmp_dir = os.path.join(oxd_tmp_root, 'oxd-server')

    if argsp.profile != 'DISA-STIG':
        download(maven_base + '/org/gluu/oxd-server/{0}{1}/oxd-server-{0}{1}-distribution.zip'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), oxd_zip_fn)
    else:
        download(maven_base + '/org/gluu/oxd-server/{0}{1}/oxd-server-{0}{1}-distribution-bc-fips.zip'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), oxd_zip_fn)

    download('https://raw.githubusercontent.com/GluuFederation/community-edition-package/{}/package/systemd/oxd-server.service'.format(app_versions['APPS_GIT_BRANCH']), os.path.join(oxd_tmp_dir, 'oxd-server.service'))

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

    if argsp.profile != 'DISA-STIG':
        download('https://corretto.aws/downloads/resources/{0}/amazon-corretto-{0}-linux-x64.tar.gz'.format(app_versions['AMAZON_CORRETTO_VERSION']), os.path.join(app_dir, 'amazon-corretto-{0}-linux-x64.tar.gz'.format(app_versions['AMAZON_CORRETTO_VERSION'])))
        download('https://nodejs.org/dist/{0}/node-{0}-linux-x64.tar.xz'.format(app_versions['NODE_VERSION']), os.path.join(app_dir, 'node-{0}-linux-x64.tar.xz'.format(app_versions['NODE_VERSION'])))
        download(maven_root + '/npm/passport/passport-{}.tgz'.format(app_versions['PASSPORT_VERSION']), os.path.join(gluu_app_dir,'passport.tgz'))
        download(maven_root + '/npm/passport/passport-version_{}-node_modules.tar.gz'.format(app_versions['PASSPORT_VERSION']), os.path.join(gluu_app_dir,'passport-version_{}-node_modules.tar.gz'.format(app_versions['PASSPORT_VERSION'])))
        download(maven_base + '/org/gluu/super-gluu-radius-server/{0}{1}/super-gluu-radius-server-{0}{1}.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'super-gluu-radius-server.jar'))
        download(maven_base + '/org/gluu/super-gluu-radius-server/{0}{1}/super-gluu-radius-server-{0}{1}-distribution.zip'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'gluu-radius-libs.zip'))
        download('https://www.apple.com/certificateauthority/Apple_WebAuthn_Root_CA.pem', os.path.join(app_dir, 'Apple_WebAuthn_Root_CA.pem'))
        download(maven_base + '/org/gluu/oxShibbolethStatic/{0}{1}/oxShibbolethStatic-{0}{1}.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'shibboleth-idp.jar'))
        download(maven_base + '/org/gluu/oxshibbolethIdp/{0}{1}/oxshibbolethIdp-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'idp.war'))
        download(maven_base + '/org/gluu/oxShibbolethKeyGenerator/{0}{1}/oxShibbolethKeyGenerator-{0}{1}.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'idp3_cml_keygenerator.jar'))
        download('https://www.apple.com/certificateauthority/Apple_WebAuthn_Root_CA.pem', os.path.join(app_dir, 'Apple_WebAuthn_Root_CA.pem'))
        download(maven_base + '/org/gluu/oxauth-server/{0}{1}/oxauth-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'oxauth.war'))
        download(maven_base + '/org/gluu/scim-server/{0}{1}/scim-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'scim.war'))
        download(maven_base + '/org/gluu/fido2-server/{0}{1}/fido2-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'fido2.war'))
        download(maven_base + '/org/gluu/casa/{0}{1}/casa-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'casa.war'))
        download(maven_base + '/org/gluu/oxtrust-server/{0}{1}/oxtrust-server-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'identity.war'))
        download(maven_base + '/org/gluu/gluu-orm-spanner-libs/{0}{1}/gluu-orm-spanner-libs-{0}{1}-distribution.zip'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'gluu-orm-spanner-libs-distribution.zip'))
        download(maven_base + '/org/gluu/gluu-orm-couchbase-libs/{0}{1}/gluu-orm-couchbase-libs-{0}{1}-distribution.zip'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'gluu-orm-couchbase-libs-distribution.zip'))
    else:
        download('https://maven.gluu.org/maven/org/gluu/oxauth-client-jar-without-provider-dependencies/{0}{1}/oxauth-client-jar-without-provider-dependencies-{0}{1}.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir, 'oxauth-client-jar-without-provider-dependencies.jar'))
        download('https://maven.gluu.org/maven/org/gluu/oxauth-server-fips/{0}{1}/oxauth-server-fips-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), oxauth_war_fn)
        download(maven_base + '/org/gluu/scim-server-fips/{0}{1}/scim-server-fips-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'scim.war'))
        download(maven_base + '/org/gluu/fido2-server-fips/{0}{1}/fido2-server-fips-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'fido2.war'))
        download(maven_base + '/org/gluu/casa-fips/{0}{1}/casa-fips-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'casa.war'))
        download(maven_base + '/org/gluu/oxtrust-server-fips/{0}{1}/oxtrust-server-fips-{0}{1}.war'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'identity.war'))

    download(maven_base + '/org/gluu/oxauth-client-jar-with-dependencies/{0}{1}/oxauth-client-jar-with-dependencies-{0}{1}.jar'.format(app_versions['OX_VERSION'], app_versions['OX_GITVERISON']), os.path.join(gluu_app_dir,'oxauth-client-jar-with-dependencies.jar'))
    download('https://repo1.maven.org/maven2/org/eclipse/jetty/{1}/{0}/{1}-{0}.tar.gz'.format(app_versions['JETTY_VERSION'], jetty_dist_string), os.path.join(app_dir,'{1}-{0}.tar.gz'.format(app_versions['JETTY_VERSION'], jetty_dist_string)))
    download(maven_base + '/org/gluufederation/jython-installer/{0}/jython-installer-{0}.jar'.format(app_versions['JYTHON_VERSION']), os.path.join(app_dir, 'jython-installer-{0}.jar'.format(app_versions['JYTHON_VERSION'])))
    download('https://github.com/npcole/npyscreen/archive/master.zip', os.path.join(app_dir, 'npyscreen-master.zip'))
    download(maven_base + '/org/gluufederation/opendj/opendj-server-legacy/{0}/opendj-server-legacy-{0}.zip'.format(app_versions['OPENDJ_VERSION']), os.path.join(app_dir,'opendj-server-{0}.zip'.format(app_versions['OPENDJ_VERSION'])))
    download('https://repo1.maven.org/maven2/com/twilio/sdk/twilio/{0}/twilio-{0}.jar'.format(app_versions['TWILIO_VERSION']), os.path.join(gluu_app_dir,'twilio-{0}.jar'.format(app_versions['TWILIO_VERSION'])))
    download('https://repo1.maven.org/maven2/org/jsmpp/jsmpp/{0}/jsmpp-{0}.jar'.format(app_versions['JSMPP_VERSION']), os.path.join(gluu_app_dir,'jsmpp-{0}.jar'.format(app_versions['JSMPP_VERSION'])))
    download('https://github.com/GluuFederation/casa/raw/{}/extras/casa.pub'.format(app_versions['APPS_GIT_BRANCH']), os.path.join(gluu_app_dir,'casa.pub'))
    download('https://raw.githubusercontent.com/GluuFederation/casa/{}/plugins/account-linking/extras/login.xhtml'.format(app_versions['APPS_GIT_BRANCH']), os.path.join(gluu_app_dir,'login.xhtml'))
    download('https://raw.githubusercontent.com/GluuFederation/casa/{}/plugins/account-linking/extras/casa.py'.format(app_versions['APPS_GIT_BRANCH']), os.path.join(gluu_app_dir,'casa.py'))
    download('https://raw.githubusercontent.com/GluuFederation/gluu-snap/master/facter/facter', os.path.join(gluu_app_dir,'facter'))
    download('https://raw.githubusercontent.com/GluuFederation/oxd/{}/debian/oxd-server'.format(app_versions['APPS_GIT_BRANCH']), os.path.join(gluu_app_dir,'oxd-server-start.sh'))
    download('https://github.com/GluuFederation/community-edition-setup/archive/{}.zip'.format(app_versions['SETUP_BRANCH']), os.path.join(gluu_app_dir,'community-edition-setup.zip'))
    download('https://github.com/sqlalchemy/sqlalchemy/archive/rel_1_3_23.zip', os.path.join(app_dir, 'sqlalchemy.zip'))
    download('https://mds.fidoalliance.org/', os.path.join(app_dir, 'fido2/mds/toc/toc.jwt'))
    download('https://secure.globalsign.com/cacert/root-r3.crt', os.path.join(app_dir, 'fido2/mds/cert/root-r3.crt'))

    download('https://files.pythonhosted.org/packages/7a/46/8b58d6b8244ff613ecb983b9428d1168dd0b014a34e13fb19737b9ba1fc1/cryptography-39.0.0-cp36-abi3-manylinux_2_17_x86_64.manylinux2014_x86_64.whl', os.path.join(app_dir, 'cryptography.whl'))
    download('https://github.com/jpadilla/pyjwt/archive/refs/tags/2.4.0.zip', os.path.join(app_dir, 'pyjwt.zip'))


    if not argsp.upgrade:
        for uf in services:
            download('https://raw.githubusercontent.com/GluuFederation/community-edition-package/{}/package/systemd/{}'.format(app_versions['APPS_GIT_BRANCH'], uf), os.path.join('/etc/systemd/system', uf))
    package_oxd()


shutil.copy(os.path.join(gluu_app_dir, 'facter'), '/usr/bin')
os.chmod('/usr/bin/facter', 33261)
if not os.path.exists(certs_dir):
    os.makedirs(certs_dir)
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
    extract_subdir(
        os.path.join(gluu_app_dir, 'community-edition-setup.zip'),
        '',
        ces_dir
        )

    extract_libs = [
            ('npyscreen-master.zip', 'npyscreen', None)
            ]
    if argsp.profile != 'DISA-STIG':
        extract_libs += [
                    ('sqlalchemy.zip', 'lib/sqlalchemy', None),
                    ('cryptography.whl', 'cryptography', ''),
                    ('pyjwt.zip', 'jwt', None)
                    ]

    for zip_fn, sub_dir, par_dir in extract_libs:
        print("Extracting", zip_fn)
        extract_subdir(os.path.join(app_dir, zip_fn), sub_dir, pylib_dir, par_dir)


    if argsp.profile == 'DISA-STIG':
        open(os.path.join(ces_dir, 'disa-stig'), 'w').close()

    if argsp.profile == 'DISA-STIG':
        war_zip = zipfile.ZipFile(oxauth_war_fn, "r")
        for fn in war_zip.namelist():
            if re.search('bc-fips-(.*?).jar$', fn) or re.search('bcpkix-fips-(.*?).jar$', fn):
                file_name = os.path.basename(fn)
                target_fn = os.path.join(app_dir, file_name)
                print("Extracting", fn, "to", target_fn)
                file_content = war_zip.read(fn)
                with open(target_fn, 'wb') as w:
                    w.write(file_content)
        war_zip.close()

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
