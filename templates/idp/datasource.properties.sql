idp.attribute.resolver.datasource.driverClass=com.%(rdbm_type)s.jdbc.Driver
idp.attribute.resolver.datasource.jdbcUrl=jdbc:%(rdbm_type)s://%(rdbm_host)s:%(rdbm_port)s/%(rdbm_db)s
idp.attribute.resolver.datasource.user=%(rdbm_user)s
idp.attribute.resolver.datasource.password=%(rdbm_password)s
idp.attribute.resolver.datasource.serverTimezone=%(server_time_zone)s
idp.attribute.resolver.sql.searchFilter=select * from `gluuPerson` where ((LOWER(uid) = "$requestContext.principalName") OR (LOWER(mail) = "$requestContext.principalName")) AND (objectClass = "gluuPerson")
