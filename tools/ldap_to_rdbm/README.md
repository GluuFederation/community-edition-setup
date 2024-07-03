# Gluu OpenDJ to MySQL Migration

This script migrates data from OpenDJ to MySQL. Please note that this tool is experimental.
Note!: Test this script on non-production server.

# Prerequisites

* Insptall `python3-ldap` package.

  On RHEL-8/CentOS-8-AppStream: `yum install python3-ldap`
  
  On Ubuntun: `apt install python3-ldap`

* If you are migration to MySQL

  Install MySQL that upports a native JSON data type (See https://dev.mysql.com/doc/refman/5.7/en/json.html).
  MySQL Server shipped with >=Ubuntu 20 and >=RHEL 8/CentOS-8-Appstream is fine.
  Create a database, namely `gluudb`, and create
  a user, namely `gluu`. User should have all previleges on created database. Sample MySQL commands 
  (If you installed MySQL on a seperate server, modify commands accordingly):

  ```
  CREATE DATABASE gluudb;
  CREATE USER 'gluu'@'localhost' IDENTIFIED BY 'TopSecret';
  GRANT ALL PRIVILEGES ON gluudb.* TO 'gluu'@'localhost';
  ```

* If you are migration to PostgreSQL

  Install postgresql server on your system (version should be at least 14.0) or any host that can be reachable from gluu host.
  Add the following line at the beginning of file `pg_hba.conf` (You can learn location of this file by executing command `sudo su - postgres -c 'psql -U postgres -d postgres -t -c "SHOW hba_file;"'`):

  `host    gluudb    gluu    0.0.0.0/0    md5`

  To crate database, user and adjust previleges, connect to postgresql server by command
  `sudo su - postgres -c 'psql'`

  Execute the following sql commands:

  ```
  CREATE DATABASE gluudb;
  CREATE USER gluu WITH PASSWORD 'TopSecret';
  GRANT ALL PRIVILEGES ON DATABASE gluudb TO gluu;
  ALTER DATABASE gluudb OWNER TO gluu;
  ```

# Migration

  - Download migration script:
    ```
    wget https://raw.githubusercontent.com/GluuFederation/community-edition-setup/tools/ldap_to_rdbm/ldap2rdbm.py -O /install/community-edition-setup/ldap2rdbm.py
    ```

  - Execute script (for MySQL):
    ```
    cd /install/community-edition-setup/
    python3 ldap2rdbm.py -rdbm-type="mysql" -rdbm-user="gluu" -rdbm-password="TopSecret" -rdbm-db="gluudb" -rdbm-host="localhost"
    ```

    - Execute script (for PostgreSQL):
    ```
    cd /install/community-edition-setup/
    python3 ldap2rdbm.py -rdbm-type="pgsql" -rdbm-user="gluu" -rdbm-password="TopSecret" -rdbm-db="gluudb" -rdbm-host="localhost" -rdbm-port="5432"

    ```

    Replace `localhost` with hostname of RDBM server

