import os
import re
import sys
import time
import sqlalchemy
import shutil

from string import Template
from collections import OrderedDict

from setup_app import paths
from setup_app.static import AppType, InstallOption
from setup_app.config import Config
from setup_app.utils import base
from setup_app.utils import ldif_utils
from setup_app.static import InstallTypes
from setup_app.installers.base import BaseInstaller
from setup_app.utils.setup_utils import SetupUtils
from setup_app.utils.package_utils import packageUtils


class RDBMInstaller(BaseInstaller, SetupUtils):

    def __init__(self):
        setattr(base.current_app, self.__class__.__name__, self)
        self.needdb = False # we will connect later
        self.service_name = 'rdbm-server'
        self.app_type = AppType.APPLICATION
        self.install_type = InstallOption.OPTONAL
        self.install_var = 'rdbm_install'
        self.register_progess()
        self.common_lib_dir = os.path.join(Config.jetty_base, 'common/libs/spanner')


    @property
    def qchar(self):
        return '`' if Config.rdbm_type in ('mysql', 'spanner') else '"'

    def prepare(self):
        self.schema_files = []
        self.gluu_attributes = []

        json_schema_files = ['gluu_schema.json', 'custom_schema.json']

        if Config.installSaml:
            edu_person_fn = ldif_utils.schema2json(
                        os.path.join(Config.staticFolder, 'opendj/96-eduperson.ldif'),
                        os.path.join(Config.install_dir, 'schema')
                        )
            json_schema_files.append(edu_person_fn)

        for schema_fn in json_schema_files:
            schema_full_path = os.path.join(Config.install_dir, 'schema', schema_fn)
            self.schema_files.append(schema_full_path)
            schema_ = base.readJsonFile(schema_full_path)
            self.gluu_attributes += schema_.get('attributeTypes', [])


    @property
    def output_dir(self):
        return os.path.join(Config.outputFolder, Config.rdbm_type)

    def install(self):
        if not os.path.exists(self.output_dir):
            self.createDirs(self.output_dir)

        self.prepare()
        if Config.rdbm_type == 'spanner':
            self.extract_libs()
        self.local_install()
        if Config.rdbm_install_type == InstallTypes.REMOTE and base.argsp.reset_rdbm_db:
            self.reset_rdbm_db()
        self.create_tables(self.schema_files)
        self.create_subtables()
        self.import_ldif()
        self.create_indexes()
        self.rdbmProperties()

    def reset_rdbm_db(self):
        self.logIt("Resetting DB {}".format(Config.rdbm_db))
        self.dbUtils.metadata.reflect(self.dbUtils.engine)
        self.dbUtils.metadata.drop_all(self.dbUtils.engine)
        self.dbUtils.session.commit()
        self.dbUtils.metadata.clear()

    def get_col_def(self, attrname, sql_tbl_name):
        not_null = ' NOT NULL' if sql_tbl_name=='gluuPerson' and attrname=='inum' else ''
        data_type = self.get_sql_col_type(attrname, sql_tbl_name)
        col_def = '{0}{1}{0} {2}{3}'.format(self.qchar, attrname, data_type, not_null)
        if Config.rdbm_type == 'mysql' and self.dbUtils.mariadb and data_type == 'JSON':
            col_def += ' check (json_valid({0}{1}{0}))'.format(self.qchar, attrname)
        return col_def

    def local_install(self):
        if not Config.rdbm_password:
            Config.rdbm_password = self.getPW()
        if not Config.rdbm_user:
            Config.rdbm_user = 'gluu'

        if Config.rdbm_install_type == InstallTypes.LOCAL:
            base.argsp.n = True
            packageUtils.check_and_install_packages()

            if Config.rdbm_type == 'mysql':
                if base.os_type == 'suse':
                    self.restart('mariadb')
                    self.enable('mariadb')
                    Config.start_oxauth_after = 'mariadb.service'
                elif base.clone_type == 'rpm':
                    self.restart('mysqld')
                    self.enable('mysqld')
            if Config.rdbm_type == 'mysql':
                result, conn = self.dbUtils.mysqlconnection(log=False)
                if not result:
                    time.sleep(5)
                    sql_cmd_list = [
                        "CREATE DATABASE {}".format(Config.rdbm_db),
                        "CREATE USER '{}'@'localhost' IDENTIFIED BY '{}'".format(Config.rdbm_user, Config.rdbm_password),
                        "GRANT ALL PRIVILEGES ON {}.* TO '{}'@'localhost'".format(Config.rdbm_db, Config.rdbm_user),
                        ]
                    for cmd in sql_cmd_list:
                        self.run("echo \"{}\" | mysql".format(cmd), shell=True)

            elif Config.rdbm_type == 'pgsql':
                if base.clone_type == 'rpm':
                    self.fix_pgsql_unit_file()
                    self.run(['postgresql-setup', 'initdb'])
                elif base.clone_type == 'deb':
                    self.run([paths.cmd_chmod, '640', '/etc/ssl/private/ssl-cert-snakeoil.key'])

                self.enable('postgresql')
                self.restart('postgresql')

                self.createUser(Config.rdbm_user, os.path.join('/home', Config.rdbm_user))
                cmd_create_db = '''su - postgres -c "psql -U postgres -d postgres -c \\"CREATE DATABASE {};\\""'''.format(Config.rdbm_db)
                cmd_create_user = '''su - postgres -c "psql -U postgres -d postgres -c \\"CREATE USER {} WITH PASSWORD '{}';\\""'''.format(Config.rdbm_user, Config.rdbm_password)
                cmd_grant_previlages = '''su - postgres -c "psql -U postgres -d postgres -c \\"GRANT ALL PRIVILEGES ON DATABASE {} TO {};\\""'''.format(Config.rdbm_db, Config.rdbm_user)
                cmd_alter_db = f'''su - postgres -c "psql -U postgres -d postgres -c \\"ALTER DATABASE {Config.rdbm_db} OWNER TO {Config.rdbm_user};\\""'''

                for cmd in (cmd_create_db, cmd_create_user, cmd_grant_previlages, cmd_alter_db):
                    self.run(cmd, shell=True)

                if base.clone_type == 'rpm':
                    hba_file_path_query = self.run('''su - postgres -c "psql -U postgres -d postgres -t -c \\"SHOW hba_file;\\""''', shell=True)
                    if hba_file_path_query and hba_file_path_query.strip():
                        self.stop('postgresql')
                        hba_file_path = hba_file_path_query.strip()
                        hba_file_content = self.readFile(hba_file_path)
                        hba_file_content = 'host\t{0}\t{1}\t127.0.0.1/32\tmd5\nhost\t{0}\t{1}\t::1/128\tmd5\n'.format(Config.rdbm_db, Config.rdbm_user) + hba_file_content
                        self.writeFile(hba_file_path, hba_file_content)
                        self.start('postgresql')

        self.dbUtils.bind(force=True)

    def get_sql_col_type(self, attrname, table=None):

        if attrname in self.dbUtils.sql_data_types:
            type_ = self.dbUtils.sql_data_types.get(f'{table}:{attrname}',{}).get(Config.rdbm_type) or self.dbUtils.sql_data_types.get(f'{table}:{attrname}',{}).get('mysql') or self.dbUtils.sql_data_types[attrname].get(Config.rdbm_type) or self.dbUtils.sql_data_types[attrname]['mysql']
            if table in type_.get('tables', {}):
                type_ = type_['tables'][table]
            if 'size' in type_:
                data_type = '{}({})'.format(type_['type'], type_['size'])
            else:
                data_type = type_['type']
        else:
            attr_syntax = self.dbUtils.get_attr_syntax(attrname)
            type_ = self.dbUtils.ldap_sql_data_type_mapping[attr_syntax].get(Config.rdbm_type) or self.dbUtils.ldap_sql_data_type_mapping[attr_syntax]['mysql']

            char_type = 'STRING' if Config.rdbm_type == 'spanner' else 'VARCHAR'

            if type_['type'] in char_type:
                if type_['size'] <= 127:
                    data_type = '{}({})'.format(char_type, type_['size'])
                elif type_['size'] <= 255:
                    data_type = 'TINYTEXT' if Config.rdbm_type == 'mysql' else 'TEXT'
                else:
                    data_type = 'TEXT'
            else:
                data_type = type_['type']

        if data_type == 'TEXT' and Config.rdbm_type == 'spanner':
            data_type = 'STRING(MAX)'

        return data_type

    def get_sql_tables(self, schema_files):

        tables_dict = OrderedDict()
        all_schema = {}
        tables_dict['__allattribs__'] = {}
        
        for schema_fn in schema_files:
            schema = base.readJsonFile(schema_fn)
            for obj in schema['objectClasses']:
                if 'sql' in obj and Config.installSaml and obj['names'][0] == 'gluuPerson':
                    obj['sql']['includeObjectClass'].append('eduPerson')
                all_schema[obj['names'][0]] = obj
            for attr in schema['attributeTypes']:
                tables_dict['__allattribs__'][attr['names'][0]] = attr

        subtable_attrs = {}
        for stbl in self.dbUtils.sub_tables.get(Config.rdbm_type):
            subtable_attrs[stbl] = [ scol[0] for scol in self.dbUtils.sub_tables[Config.rdbm_type][stbl] ]

        for obj_name in all_schema:
            obj = all_schema[obj_name]

            if obj.get('sql', {}).get('ignore'):
                continue

            sql_tbl_name = obj['names'][0]
            tables_dict[sql_tbl_name] = []

            attr_list = obj['may']
            if 'sql' in obj:
                attr_list += obj['sql'].get('include',[])
                if 'includeObjectClass' in obj['sql']:
                    for incobjcls in obj['sql']['includeObjectClass']:
                        attr_list += all_schema[incobjcls]['may']

            for s in obj['sup']:
                if s == 'top':
                    continue
                attr_list += all_schema[s]['may']

            cols_ =[]
            for attrname in attr_list:
                if attrname in cols_:
                    continue

                if attrname in subtable_attrs.get(sql_tbl_name, []):
                    continue

                cols_.append(attrname)
                data_type = self.get_sql_col_type(attrname, sql_tbl_name)
                tables_dict[sql_tbl_name].append((attrname, data_type))

        return tables_dict

    def quote_column(self, col):
        if not col.startswith(self.qchar):
            col = self.qchar + col + self.qchar
        return col

    def create_table(self, sql_tbl_name, sql_tbl_cols_list):

        sql_tbl_cols = [f'{self.quote_column(col)} {dtype}' for col, dtype in sql_tbl_cols_list]

        if not self.dbUtils.table_exists(sql_tbl_name):
            doc_id_type = self.get_sql_col_type('doc_id', sql_tbl_name)
            uniq_col = ''
            if Config.rdbm_type == 'pgsql':
                if sql_tbl_name == 'gluuPerson':
                    uniq_col = ', UNIQUE (uid)'
                sql_cmd = 'CREATE TABLE "{}" (doc_id {} NOT NULL UNIQUE, "objectClass" VARCHAR(48), "dn" VARCHAR(128), {}, PRIMARY KEY (doc_id){});'.format(sql_tbl_name, doc_id_type, ', '.join(sql_tbl_cols), uniq_col)
            elif Config.rdbm_type == 'spanner':
                sql_cmd = 'CREATE TABLE `{}` (`doc_id` {} NOT NULL, `objectClass` STRING(48), dn STRING(128), {}) PRIMARY KEY (`doc_id`);'.format(sql_tbl_name, doc_id_type, ', '.join(sql_tbl_cols))
            else:
                if sql_tbl_name == 'gluuPerson':
                    uniq_col = ', UNIQUE(uid)'
                sql_cmd = 'CREATE TABLE `{}` (`doc_id` {} NOT NULL UNIQUE, `objectClass` VARCHAR(48), dn VARCHAR(128), {}, PRIMARY KEY (`doc_id`){});'.format(sql_tbl_name, doc_id_type, ', '.join(sql_tbl_cols), uniq_col)

            self.dbUtils.exec_rdbm_query(sql_cmd)
            self.appendLine(sql_cmd, os.path.join(self.output_dir, 'gluu_tables.sql'), backup=False)


    def get_columns_of_table(self, table_name):
        tbl_cls = self.dbUtils.Base.classes[table_name]
        cols = [ col_cls.name for col_cls in tbl_cls.__table__.columns ]
        return cols

    def add_missing_attributes(self, all_attribs):

        for attrname in all_attribs:
            attr = all_attribs[attrname]
            if attr.get('sql', {}).get('add_table'):
                tbl_name = attr['sql']['add_table']
                self.add_attribute_to_table(tbl_name, attr)


    def add_attribute_to_table(self, tbl_name, attrib):
        col_def = self.get_col_def(attrib['names'][0], tbl_name)
        self.add_col_to_table(tbl_name, col_def)

    def add_col_to_table(self, tbl_name, col_def):
        self.logIt("Adding column {} to {}".format(col_def, tbl_name))

        column_add = 'COLUMN ' if Config.rdbm_type == 'spanner' else ''
        alter_table_sql_cmd = 'ALTER TABLE %s{}%s ADD %s{};' % (self.qchar, self.qchar, column_add)
        sql_cmd = alter_table_sql_cmd.format(tbl_name, col_def)

        if Config.rdbm_type == 'spanner':
            req = self.dbUtils.exec_rdbm_query(sql_cmd.strip(';'))
        else:
            self.dbUtils.exec_rdbm_query(sql_cmd)

        self.appendLine(sql_cmd, os.path.join(self.output_dir, 'gluu_tables.sql'), backup=False)

    def create_tables(self, schema_files):
        self.logIt("Creating tables for {}".format(schema_files))
        tables_dict = self.get_sql_tables(schema_files)
        for tbl_name in tables_dict:
            if tbl_name.startswith('__') and tbl_name.endswith('__'):
                continue
            self.create_table(tbl_name, tables_dict[tbl_name])


    def create_subtables(self):

        for subtable in self.dbUtils.sub_tables.get(Config.rdbm_type, {}):
            for sattr, sdt in self.dbUtils.sub_tables[Config.rdbm_type][subtable]:
                subtbl_name = '{0}_{1}'.format(subtable, sattr)
                if not self.dbUtils.table_exists(subtbl_name):
                    subtable_columns = []
                    sql_cmd = 'CREATE TABLE `{0}_{1}` (`doc_id` STRING(64) NOT NULL, `dict_doc_id` STRING(64), `{1}` {2}) PRIMARY KEY (`doc_id`, `dict_doc_id`), INTERLEAVE IN PARENT `{0}` ON DELETE CASCADE'.format(subtable, sattr, sdt)
                    self.dbUtils.exec_rdbm_query(sql_cmd)
                    sql_cmd_index = 'CREATE INDEX `{0}_{1}Idx` ON `{0}_{1}` (`{1}`)'.format(subtable, sattr)
                    self.dbUtils.exec_rdbm_query(sql_cmd_index)
                else:
                    subtable_cols = self.get_columns_of_table(subtbl_name)
                    if sdt not in subtable_cols:
                        col_def = '{0}{1}{0} {2}'.format(self.qchar, sattr, sdt)
                        self.add_col_to_table(subtbl_name, col_def)


    def get_index_name(self, attrname):
        return re.sub(r'[^0-9a-zA-Z\s]+','_', attrname)


    def old_mysql_json_index(self, tbl_name, col_name):
        mem_index_tmp = "ALTER TABLE {0}.{1} ADD COLUMN `{3}_mem_idx_{2}` CHAR(128) AS ({3}->'$.v[{2}]')"
        raw_index_tmp = "ALTER TABLE {0}.{1} ADD INDEX `{3}_mem_idx_{2}` (`{3}_mem_idx_{2}`)"
        for i in range(4):
            self.dbUtils.exec_rdbm_query(mem_index_tmp.format(Config.rdbm_db, tbl_name, i, col_name))
            self.dbUtils.exec_rdbm_query(raw_index_tmp.format(Config.rdbm_db, tbl_name, i, col_name))

    def create_indexes(self):

        indexes = []

        sql_indexes_fn = os.path.join(Config.static_rdbm_dir, Config.rdbm_type + '_index.json')
        sql_indexes = base.readJsonFile(sql_indexes_fn)


        # read opendj indexes and add multivalued attributes to JSON indexing
        opendj_index = base.readJsonFile(base.current_app.OpenDjInstaller.openDjIndexJson)
        opendj_index_list = [ atribute['attribute'] for atribute in opendj_index ]

        for attribute in self.gluu_attributes:
            if attribute.get('multivalued'):
                for attr_name in attribute['names']:
                    if attr_name in opendj_index_list and attr_name not in sql_indexes['__common__']['fields']:
                        sql_indexes['__common__']['fields'].append(attr_name)

        if Config.rdbm_type == 'spanner':
            tables = self.dbUtils.spanner_client.get_tables()
            for tblCls in tables:
                tbl_fields = sql_indexes.get(tblCls, {}).get('fields', []) +  sql_indexes['__common__']['fields']

                tbl_data = self.dbUtils.spanner_client.exec_sql('SELECT * FROM {} LIMIT 1'.format(tblCls))

                for attr in tbl_data.get('fields', []):
                    if attr['name'] == 'doc_id':
                        continue
                    attr_name = attr['name']
                    ind_name = self.get_index_name(attr['name'])
                    data_type = attr['type']

                    if data_type == 'ARRAY':
                        # How to index for ARRAY types in spanner?
                        pass

                    elif attr_name in tbl_fields:
                        sql_cmd = 'CREATE INDEX `{1}_{0}Idx` ON `{1}` (`{2}`)'.format(
                                    ind_name,
                                    tblCls,
                                    attr_name
                                )
                        self.dbUtils.spanner_client.exec_sql(sql_cmd)

                for i, custom_index in enumerate(sql_indexes.get(tblCls, {}).get('custom', [])):
                    sql_cmd = 'CREATE INDEX `{0}_CustomIdx{1}` ON {0} ({2})'.format(
                                    tblCls,
                                    i+1, 
                                    custom_index
                                )
                    self.dbUtils.spanner_client.exec_sql(sql_cmd)

                if tblCls == 'gluuPerson':
                    uniq_index_cmd = 'CREATE UNIQUE NULL_FILTERED INDEX gluuPerson_unique_uuid ON gluuPerson (uid)'
                    self.dbUtils.spanner_client.exec_sql(uniq_index_cmd)

        else:
            for tblCls in self.dbUtils.Base.classes.keys():
                tblObj = self.dbUtils.Base.classes[tblCls]()
                tbl_fields = sql_indexes.get(tblCls, {}).get('fields', []) + sql_indexes['__common__']['fields']

                for attr in tblObj.__table__.columns:
                    if attr.name == 'doc_id':
                        continue
                    ind_name = self.get_index_name(attr.name)
                    data_type = self.get_sql_col_type(attr, tblCls)
                    data_type = data_type.replace('VARCHAR', 'CHAR')

                    if isinstance(attr.type, self.dbUtils.json_dialects_instance):

                        if attr.name in tbl_fields:
                            if Config.rdbm_type == 'mysql' and self.dbUtils.mysql_version < (5, 7, 38):
                                self.old_mysql_json_index(tblCls, attr.name)
                            else:
                                for i, ind_str in enumerate(sql_indexes['__common__']['JSON']):
                                    tmp_str = Template(ind_str)
                                    if Config.rdbm_type == 'mysql':
                                        sql_cmd = 'ALTER TABLE {0}.{1} ADD INDEX `{2}_json_{3}`(({4}));'.format(
                                                Config.rdbm_db,
                                                tblCls,
                                                ind_name,
                                                i+1,
                                                tmp_str.safe_substitute({'field':attr.name})
                                                )
                                        self.dbUtils.exec_rdbm_query(sql_cmd)
                                    elif Config.rdbm_type == 'pgsql':
                                        sql_cmd ='CREATE INDEX ON "{}" {};'.format(
                                                tblCls,
                                                tmp_str.safe_substitute({'field':attr.name})
                                                )
                                        self.dbUtils.exec_rdbm_query(sql_cmd)


                    elif attr.name in tbl_fields:
                        if Config.rdbm_type == 'mysql':
                            idx_key_length = '(768)' if str(attr.type) == 'TEXT' else ''
                            sql_cmd = 'ALTER TABLE {0}.{1} ADD INDEX `{1}_{2}` (`{3}`{4});'.format(
                                        Config.rdbm_db,
                                        tblCls,
                                        ind_name,
                                        attr.name,
                                        idx_key_length
                                    )
                            self.dbUtils.exec_rdbm_query(sql_cmd)
                        elif Config.rdbm_type == 'pgsql':
                            sql_cmd = 'CREATE INDEX ON "{}" ("{}");'.format(
                                        tblCls,
                                        attr.name
                                    )
                            self.dbUtils.exec_rdbm_query(sql_cmd)

                for i, custom_index in enumerate(sql_indexes.get(tblCls, {}).get('custom', [])):
                    if Config.rdbm_type == 'mysql':
                        sql_cmd = 'ALTER TABLE {0}.{1} ADD INDEX `{2}` ({3});'.format(
                                        Config.rdbm_db,
                                        tblCls,
                                        '{}_CustomIdx{}'.format(tblCls, i+1),
                                        custom_index
                                    )
                        self.dbUtils.exec_rdbm_query(sql_cmd)
                    elif Config.rdbm_type == 'pgsql':
                        sql_cmd = 'CREATE INDEX ON "{}" {};'.format(
                                    tblCls,
                                    custom_index
                                    )
                        self.dbUtils.exec_rdbm_query(sql_cmd)

    def import_ldif(self):
        ldif_files = []

        if Config.mappingLocations['default'] == 'rdbm':
            ldif_files += Config.couchbaseBucketDict['default']['ldif']

        ldap_mappings = self.getMappingType('rdbm')

        for group in ldap_mappings:
            ldif_files +=  Config.couchbaseBucketDict[group]['ldif']

        if Config.ldif_metric in ldif_files:
            ldif_files.remove(Config.ldif_metric)

        if Config.ldif_site in ldif_files:
            ldif_files.remove(Config.ldif_site)

        Config.pbar.progress(self.service_name, "Importing base ldif files to {}".format(Config.rdbm_type), False)
        if Config.ldif_base not in ldif_files:
            if Config.rdbm_type == 'mysql':
                force = BackendTypes.MYSQL
            elif Config.rdbm_type == 'pgsql':
                force = BackendTypes.PGSQL
            elif Config.rdbm_type == 'spanner':
                force = BackendTypes.SPANNER
            self.dbUtils.import_ldif([Config.ldif_base], force=force)


        self.dbUtils.import_ldif(ldif_files)


    def rdbmProperties(self):
        if Config.rdbm_type in ('pgsql', 'mysql'):
            Config.rdbm_password_enc = self.obscure(Config.rdbm_password)
            src_temp_fn = os.path.join(Config.templateFolder, 'gluu-{}.properties'.format(Config.rdbm_type))
            targtet_fn = os.path.join(Config.configFolder, Config.gluuRDBMProperties)
            rendered_tmp = self.render_template(src_temp_fn)
            self.writeFile(targtet_fn, rendered_tmp)

        elif Config.rdbm_type == 'spanner':
            if Config.spanner_emulator_host:
                Config.templateRenderingDict['spanner_creds'] = 'connection.emulator-host={}:9010'.format(Config.spanner_emulator_host)
            else:
                auth_cred_target_fn = os.path.join(Config.configFolder, 'google_application_credentials.json')
                shutil.copy(Config.google_application_credentials, auth_cred_target_fn)
                Config.templateRenderingDict['spanner_creds'] = 'connection.credentials-file={}'.format(auth_cred_target_fn)

            self.renderTemplateInOut(Config.gluuSpannerProperties, Config.templateFolder, Config.configFolder)

    def fix_pgsql_unit_file(self):
        self.logIt("Fixing postgresql unit file")
        pg_unit_file_fn = self.get_unit_file_location('postgresql')
        unit_file_dict = self.parse_unit_file(pg_unit_file_fn)

        for i, entry in  enumerate(unit_file_dict['Service']):
            if entry[0] == 'TimeoutSec':
                unit_file_dict['Service'][i][1] = '300'
                break
        else:
            unit_file_dict['Service'].append(['TimeoutSec', '300'])

        new_unit_file_list = []
        for section in unit_file_dict:
            new_unit_file_list.append(f'[{section}]')
            for i, entry in  enumerate(unit_file_dict[section]):
                new_unit_file_list.append('='.join(entry))
            new_unit_file_list.append('')

        unit_file_content = '\n'.join(new_unit_file_list)
        self.writeFile(pg_unit_file_fn, unit_file_content, backup=False)

        self.run([paths.cmd_systemctl, 'daemon-reload'])

    def extract_libs(self):
        lib_archive = os.path.join(Config.distGluuFolder, 'gluu-orm-spanner-libs-distribution.zip')
        self.logIt("Extracting {}".format(lib_archive))
        if not os.path.exists(self.common_lib_dir):
            self.createDirs(self.common_lib_dir)
        shutil.unpack_archive(lib_archive, self.common_lib_dir)
        self.chown(os.path.join(Config.jetty_base, 'common'), Config.jetty_user, Config.gluu_group, True)

    def create_folders(self):
        self.createDirs(Config.static_rdbm_dir)

    def installed(self):
        return os.path.exists(Config.gluuRDBMProperties) or os.path.exists(Config.gluuSpannerProperties)

