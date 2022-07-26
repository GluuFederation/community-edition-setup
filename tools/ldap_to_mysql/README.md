# Gluu OpenDJ to MySQL Migration

This script migrates data from OpenDJ to MySQL. Please note that this tool is experimental.
Note!: Test this script on non-production server.

# Prerequisites

* Insptall `python3-ldap` package.

  On RHEL-8/CentOS-8-AppStream: `yum install python3-ldap`
  
  On Ubuntun: `apt install python3-ldap`

* Install and Configure MySQL
  Install MySQL that upports a native JSON data type (See https://dev.mysql.com/doc/refman/5.7/en/json.html).
  Create a database, namely `gluudb`, and create
  a user, namely `gluu`. User should have all previleges on created database. Sample MySQL commands 
  (If you installed MySQL on a seperate server, modify commands accordingly):

  ```
  > CREATE DATABASE gluudb;
  > CREATE USER 'gluu'@'localhost' IDENTIFIED BY 'TopSecret';
  > GRANT ALL PRIVILEGES ON gluudb.* TO 'gluu'@'localhost';
  ```

# Download CE Setup and Migration Script

  - You need latest version of CE Setup:
    ```
    wget https://github.com/GluuFederation/community-edition-setup/archive/refs/heads/version_4.4.1.zip
    ```
  
  - Extract:
    ```
    unizp version_4.4.1.zip
    ```
  
  - Copy migration script to Setup root directory:
    ```
    cd community-edition-setup-version_4.4.1
    cp ./tools/ldap_to_mysql/ldap2mysql.py ./
    ```
  
  - Execute script:
    ```
    python3 ldap2mysql.py -rdbm-user=gluu -rdbm-password=TopSecret -rdbm-db=gluudb -rdbm-host=localhost
    ```
