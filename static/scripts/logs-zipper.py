#!/usr/bin/python

import os
import sys
import zipfile

root_path = ''
version_info = ''
directory_list = {'oxauth': '/opt/gluu/jetty/oxauth/logs/',
                  'identity': '/opt/gluu/jetty/identity/logs/',
                  'idp': '/opt/gluu/jetty/idp/logs/',
                  'setup': '/install/community-edition-setup/',
                  'shibboleth': '/opt/shibboleth-idp/logs/',
                  'oxauth-rp': '/opt/gluu/jetty/oxauth-rp/logs/',
                  'redis': '/opt/gluu/node/passport/node_modules/redis-parser/',
                  'apache': '/var/log/apache2/',
                  'passport': '/opt/gluu/node/passport/logs'}

# to check file is running from out side of gluu-server
if os.path.exists('/opt/gluu/jetty/oxauth'):
    version_info = os.popen('/opt/gluu/bin/show_version.py').read()
else:
    root_path = '/opt/gluu-server'
    version_info = os.popen('/sbin/gluu-serverd version').read()

if version_info == '':
    sys.exit('Run this program as a root user')

handle = zipfile.ZipFile('All_logs.zip', 'w')

for directory_name in directory_list:
    path = root_path + directory_list[directory_name]
    if os.path.exists(path):
        os.chdir(path)
        for file in os.listdir():
            if file.endswith('.log'):
                handle.write(file,
                             os.path.relpath(os.path.join(directory_name, file), path),
                             compress_type=zipfile.ZIP_DEFLATED)

handle.writestr('version_info.txt', version_info)
handle.close()
