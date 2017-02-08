# Schema Management Suite

The Schema Management Suite provides utilities for managing the custom  LDAP Schema definitions defined by Gluu and used in the Gluu Server for data storage.

The `manager.py` acts as the command excution interface to perform various activities like generating schema files, parsing schema files etc.,

## How to update Schema of Gluu Server?

1. Edit the file `gluu_schema.json` and add the custom attribute under `attributeTypes` list and the custom classes under `objectClasses` list.
2. Run `python manage.py autogenerate` - this will update the schema files in the folder `static/openldap` and `static/opendj` with new schema definitions.

## Available Commands

### Generating the Schema files for OpenLDAP and OpenDJ

```
python manage.py autogenerate
```

### Generating a specific type of schema file

```
python manage.py generate --type openldap --filename gluu_schema.json
(or)
python manage.py generate --type opendj --filename <json filename>
```

### Generate JSON from Schema files

```
python manage.py makejson --filename <path to schema file>
```

### Generate Markdown Docs for the Schema

```
python manage.py makedocs
```

### Getting Help

```
python manage.py --help
```
