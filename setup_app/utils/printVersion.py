#!/usr/bin/python3
from __future__ import print_function

import re
import zipfile
import glob
import sys
import os
import ssl
import json
import argparse
import datetime

try:
    from urllib.request import urlopen
except:
    from urllib2 import urlopen

ssl._create_default_https_context = ssl._create_unverified_context

repos = {
        'identity': 'oxTrust',
        'oxauth': 'oxAuth',
        'idp': 'oxShibboleth',
        }


def get_latest_commit(service, branch):
    url = 'https://api.github.com/repos/GluuFederation/{0}/commits/{1}'.format(repos[service], branch)
    try:
        f = urlopen(url)
        content = f.read()
        commits = json.loads(content.decode('utf-8'))
        return commits['sha']
    except:
        return "ERROR: Unable to retreive latest commit"

def get_war_info(war_fn):
    retDict = {'title':'', 'version':'', 'build':'', 'buildDate':'', 'branch':''}
    war_zip = zipfile.ZipFile(war_fn, 'r')
    menifest_fn = 'META-INF/MANIFEST.MF'
    menifest = war_zip.read(menifest_fn)

    for l in menifest.splitlines():
        ls = l.strip().decode('utf-8')
        for key in retDict:
            if ls.startswith('Implementation-{0}'.format(key.title())):
                retDict[key] = ls.split(':')[1].strip()
                break
        if ls.startswith('Build-Branch:'):
            branch = ls.split(':')[1].strip()
            if '/' in branch:
                branch = branch.split('/')[1]

            retDict['branch'] = branch

    menifest_info = war_zip.getinfo(menifest_fn)
    retDict['buildDate'] = str(datetime.datetime(*menifest_info.date_time))


    return retDict

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument("--show-latest-commit", help="Gets latest commit from githbub", action='store_true')
    parser.add_argument("-target", help="Target directory", default='/opt/gluu/jetty/*/webapps')
    parser.add_argument("--json", help="Print output in json format", action='store_true')
    args = parser.parse_args()

    target = os.path.join(args.target, '*.war')

    if args.json:
        output = []

    for war_fn in glob.glob(target):
        info = get_war_info(war_fn)
        service = os.path.basename(war_fn).split('.')[0]
        
        if not args.json:
            for si in ('title', 'version', 'buildDate', 'build'):
                print("{0}: {1}".format(si.title(), info[si]))
        
        if args.show_latest_commit and (service in repos):
            latest_commit = get_latest_commit(service, info['branch'])
            if not 'ERROR:' in latest_commit and info['build'] != latest_commit:
                compare_build = 'diff: https://github.com/GluuFederation/{0}/compare/{1}...{2}'.format(repos[service], info['build'], latest_commit) 
            else:
                compare_build = ''
            if not args.json:
                print("Latest Commit:", latest_commit, compare_build)
            else:
                info["Latest Commit"] = latest_commit

        if args.json:
            info["file"] = war_fn
            output.append(info)
        else:
            print()
            

    if args.json:
        print(json.dumps(output))
