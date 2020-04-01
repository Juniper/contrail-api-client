from __future__ import print_function
#
# Copyright (c) 2016 Juniper Networks, Inc. All rights reserved.
#

from builtins import object
import os
import re
import sys
import json

import type_model

try:
    import pyaml
    yaml_parser = "pyaml"
except ImportError:
    import yaml
    yaml_parser = "PyYAML"
except ImportError:
    yaml_parser = None


class ContrailJsonSchemaGenerator(object):
    def __init__(self, parser, type_map, identifiers, metadata):
        self._parser = parser
        self._type_map = type_map
        self._top_level_map = {
            'SubnetType': self._type_map['SubnetType']
        }
        self._identifier_map = identifiers
        self._metadata_map = metadata
        self._type_count = {}
        # map which will hold the schema for the types which will be generated below
        self._json_type_map = {}
        self._objectsList = []

    def yaml_dump(self, data, indent=2, safe=True):
        if yaml_parser == 'pyaml':
            return pyaml.dumps(data, indent=indent, safe=safe)
        elif yaml_parser == 'PyYAML':
            if safe:
                return yaml.safe_dump(data, indent=indent, default_flow_style=False)
            else:
                return yaml.dump(data, indent=indent, default_flow_style=False)
        else:
            print("please install pyaml or PyYAML")
            sys.exit(1)

    # For mapping the js data type given the ctype or jtype
    def _getJSDataType(self, type):
        if (type.lower() == "string" or type.lower() == 'xsd:string'):
            return "string"
        elif (type.lower() == "integer" or type.lower() == "int" or type.lower() == "long" or type.lower() == "xsd:integer"):
            return "integer"
        elif (type.lower() == "number"):
            return "number"
        elif (type.lower() == "boolean" or type.lower() == "bool" or type.lower() == "xsd:boolean"):
            return "boolean"
        elif (type.lower().startswith("list")):
            return "array"
        else:
            return "object"

    def _convertHyphensToUnderscores(self, str):
        return str.replace("-", "_")

    def _GenerateJavascriptSchema(self, ident, base, filename):
        file = self._parser.makeFile(filename)
        propertiesJSON = {}

        identProperties = ident.getProperties()
#        First loop through the direct properties and generate the schema
        propertiesOrder = []
        required = []
        for prop in identProperties:
            propertyID = self._convertHyphensToUnderscores(
                prop._name)
            propMemberInfo = prop._memberinfo
            xelementType = prop._xelement.type
            propType = self._getJSDataType(xelementType)
            presence = prop.getPresence()
            simple_type = prop.getElement().getSimpleType()
            propSchema = {}
            if propType == "object":
                if self._json_type_map.get(xelementType):
                    subJson = {
                        "$ref": "types.json#/definitions/" + xelementType}
                else:
                    subJson = {"type": propType}
            else:
                subJson = {"type": propType}

            if prop.isMap():
                subJson["collectionType"] = "map"
                subJson["mapKey"] = prop.getMapKeyName()
                subJson["wrapper"] = prop.isMapUsingWrapper()
            elif prop.isList():
                subJson["collectionType"] = "list"
                subJson["wrapper"] = prop.isListUsingWrapper()

            default = prop.getDefault()
            if default:
                if propType == "boolean":
                    subJson["default"] = default == "true"
                elif propType == "number":
                    subJson["default"] = int(default)
                else:
                    subJson["default"] = default

            if presence == 'required':
                required.append(propertyID)

            if simple_type:
                subJson = self.generateRestrictions(simple_type, subJson)

            subJson["presence"] = presence
            subJson["operations"] = prop.getOperations()
            try:
                subJson["description"] = prop.getDescription()
            except ValueError as detail:
                pass

            if prop._parent == "all":
                base["schema"]["properties"][propertyID] = subJson
            else:
                propertiesJSON[propertyID] = subJson

#       Now look for the links and generate respective schema, exclude the children (has relationship) objects
        references = {}
        for link_info in ident.getLinksInfo():
            presence = link_info[0].getPresence()
            operation = link_info[0].getOperations()
            try:
                description = link_info[0].getDescription()
            except:
                description = ""

            link_to = ident.getLinkTo(link_info)
            link_type = link_info[0]._xelement.type
            if not ident.isLinkRef(link_info):
                continue

            reference = self._convertHyphensToUnderscores(link_to.getName())
            subJson = {
                "operations": operation,
                "presence": presence,
                "description": description}

            if self._json_type_map.get(link_type):
                subJson["$ref"] = "types.json#/definitions/" + link_type

            if "derived" in link_info[2]:
                subJson["derived"] = True

            if link_info[0]._idl_info[1] == "all":
                base["references"][reference] = subJson
            else:
                references[reference] = subJson

        parents = {}
        parents_obj = ident.getParents()

        if parents_obj:
            for parent in parents_obj:
                presence = parent[1].getPresence()
                operation = parent[1].getOperations()
                try:
                    description = parent[1].getDescription()
                except:
                    description = ""

                subJson = {
                    "operations": operation,
                    "presence": presence,
                    "description": description
                }
                link_type = parent[1]._xelement.type
                if ident.isDerived(parent[0]):
                    subJson["derived"] = True
                if self._json_type_map.get(link_type):
                    subJson["$ref"] = "types.json#/definitions/" + link_type
                parents[parent[0].getJsonName()] = subJson

        id = self._convertHyphensToUnderscores(ident._name)
#       Then look for back links and create back_ref schema if required
        jsonSchema = {"id": id, "prefix": "/",
                      "plural": id + "s",
                      "extends": ["base"],
                      "api_style": "contrail",
                      "parents": parents,
                      "references": references,
                      "schema": {"type": "object",
                                 "required": required,
                                 "properties": propertiesJSON}}
        file.write(self.yaml_dump(jsonSchema))

    def _getSubJS(self, type, dataMember):
        ret = {}
        if type in ("string", "xsd:string"):
            ret["type"] = "string"
        elif type in ("xsd:integer", "xsd:unsignedInt", "xsd:unsignedLong"):
            ret["type"] = "integer"
        elif (type == "xsd:boolean"):
            ret["type"] = "boolean"
        elif (type.lower().startswith("list")):
            ret["type"] = "array"
            if(dataMember.sequenceType == "std::string"):
                ret["items"] = {"type": "string"}
            elif(self._type_map.get(dataMember.sequenceType)):
                ret["items"] = self._GenerateTypeMap(
                    self._type_map.get(dataMember.sequenceType))
            else:
                ret["items"] = {"type": "string"}
        elif type in ("xsd:dateTime"):
            ret["type"] = "string"
            ret["format"] = "date-time"
        elif type in ("xsd:time"):
            ret["type"] = "string"
        else:
            self._GenerateTypeMap(self._type_map.get(type))
            ret = {"$ref": "types.json#/definitions/" + type}
        return ret

    def _GenerateTypeMap(self, ctype):
        self._json_type_map[ctype.getName()] = {
            "type": "object", "properties": {}}
        typeDataMembers = ctype._data_members
        for dataMember in typeDataMembers:
            if dataMember.xsd_object.maxOccurs == 1:
                subJson = self._getSubJS(
                    dataMember.xsd_object.type, dataMember)
            else:
                subJson = {
                    "type": "array",
                    "items": self._getSubJS(dataMember.xsd_object.type, dataMember)
                }
            simple_type = dataMember.xsd_object.simpleType
            if simple_type:
                subJson = self.generateRestrictions(simple_type, subJson)

            if(dataMember.xsd_object.description):
                subJson['description'] = dataMember.xsd_object.description
            if(dataMember.xsd_object.required):
                subJson['presence'] = dataMember.xsd_object.required

            for k, v in type_model.KEYWORDS.items():
                if v == dataMember.membername:
                    dataMember.membername = k
            self._json_type_map[ctype.getName(
            )]["properties"][dataMember.membername] = subJson
        return self._json_type_map[ctype.getName()]

    def generateRestrictions(self, simple_type, subJson):
        restrictions = None
        # TODO(nati) fix why invalid data given here.
        if simple_type == 1:
            return

        if(self._parser.SimpleTypeDict.get(simple_type)):
            restriction_object = self._parser.SimpleTypeDict[simple_type]
            restrictions = restriction_object.values
            restrictionAttrs = restriction_object.getRestrictionAttrs()
            if (restrictions and len(restrictions) > 0):
                if(type(restrictions[0]) is dict):
                    # If it is a dict we assume it to be min max type
                    subJson["minimum"] = restrictions[0]["minimum"]
                    subJson["maximum"] = restrictions[1]["maximum"]
                else:
                    # else they are enum
                    if(subJson["type"] == "array"):
                        if(subJson.get("items")):
                            subJson["items"]["enum"] = restrictions
                        else:
                            subJson["items"] = {}
                            subJson["items"]["enum"] = restrictions
                    else:
                        subJson["enum"] = restrictions
        self._json_type_map[simple_type] = subJson
        return {
            "$ref": "types.json#/definitions/" + simple_type}

    def Generate(self, dirname):
        if not yaml_parser:
            print("please install pyaml or PyYAML")
            sys.exit(1)

        if not os.path.exists(dirname):
            os.makedirs(dirname)
        elif not os.path.isdir(dirname):
            print("-o option must specify directory")
            sys.exit(1)

        for ctype in list(self._type_map.values()):
            self._GenerateTypeMap(ctype)

        base = {"id": "base", "prefix": "/",
                "plural": "base",
                "type": "abstract",
                "parents": {},
                "references": {},
                "schema": {"type": "object",
                           "required": [],
                           "properties": {
                                          "uuid": {
                                            "presence": "true",
                                            "description": "UUID of the object, system automatically allocates one if not provided",
                                            "type": "string"
                                          },
                                          "name": {
                                            "presence": "true",
                                            "description": "Name of the object, defaults to 'default-<resource-type>'",
                                            "type": "string",
                                            "nullable": "false"
                                          },
                                          "parent_uuid": {
                                            "presence": "optional",
                                            "description": "UUID of the parent object",
                                            "type": "string"
                                          },
                                          "parent_type": {
                                            "presence": "optional",
                                            "description": "Parent resource type",
                                            "type": "string"
                                          },
                                          "fq_name": {
                                            "presence": "true",
                                            "description": "FQ Name of the object",
                                            "type": "array",
                                            "items": {
                                              "type": "string"
                                            }
                                          },
                                          "configuration_version": {
                                            "operations": "CRUD",
                                            "presence": "optional",
                                            "description": "Configuration Version for the object.",
                                            "type": "integer",
                                            "sql": "bigint"
                                          },
                                          "href": {
                                            "operations": "R",
                                            "presence": "service",
                                            "description": "Instance reference URL",
                                            "type": "string"
                                          }
                                       } }}

        for ident in list(self._identifier_map.values()):
            self._objectsList.append(ident._name)
            filename = os.path.join(dirname, ident._name + "-schema.yml")
            self._GenerateJavascriptSchema(ident, base, filename)

        # Generate the file containing the list of all identfiers/objects

        # Generate the base schema
        objFileName = os.path.join(dirname, "base.yml")
        objFile = self._parser.makeFile(objFileName)
        objFile.write(self.yaml_dump(base))

        typeFileName = os.path.join(dirname, "types.yml")
        typeFile = self._parser.makeFile(typeFileName)
        typeJson = {"definitions": self._json_type_map}
        typeFile.write(self.yaml_dump(typeJson))

        print("Done!")
        print("Schemas generated under directory: " + dirname)
