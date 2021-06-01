#!/usr/bin/python3

import os
import sys
import zipfile
import argparse
from datetime import datetime

directory_list = {'oxauth': '/opt/gluu/jetty/oxauth/logs/',
                  'scim': '/opt/gluu/jetty/scim/logs/',
                  'identity': '/opt/gluu/jetty/identity/logs/',
                  'idp': '/opt/gluu/jetty/idp/logs/',
                  'setup': '/install/community-edition-setup/',
                  'shibboleth': '/opt/shibboleth-idp/logs/',
                  'oxauth-rp': '/opt/gluu/jetty/oxauth-rp/logs/',
                  'redis': '/opt/gluu/node/passport/node_modules/redis-parser/',
                  'apache': '/var/log/apache2/',
                  'passport': '/opt/gluu/node/passport/logs/',
                  'opendj': '/opt/opendj/logs/',
                  'casa': '/opt/gluu/jetty/casa/logs/',
                  'fido2': '/opt/gluu/jetty/fido2/logs/',
                  'radius': '/opt/gluu/radius/logs'}


def error():
    print("Invalid command; Please use: -h or --help to get valid information")


def zipper(final_attr):
    root_path = ''

    # to check file is running from out side of gluu-server
    if os.path.exists('/opt/gluu/bin/show_version.py'):
        version = os.popen('/opt/gluu/bin/show_version.py').read()

    elif os.path.exists('/sbin/gluu-serverd'):
        root_path = '/opt/gluu-server'
        version = os.popen('/sbin/gluu-serverd version').read()

    else:
        version = 'This script supports only version 4.0 or later.'

    if final_attr is None:
        print('No logs are found.')
        return

    handle = zipfile.ZipFile(datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + '_All_logs.zip', 'w')
    print('Zipper is started...\n')

    for directory_name in final_attr:
        path = root_path + directory_list[directory_name]
        if os.path.exists(path):
            os.chdir(path)
            print('Zipper is running for ' + directory_name + '...')
            for file in os.listdir('.'):
                if file.endswith('.log') or file.endswith('.txt'):
                    handle.write(file,
                                 os.path.relpath(os.path.join(directory_name, file), path),
                                 compress_type=zipfile.ZIP_DEFLATED)
        else:
            print(directory_name + ' logs are not available...')

    handle.writestr('version_info.txt', version)
    print('\nZipper process has been finished.\nLogs are zipped in All_logs.zip')
    handle.close()


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("--all", help="Add all logs", action="store_true")
    parser.add_argument("--add", nargs="+", help="enter each name separately to add into zip file.['oxauth', "
                                                 "'identity', 'idp', 'setup', 'shibboleth', 'oxauth-rp', 'redis', "
                                                 "'apache', 'passport', 'scim', 'radius', 'casa', 'fido2', 'opendj'];"
                                                 "for example: logs-zipper.py --add 'apache' 'idp' 'setup' ")

    parser.add_argument("--del", nargs="+", help="enter each name separately to exclude from zip file, ['oxauth', "
                                                 "'identity', 'idp', 'setup', 'shibboleth', 'oxauth-rp', 'redis', "
                                                 "'apache', 'passport', 'scim', 'radius', 'casa', 'fido2', 'opendj'];"
                                                 "for example: logs-zipper.py --del 'apache' 'idp' 'setup' ")
    args = parser.parse_args()

    if len(sys.argv) <= 1 or args.all:
        zipper(directory_list.keys())
    else:
        if args.__dict__['all']:
            zipper(directory_list.keys())
        elif args.__dict__['add']:
            final_attributes = list(set(directory_list.keys()).intersection(args.__dict__['add']))
            if len(final_attributes) != len(args.__dict__['add']):
                error()
            else:
                zipper(final_attributes)
        elif args.__dict__['del']:
            final_attributes = list(set(directory_list.keys()) - set(args.__dict__['del']))
            zipper(final_attributes)
        else:
            error()

    sys.exit()
