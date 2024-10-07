#!/usr/bin/python3
import warnings
warnings.filterwarnings("ignore")
import os
import sys
import json
import argparse

from collections import OrderedDict
try:
    from ldap.schema.models import AttributeType, ObjectClass
except:
    print("This tool requires python3-ldap package. Please install and re-run")
    sys.exit()


result = input("This is experimental script. Continue anyway? [y/N]")
if not result.lower().startswith('y'):
    sys.exit()


parser = argparse.ArgumentParser(description="Gluu CE LDAP to RDBM migrator script")
parser.add_argument('-rdbm-type', choices=['mysql', 'pgsql'], help="Enables using remote RDBM server", default='mysql')
parser.add_argument('-rdbm-user', help="RDBM username",  required = True)
parser.add_argument('-rdbm-password', help="RDBM password",  required = True)
parser.add_argument('-rdbm-port', help="RDBM port", type=int)
parser.add_argument('-rdbm-db', help="RDBM database",  required = True)
parser.add_argument('-rdbm-host', help="RDBM host",  required = True)
argsp = parser.parse_args()
rdbm_config_params = ('rdbm_type', 'rdbm_user', 'rdbm_password', 'rdbm_host', 'rdbm_db', 'rdbm_host', 'rdbm_port')
argsp_dict = { a: getattr(argsp, a) for a in rdbm_config_params }
sys.argv = [sys.argv[0]]


from setup_app.utils.arg_parser import arg_parser
argsp = arg_parser()

from setup_app import paths
from setup_app import static

from setup_app.utils import base
base.argsp = argsp

from setup_app.config import Config
from setup_app.utils.collect_properties import CollectProperties
from setup_app.utils.setup_utils import SetupUtils
from setup_app.utils.properties_utils import PropertiesUtils
from setup_app.installers.gluu import GluuInstaller
from setup_app.utils.ldif_utils import myLdifParser
from setup_app.installers.opendj import OpenDjInstaller
from setup_app.installers.rdbm import RDBMInstaller
from setup_app.pylib.ldif4.ldif import LDIFWriter
from ldap3.utils import dn as dnutils

Config.init(paths.INSTALL_DIR)
Config.determine_version()
SetupUtils.init()
gluuInstaller = GluuInstaller()
gluuInstaller.initialize()
collectProperties = CollectProperties()
collectProperties.collect()
Config.installed_instance = True
openDjInstaller = OpenDjInstaller()
rdbmInstaller = RDBMInstaller()
propertiesUtils = PropertiesUtils()

parser = myLdifParser("/opt/opendj/config/schema/77-customAttributes.ldif")
parser.parse()

from collections import OrderedDict
from ldap.schema.models import AttributeType, ObjectClass

gluuInstaller.createLdapPw()

out_dir = os.path.join(Config.outputFolder, 'ldap_dump')
if not os.path.exists(out_dir):
    os.mkdir(out_dir)
static_ldif_fn = os.path.join(out_dir, 'statistic_data.ldif')
current_ldif_fn = os.path.join(out_dir, 'current_data.ldif')

def dump_ldap(ldap_filter, output_fn):
    print(f"Dumping data from LDAP with filter {ldap_filter} to {output_fn}. This may take a while...")


    gluuInstaller.run(' '.join([
                            '/opt/opendj/bin/ldapsearch',
                            '-X', '-Z', '-D',
                            '"{}"'.format(Config.ldap_binddn),
                            '-j',
                            Config.ldapPassFn,
                            '-h',
                            Config.ldap_hostname,
                            '-p',
                            '1636',
                            '-b',
                            'o=gluu',
                            ldap_filter,
                            '>',
                            output_fn]), shell=True)

print("Dumping data from LDAP Server")

dump_ldap("'(objectClass=jansStatEntry)'", static_ldif_fn)
dump_ldap("'(&(objectClass=*)(!(objectClass=jansStatEntry)))'", current_ldif_fn)

gluuInstaller.deleteLdapPw()

print("Migrating Statistic Data")

stat_ldif_parser = myLdifParser(static_ldif_fn)
stat_ldif_parser.parse()

migrated_static_ldif_fn = static_ldif_fn + '.migrated'
with open(migrated_static_ldif_fn, 'wb') as w:
    stat_ldif_writer = LDIFWriter(w, cols=10000)

    for dn, entry in stat_ldif_parser.entries:
        rd_list = dnutils.parse_dn(dn)
        stat_ou = rd_list[1][1]
        if not rd_list[0][1].endswith(f'_{stat_ou}'):
            jans_id = rd_list[0][1] + '_' + stat_ou
            rd_list[0] = (rd_list[0][0], jans_id, rd_list[0][2])
            entry['jansId'] = [jans_id]
            dn = ','.join(['='.join([dne[0], dne[1]])  for dne in rd_list])

        stat_ldif_writer.unparse(dn, entry)

static_ldif_fn = migrated_static_ldif_fn

print("Preparing custom schema from attributes")
schema = {'attributeTypes':[], 'objectClasses':[]}

for attr_s in parser.entries[0][1].get('attributeTypes', []):
    attr_obj = AttributeType(attr_s)
    attr_dict = {a:getattr(attr_obj, a) for a in ('desc', 'equality', 'names', 'oid', 'substr', 'syntax', 'x_origin') }
    attr_dict['x_origin'] = attr_dict['x_origin'][0]

    schema['attributeTypes'].append(attr_dict)

for obcls_s in parser.entries[0][1]['objectClasses']:
    obcls_obj = ObjectClass(obcls_s)
    obcls_dict = {a:getattr(obcls_obj, a) for a in ('may', 'names', 'oid', 'x_origin') }
    obcls_dict['x_origin'] = obcls_dict['x_origin'][0]
    schema['objectClasses'].append(obcls_dict)


current_attributes = gluuInstaller.dbUtils.search("ou=attributes,o=gluu", fetchmany=True)

with open(os.path.join(Config.install_dir, 'schema/custom_schema.json')) as f:
    gluu_custom_schma = json.load(f)


for custom_ocl in gluu_custom_schma['objectClasses']:
    if custom_ocl['names'][0] == 'gluuCustomPerson':
        gluu_custom_ocl_names = custom_ocl['may'][:]
        break


for cur_ocl in schema['objectClasses']:
    if cur_ocl['names'][0] == 'gluuCustomPerson':
        for cur_anme in cur_ocl['may']:
            if cur_anme not in gluu_custom_ocl_names:
                for cur_atr in schema['attributeTypes']:
                    if cur_atr['names'][0] == cur_anme:
                        for dn, entry in current_attributes:
                            if entry['gluuAttributeName'] == cur_anme:
                                    if entry.get('oxMultivaluedAttribute'):
                                        cur_atr['multivalued'] = True

                        gluu_custom_schma['attributeTypes'].append(cur_atr)
                        custom_ocl['may'].append(cur_anme)



current_custom_schema_fn = os.path.join(Config.install_dir, 'schema/custom_schema.json')

with open(current_custom_schema_fn, 'w') as w:
    json.dump(gluu_custom_schma, w, indent=2)


schmema_files = [
    os.path.join(Config.install_dir, 'schema/gluu_schema.json'),
    current_custom_schema_fn
    ]

rdbmInstaller.prepare()
rdbmInstaller.dbUtils.read_gluu_schema()

for a in rdbm_config_params:
    if argsp_dict[a]:
        setattr(Config, a, argsp_dict[a])

Config.ldap_install = static.InstallTypes.NONE
Config.rdbm_install = static.InstallTypes.REMOTE

Config.mappingLocations = { group: 'rdbm' for group in Config.couchbaseBucketDict }

rdbmInstaller.dbUtils.bind(force=True)
propertiesUtils.set_persistence_type()

print("Creating RDBM tables")
rdbmInstaller.create_tables(schmema_files)

print("Re-formatting data. This will take a while...")
cur_data_parser = myLdifParser(current_ldif_fn)
cur_data_parser.parse()

current_ldif_tmp_fn = current_ldif_fn + '~'

with open(current_ldif_tmp_fn, 'wb') as w:
    ldif_writer = LDIFWriter(w, cols=10000)

    for dn, entry in cur_data_parser.entries:
        if 'gluuAttribute' in entry['objectClass']:
            entry['description'][0] = entry['description'][0][:768]
        ldif_writer.unparse(dn, entry)

os.rename(current_ldif_tmp_fn, current_ldif_fn)


for ldif_fn in (current_ldif_fn, static_ldif_fn):
    print("Importing data into RDBM from {}. This may take a while ...".format(ldif_fn))
    rdbmInstaller.dbUtils.import_ldif([ldif_fn])

print("Creating indexes...")
rdbmInstaller.create_indexes()

print("Writing Gluu config properties")
rdbmInstaller.rdbmProperties()
gluuInstaller.renderTemplateInOut(
                    Config.gluu_properties_fn,
                    os.path.join(Config.install_dir, 'templates'),
                    Config.configFolder
                )

print("Please disable opendj and restart container")
