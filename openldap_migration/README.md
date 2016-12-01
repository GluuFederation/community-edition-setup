## Pre-requisites
- Ubuntu 14.04
- OpenLDAP Binary as a deb package - Preferably Symas Openldap Gold 

### Procedure for replacing OpenDJ with OpenLDAP in 2.4.4.2
1. Install the Openldap debian package  `dpkg -i <openldap.deb>`
2. Generate the certificates using OpenSSL

    ```bash
    cd /etc/certs
    openssl genrsa -des3 -out openldap.key 2048
    openssl rsa -in openldap.key -out openldap.key.insecure
    mv openldap.key.insecure openldap.key
    openssl req -new -key openldap.key -out openldap.csr
    openssl x509 -req -days 365 -in openldap.csr -signkey openldap.key -out openldap.crt
    ```

3. Clone the community-edition-setup for the scripts

    ```bash
    cd ~
    git clone -b openldap-migration --single-branch https://github.com/GluuFederation/community-edition-setup.git
    cd community-edition-setup/openldap_migration
    ```

4. Stop OpenDJ and Setup OpenLDAP

    ```bash
    service opendj stop
    python setup_openldap.py
    ```

5. Start the OpenLDAP server

    ```
    service solserver start
    ```

6. Update the `ox-ldap.properties` bindDN. Open `/opt/tomcat/conf/ox-ldap.properties` using a text editor like Vim and change
   the bind DN to

    ```
    bindDN: cn=directory manager,o=gluu
    ```

7. Connect to the LDAP server from a client like jXplorer using the server IP, port 1636, bindDN `cn=directory manager,o=gluu`, via SSL + User + Password.
    * Navigate to the entry o=gluu > ou=appliances > \<inum of your Org>. Edit the attribute `oxIDPAuthentication`. Find bindDN and change it to `cn=directory manager,o=gluu`.
    * Navigate to the entry o=gluu > ou=appliances > \<inum of your Org> > ou=configuration > ou=oxTrust. Edit the attribute `oxTrustConfApplication`. Find the value for `idpBindDn` and update it to `cn=directory manager,o=gluu`

8. Patch oxAuth

    ```
    service tomcat stop
    cd /opt/tomcat/webapps/
    rm -rf oxauth
    mv oxauth.war oxauth.war.bk01
    wget http://ox.gluu.org/maven/org/xdi/oxauth-server/2.4.4.sp2_openldap/oxauth-server-2.4.4.sp2_openldap.war -O oxauth.war
    service tomcat start
    ```

Now the system has been migrated from OpenDJ to OpenLDAP.


### Procedure for migrating an existing Gluu Server 2.4.4
1. Export the ldap data using the export\_opendj script

  ```bash
  service gluu-server-2.4.4 login
  wget https://raw.githubusercontent.com/GluuFederation/community-edition-setup/master/openldap_migration/export_opendj.py
  python export_opendj.py
  exit
  ```
  
  This creates a folder called backup\_24 that will contain all the LDAP data in the ldif file format.
2. Install the Gluu Server 3.0.0 alpha version.

  ```bash
  echo "deb https://repo.gluu.org/ubuntu/ trusty-devel main" > /etc/apt/sources.list.d/gluu-repo.list
  curl https://repo.gluu.org/ubuntu/gluu-apt.key | apt-key add -
  apt-get update
  apt-get install gluu-server-3.0.0
  ```
  
3. Stop the old server and copy the files to the new one. Assuming you have `openldap.deb` in the `/root` directory

  ```bash
  service gluu-server-2.4.4 stop
  cp -r /opt/gluu-server-2.4.4/root/backup_24/ /opt/gluu-server-3.0.0/root/
  cp openldap.deb /opt/gluu-server-3.0.0/root/
  ```
  
4. Start the new server and login and do some bootstrapping.

  ```bash
  service gluu-server-3.0.0 start
  service gluu-server-3.0.0 login
  dpkg -i openldap.deb
  cd /install
  rm -rf community-edition-setup
  git clone https://github.com/GluuFederation/community-edition-setup.git
  cd community-edition-setup
  cp /root/backup_24/setup.properties /install/community-edition-setup/
  sed -i 's/ldap_type\ \=\ \"opendj\"/ldap_type\ \=\ \"openldap\"/' setup.py
  ./setup.py
  ```
  
5. Input the values and wait for the installation to finish.
6. Import the old OpenDJ data into OpenLDAP

  ```bash
  wget -c https://raw.githubusercontent.com/GluuFederation/community-edition-setup/master/openldap_migration/import_openldap.py
  wget -c https://raw.githubusercontent.com/GluuFederation/community-edition-setup/master/ldif.py
  apt-get update
  apt-get install python-pip
  pip install jsonmerge
  python import_openldap.py backup_24
  ```
  
7. Start the Openldap server

  ```bash
  service solserver start
  ```
  
8. Verify connection using username `cn=directory manager,o=gluu` and your ldap password from the old installation on the port 1636.
