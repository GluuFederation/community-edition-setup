idp.attribute.resolver.datasource.driverClass=%(rdbm_driver_origin)s.%(rdbm_driver)s.jdbc.Driver
idp.attribute.resolver.datasource.jdbcUrl=jdbc:%(rdbm_driver)s://%(rdbm_host)s:%(rdbm_port)s/%(rdbm_db)s
idp.attribute.resolver.datasource.user=%(rdbm_user)s
idp.attribute.resolver.datasource.password=%(rdbm_password)s
idp.attribute.resolver.datasource.serverTimezone=%(server_time_zone)s
idp.attribute.resolver.sql.searchFilter=select * from `gluuPerson` where ((LOWER(uid) = "$requestContext.principalName") OR (LOWER(mail) = "$requestContext.principalName")) AND (objectClass = "gluuPerson")
