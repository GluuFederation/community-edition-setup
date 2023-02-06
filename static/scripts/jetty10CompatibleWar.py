#!/usr/bin/python3

import os
import sys
import shutil
import argparse
import tempfile
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser(description="This script makes Jetty 9.x war file compatible with Jetty 10.0.x or 11.0.x")
parser.add_argument('-in-file', help="Download server", required=True)
parser.add_argument('-out-file', help="Download server", required=True)
parser.add_argument('-jetty-version', help="Jetty version", default="10.0.x")
argsp = parser.parse_args()


def war_for_jetty10(war_file, out_file, jetty_version):

    with tempfile.TemporaryDirectory() as tmp_dir:

        unpack_dir = os.path.join(tmp_dir, 'unpacked')

        print("Unpacking {} to {}".format(war_file, unpack_dir))
        try:
            shutil.unpack_archive(war_file, unpack_dir, format='zip')
        except Exception as e:
            print("Error unpacking file {}: {}".format(war_file, e))
            return

        jetty_env_fn = os.path.join(unpack_dir, 'WEB-INF/jetty-env.xml')

        if not os.path.exists(jetty_env_fn):
            print("Can't find {} exting.".format(jetty_env_fn))
            return

        print("Modifying {}".format(jetty_env_fn))

        tree = ET.parse(jetty_env_fn)
        root = tree.getroot()

        for new in root.findall("New"):
            for arg in new.findall("Arg"):
                for ref in arg.findall("Ref"):
                    if ref.attrib.get('id') == 'webAppCtx':
                        ref.set('refid', 'webAppCtx')
                        ref.attrib.pop('id')

        jetty_web_fn = os.path.join(unpack_dir, 'WEB-INF/jetty-web.xml')
        if os.path.exists(jetty_web_fn):
            os.remove(jetty_web_fn)

        jetty_version_string = '_'.join(jetty_version.split('.')[:2])

        xml_header = '<!DOCTYPE Configure PUBLIC "-//Jetty//Configure//EN" "https://www.eclipse.org/jetty/configure_{}.dtd">\n\n'.format(jetty_version_string)
        with open(jetty_env_fn, 'wb') as f:
            f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(xml_header.encode())
            f.write(ET.tostring(root,method='xml'))

        tmp_war_fn = os.path.join(tmp_dir, '{}.war'.format(os.urandom(6).hex()))
        print("Packing {}".format(tmp_war_fn))
        shutil.make_archive(tmp_war_fn, format='zip', root_dir=unpack_dir)
        print("Renaming pack to", out_file)
        shutil.move(tmp_war_fn+'.zip', out_file)


if __name__ == '__main__':
    war_for_jetty10(argsp.in_file, argsp.out_file, argsp.jetty_version)
