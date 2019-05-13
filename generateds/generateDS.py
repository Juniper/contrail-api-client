#!/usr/bin/env python2
"""
Synopsis:
    Generate Python classes from XML Schema definition.
    Input is read from in_xsd_file or, if "-" (dash) arg, from stdin.
    Output is written to files named in "-o" and "-s" options.
Usage:
    python generateDS.py [ options ] <xsd_file>
    python generateDS.py [ options ] -
Options:
    -h, --help               Display this help information.
    -o <outfilename>         Output file name for data representation classes
    -s <subclassfilename>    Output file name for subclasses
    -p <prefix>              Prefix string to be pre-pended to the class names
    -f                       Force creation of output files.  Do not ask.
    -a <namespaceabbrev>     Namespace abbreviation, e.g. "xsd:".
                             Default = 'xs:'.
    -b <behaviorfilename>    Input file name for behaviors added to subclasses
    -m                       Generate properties for member variables
    --subclass-suffix="XXX"  Append XXX to the generated subclass names.
                             Default="Sub".
    --root-element="XXX"     Assume XXX is root element of instance docs.
                             Default is first element defined in schema.
                             Also see section "Recognizing the top level
                             element" in the documentation.
    --super="XXX"            Super module name in subclass module. Default="???"
    --validator-bodies=path  Path to a directory containing files that provide
                             bodies (implementations) of validator methods.
    --use-old-getter-setter  Name getters and setters getVar() and setVar(),
                             instead of get_var() and set_var().
    --user-methods= <module>,
    -u <module>              Optional module containing user methods.  See
                             section "User Methods" in the documentation.
    --no-dates               Do not include the current date in the generated
                             files. This is useful if you want to minimize
                             the amount of (no-operation) changes to the
                             generated python code.
    --no-versions            Do not include the current version in the generated
                             files. This is useful if you want to minimize
                             the amount of (no-operation) changes to the
                             generated python code.
    --no-process-includes    Do not process included XML Schema files.  By
                             default, generateDS.py will insert content
                             from files referenced by <include ... />
                             elements into the XML Schema to be processed.
    --silence                Normally, the code generated with generateDS
                             echoes the information being parsed. To prevent
                             the echo from occurring, use the --silence switch.
    --namespacedef='xmlns:abc="http://www.abc.com"'
                             Namespace definition to be passed in as the
                             value for the namespacedef_ parameter of
                             the export_xml() method by the generated
                             parse() and parseString() functions.
                             Default=''.
    --external-encoding=<encoding>
                             Encode output written by the generated export
                             methods using this encoding.  Default, if omitted,
                             is the value returned by sys.getdefaultencoding().
                             Example: --external-encoding='utf-8'.
    --member-specs=list|dict
                             Generate member (type) specifications in each
                             class: a dictionary of instances of class
                             MemberSpec_ containing member name, type,
                             and array or not.  Allowed values are
                             "list" or "dict".  Default: do not generate.
    -q, --no-questions       Do not ask questios, for example,
                             force overwrite.
    --session=mysession.session
                             Load and use options from session file. You can
                             create session file in generateds_gui.py.  Or,
                             copy and edit sample.session from the
                             distribution.
    --version                Print version and exit.

"""


## LICENSE

## Copyright (c) 2003 Dave Kuhlman

## Permission is hereby granted, free of charge, to any person obtaining
## a copy of this software and associated documentation files (the
## "Software"), to deal in the Software without restriction, including
## without limitation the rights to use, copy, modify, merge, publish,
## distribute, sublicense, and/or sell copies of the Software, and to
## permit persons to whom the Software is furnished to do so, subject to
## the following conditions:

## The above copyright notice and this permission notice shall be
## included in all copies or substantial portions of the Software.

## THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
## EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
## MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
## IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
## CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
## TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
## SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


import sys
import os.path
import time
import getopt
import urllib2
import imp
from xml.sax import handler, make_parser
import xml.sax.xmlreader
import logging
import keyword
import StringIO
import textwrap
from cctype import TypeGenerator
from ccmap import IFMapGenerator
from ccsvc import ServiceGenerator

# Default logger configuration
## logging.basicConfig(level=logging.DEBUG,
##                     format='%(asctime)s %(levelname)s %(message)s')

## import warnings
## warnings.warn('importing IPShellEmbed', UserWarning)
## from IPython.Shell import IPShellEmbed
## args = ''
## ipshell = IPShellEmbed(args,
##     banner = 'Dropping into IPython',
##     exit_msg = 'Leaving Interpreter, back to program.')

# Then use the following line where and when you want to drop into the
# IPython shell:
#    ipshell('<some message> -- Entering ipshell.\\nHit Ctrl-D to exit')


#
# Global variables etc.
#

#
# Do not modify the following VERSION comments.
# Used by updateversion.py.
##VERSION##
VERSION = '2.7c'
##VERSION##

class XsdParserGenerator(object):
    def __init__(self):
        self.Version = VERSION
        self.GenerateProperties = 0
        self.UseOldGetterSetter = 0
        self.MemberSpecs = None
        self.DelayedElements = []
        self.DelayedElements_subclass = []
        self.AlreadyGenerated = []
        self.AlreadyGenerated_subclass = []
        self.PostponedExtensions = []
        self.ElementsForSubclasses = []
        self.ElementDict = {}
        self.Force = False
        self.NoQuestions = False
        self.Dirpath = []
        self.ExternalEncoding = sys.getdefaultencoding()
        self.genCategory = None
        self.genLang = None
        self.LangGenr = None
        self.NamespacesDict = {}
        self.Targetnamespace = ""

        self.NameTable = {
            'type': 'type_',
            'float': 'float_',
            'build': 'build_',
            }
        extras = ['self']
        for kw in keyword.kwlist + extras:
            self.NameTable[kw] = '%sxx' % kw


        self.SubclassSuffix = 'Sub'
        self.RootElement = None
        self.AttributeGroups = {}
        self.ElementGroups = {}
        self.SubstitutionGroups = {}
        #
        # SubstitutionGroups can also include simple types that are
        #   not (defined) elements.  Keep a list of these simple types.
        #   These are simple types defined at top level.
        self.SimpleElementDict = {}
        self.SimpleTypeDict = {}
        self.ValidatorBodiesBasePath = None
        self.UserMethodsPath = None
        self.UserMethodsModule = None
        self.XsdNameSpace = ''
        self.CurrentNamespacePrefix = 'xs:'
        self.AnyTypeIdentifier = '__ANY__'

    def args_parse(self):
        self.outputText = True
        self.args = sys.argv[1:]
        try:
            options, self.args = getopt.getopt(self.args, 'l:g:hfyo:s:p:a:b:mu:q',
                ['help', 'subclass-suffix=',
                'root-element=', 'super=',
                'validator-bodies=', 'use-old-getter-setter',
                'user-methods=', 'no-process-includes', 'silence',
                'namespacedef=', 'external-encoding=',
                'member-specs=', 'no-dates', 'no-versions',
                'no-questions', 'session=', 'generator-category=',
                'generated-language=', 'version',
                ])
        except getopt.GetoptError, exp:
            usage()
        self.prefix = ''
        self.outFilename = None
        self.subclassFilename = None
        self.behaviorFilename = None
        self.nameSpace = 'xs:'
        superModule = '???'
        self.processIncludes = 1
        self.namespacedef = ''
        self.ExternalEncoding = sys.getdefaultencoding()
        self.NoDates = False
        self.NoVersion = False
        self.NoQuestions = False
        showVersion = False
        self.xschemaFileName = None
        for option in options:
            if option[0] == '--session':
                sessionFilename = option[1]
                from libgenerateDS.gui import generateds_gui_session
                from xml.etree import ElementTree as etree
                doc = etree.parse(sessionFilename)
                rootNode = doc.getroot()
                sessionObj = generateds_gui_session.sessionType()
                sessionObj.build(rootNode)
                if sessionObj.get_input_schema():
                    self.xschemaFileName = sessionObj.get_input_schema()
                if sessionObj.get_output_superclass():
                    self.outFilename = sessionObj.get_output_superclass()
                if sessionObj.get_output_subclass():
                    self.subclassFilename = sessionObj.get_output_subclass()
                if sessionObj.get_force():
                    self.Force = True
                if sessionObj.get_prefix():
                    self.prefix = sessionObj.get_prefix()
                if sessionObj.get_empty_namespace_prefix():
                    self.nameSpace = ''
                elif sessionObj.get_namespace_prefix():
                    self.nameSpace = sessionObj.get_namespace_prefix()
                if sessionObj.get_behavior_filename():
                    self.behaviorFilename = sessionObj.get_behavior_filename()
                if sessionObj.get_properties():
                    self.GenerateProperties = True
                if sessionObj.get_subclass_suffix():
                    SubclassSuffix = sessionObj.get_subclass_suffix()
                if sessionObj.get_root_element():
                    self.RootElement = sessionObj.get_root_element()
                if sessionObj.get_superclass_module():
                    superModule = sessionObj.get_superclass_module()
                if sessionObj.get_old_getters_setters():
                    self.UseOldGetterSetter = 1
                if sessionObj.get_validator_bodies():
                    ValidatorBodiesBasePath = sessionObj.get_validator_bodies()
                    if not os.path.isdir(ValidatorBodiesBasePath):
                        err_msg('*** Option validator-bodies must specify an existing path.\n')
                        sys.exit(1)
                if sessionObj.get_user_methods():
                    UserMethodsPath = sessionObj.get_user_methods()
                if sessionObj.get_no_dates():
                    self.NoDates = True
                if sessionObj.get_no_versions():
                    self.NoVersion = True
                if sessionObj.get_no_process_includes():
                    self.processIncludes = 0
                if sessionObj.get_silence():
                    self.outputText = False
                if sessionObj.get_namespace_defs():
                    self.namespacedef = sessionObj.get_naspace_defs()
                if sessionObj.get_external_encoding():
                    self.ExternalEncoding = sessionObj.get_external_encoding()
                if sessionObj.get_member_specs() in ('list', 'dict'):
                    MemberSpecs = sessionObj.get_member_specs()
                break
        for option in options:
            if option[0] == '-h' or option[0] == '--help':
                usage()
            elif option[0] == '-p':
                self.prefix = option[1]
            elif option[0] == '-o':
                self.outFilename = option[1]
            elif option[0] == '-s':
                self.subclassFilename = option[1]
            elif option[0] == '-f':
                self.Force = 1
            elif option[0] == '-a':
                self.nameSpace = option[1]
            elif option[0] == '-b':
                self.behaviorFilename = option[1]
            elif option[0] == '-m':
                self.GenerateProperties = 1
            elif option[0] == '--no-dates':
                self.NoDates = True
            elif option[0] == '--no-versions':
                self.NoVersion = True
            elif option[0] == '--subclass-suffix':
                SubclassSuffix = option[1]
            elif option[0] == '--root-element':
                self.RootElement = option[1]
            elif option[0] == '--super':
                superModule = option[1]
            elif option[0] == '--validator-bodies':
                ValidatorBodiesBasePath = option[1]
                if not os.path.isdir(ValidatorBodiesBasePath):
                    err_msg('*** Option validator-bodies must specify an existing path.\n')
                    sys.exit(1)
            elif option[0] == '--use-old-getter-setter':
                self.UseOldGetterSetter = 1
            elif option[0] in ('-u', '--user-methods'):
                UserMethodsPath = option[1]
            elif option[0] == '--no-process-includes':
                self.processIncludes = 0
            elif option[0] == "--silence":
                self.outputText = False
            elif option[0] == "--namespacedef":
                self.namespacedef = option[1]
            elif option[0] == '--external-encoding':
                self.ExternalEncoding = option[1]
            elif option[0] in ('-q', '--no-questions'):
                self.NoQuestions = True
            elif option[0] == '--version':
                showVersion = True
            elif option[0] == '--member-specs':
                MemberSpecs = option[1]
                if MemberSpecs not in ('list', 'dict', ):
                    raise RuntimeError('Option --member-specs must be "list" or "dict".')
            elif option[0] in ('-l', '--generated-language'):
                self.genLang = option[1]
                if self.genLang not in ('py', 'c++'):
                    raise RuntimeError('Option --generated-language must be "py" or "c++".')
            elif option[0] in ('-g', '--generator-category'):
                self.genCategory = option[1]
                if self.genCategory not in ('type',
                                            'service',
                                            'ifmap-frontend',
                                            'ifmap-backend',
                                            'device-api',
                                            'java-api',
                                            'golang-api',
                                            'contrail-json-schema',
                                            'json-schema'):
                    raise RuntimeError('Option --generator-category must be "type", service", "ifmap-frontend", "ifmap-backend", "device-api", "java-api", "golang-api", "contrail-json-schema" or "json-schema".')
        if showVersion:
            print 'generateDS.py version %s' % VERSION
            sys.exit(0)

    def countChildren(self, element, count):
        count += len(element.getChildren())
        base = element.getBase()
        if base and base in self.ElementDict:
            parent = self.ElementDict[base]
            count = self.countChildren(parent, count)
        return count

    def getParentName(self, element):
        base = element.getBase()
        rBase = element.getRestrictionBaseObj()
        parentName = None
        parentObj = None
        if base and base in self.ElementDict:
            parentObj = self.ElementDict[base]
            parentName = self.cleanupName(parentObj.getName())
        elif rBase:
            base = element.getRestrictionBase()
            parentObj = self.ElementDict[base]
            parentName = self.cleanupName(parentObj.getName())
        return parentName, parentObj

    def makeFile(self, outFileName, outAppend = False):
        outFile = None
        if ((not self.Force) and os.path.exists(outFileName)
                             and not outAppend):
            if self.NoQuestions:
                sys.stderr.write('File %s exists.  Change output file or use -f (force).\n' % outFileName)
                sys.exit(1)
            else:
                reply = raw_input('File %s exists.  Overwrite? (y/n): ' % outFileName)
                if reply == 'y':
                    outFile = file(outFileName, 'w')
        else:
            if (outAppend):
                outFile = file(outFileName, 'a')
            else:
                outFile = file(outFileName, 'w')
        return outFile

    def mapName(self, oldName):
        newName = oldName
        if self.NameTable:
            if oldName in self.NameTable:
                newName = self.NameTable[oldName]
        return newName

    def cleanupName(self, oldName):
        newName = oldName.replace(':', '_')
        newName = newName.replace('-', '_')
        newName = newName.replace('.', '_')
        return newName

    def make_gs_name(self, oldName):
        if self.UseOldGetterSetter:
            newName = oldName.capitalize()
        else:
            newName = '_%s' % oldName
        return newName

    def is_builtin_simple_type(self, type_val):
        if type_val in self.StringType or \
            type_val == self.TokenType or \
            type_val == self.DateTimeType or \
            type_val == self.TimeType or \
            type_val == self.DateType or \
            type_val in self.IntegerType or \
            type_val == self.DecimalType or \
            type_val == self.PositiveIntegerType or \
            type_val == self.NonPositiveIntegerType or \
            type_val == self.NegativeIntegerType or \
            type_val == self.NonNegativeIntegerType or \
            type_val == self.BooleanType or \
            type_val == self.FloatType or \
            type_val == self.DoubleType or \
            type_val in self.OtherSimpleTypes:
            return True
        else:
            return False

    def set_type_constants(self, nameSpace):
        self.CurrentNamespacePrefix = nameSpace
        self.AttributeGroupType = nameSpace + 'attributeGroup'
        self.AttributeType = nameSpace + 'attribute'
        self.BooleanType = nameSpace + 'boolean'
        self.ChoiceType = nameSpace + 'choice'
        self.SimpleContentType = nameSpace + 'simpleContent'
        self.ComplexContentType = nameSpace + 'complexContent'
        self.ComplexTypeType = nameSpace + 'complexType'
        self.GroupType = nameSpace + 'group'
        self.SimpleTypeType = nameSpace + 'simpleType'
        self.RestrictionType = nameSpace + 'restriction'
        self.WhiteSpaceType = nameSpace + 'whiteSpace'
        self.AnyAttributeType = nameSpace + 'anyAttribute'
        self.DateTimeType = nameSpace + 'dateTime'
        self.TimeType = nameSpace + 'time'
        self.DateType = nameSpace + 'date'
        self.IntegerType = (nameSpace + 'integer',
                 nameSpace + 'unsignedShort',
                 nameSpace + 'unsignedLong',
                 nameSpace + 'unsignedInt',
                 nameSpace + 'unsignedByte',
                 nameSpace + 'byte',
                 nameSpace + 'short',
                 nameSpace + 'long',
                 nameSpace + 'int',
                 )
        self.DecimalType = nameSpace + 'decimal'
        self.PositiveIntegerType = nameSpace + 'positiveInteger'
        self.NegativeIntegerType = nameSpace + 'negativeInteger'
        self.NonPositiveIntegerType = nameSpace + 'nonPositiveInteger'
        self.NonNegativeIntegerType = nameSpace + 'nonNegativeInteger'
        self.DoubleType = nameSpace + 'double'
        self.ElementType = nameSpace + 'element'
        self.ExtensionType = nameSpace + 'extension'
        self.FloatType = nameSpace + 'float'
        self.IDREFSType = nameSpace + 'IDREFS'
        self.IDREFType = nameSpace + 'IDREF'
        self.IDType = nameSpace + 'ID'
        self.IDTypes = (self.IDREFSType, self.IDREFType, self.IDType, )
        self.SchemaType = nameSpace + 'schema'
        self.SequenceType = nameSpace + 'sequence'
        self.StringType = (nameSpace + 'string',
                 nameSpace + 'duration',
                 nameSpace + 'anyURI',
                 nameSpace + 'base64Binary',
                 nameSpace + 'hexBinary',
                 nameSpace + 'normalizedString',
                 nameSpace + 'NMTOKEN',
                 nameSpace + 'ID',
                 nameSpace + 'Name',
                 nameSpace + 'language',
                 )
        self.TokenType = nameSpace + 'token'
        self.NameType = nameSpace + 'Name'
        self.NCNameType = nameSpace + 'NCName'
        self.QNameType = nameSpace + 'QName'
        self.NameTypes = (self.NameType, self.NCNameType, self.QNameType, )
        self.ListType = nameSpace + 'list'
        self.EnumerationType = nameSpace + 'enumeration'
        self.MinInclusiveType = nameSpace + 'minInclusive'
        self.MaxInclusiveType = nameSpace + 'maxInclusive'
        self.UnionType = nameSpace + 'union'
        self.AnnotationType = nameSpace + 'annotation'
        self.DocumentationType = nameSpace + 'documentation'
        self.AnyType = nameSpace + 'any'
        self.OtherSimpleTypes = (
                 nameSpace + 'ENTITIES',
                 nameSpace + 'ENTITY',
                 nameSpace + 'ID',
                 nameSpace + 'IDREF',
                 nameSpace + 'IDREFS',
                 nameSpace + 'NCName',
                 nameSpace + 'NMTOKEN',
                 nameSpace + 'NMTOKENS',
                 nameSpace + 'NOTATION',
                 nameSpace + 'Name',
                 nameSpace + 'QName',
                 nameSpace + 'anyURI',
                 nameSpace + 'base64Binary',
                 nameSpace + 'hexBinary',
                 nameSpace + 'boolean',
                 nameSpace + 'byte',
                 nameSpace + 'date',
                 nameSpace + 'dateTime',
                 nameSpace + 'time',
                 nameSpace + 'decimal',
                 nameSpace + 'double',
                 nameSpace + 'duration',
                 nameSpace + 'float',
                 nameSpace + 'gDay',
                 nameSpace + 'gMonth',
                 nameSpace + 'gMonthDay',
                 nameSpace + 'gYear',
                 nameSpace + 'gYearMonth',
                 nameSpace + 'int',
                 nameSpace + 'integer',
                 nameSpace + 'language',
                 nameSpace + 'long',
                 nameSpace + 'negativeInteger',
                 nameSpace + 'nonNegativeInteger',
                 nameSpace + 'nonPositiveInteger',
                 nameSpace + 'normalizedString',
                 nameSpace + 'positiveInteger',
                 nameSpace + 'short',
                 nameSpace + 'string',
                 nameSpace + 'time',
                 nameSpace + 'token',
                 nameSpace + 'unsignedByte',
                 nameSpace + 'unsignedInt',
                 nameSpace + 'unsignedLong',
                 nameSpace + 'unsignedShort',
                 nameSpace + 'anySimpleType',
             )

    def init_with_args(self):
        self.XsdNameSpace = self.nameSpace
        self.Namespacedef = self.namespacedef
        self.set_type_constants(self.nameSpace)
        if self.behaviorFilename and not self.subclassFilename:
            err_msg(USAGE_TEXT)
            err_msg('\n*** Error.  Option -b requires -s\n')
        if self.xschemaFileName is None:
            if len(self.args) != 1:
                usage()
            else:
                self.xschemaFileName = self.args[0]
        silent = not self.outputText
        self._load_config()

        if self.genCategory == 'type':
            self._Generator = TypeGenerator(self)
        elif self.genCategory == 'service':
            self._Generator = ServiceGenerator(self)
        elif (self.genCategory == 'ifmap-backend' or
              self.genCategory == 'ifmap-frontend' or
              self.genCategory == 'device-api' or
              self.genCategory == 'java-api' or
              self.genCategory == 'golang-api' or
              self.genCategory == 'contrail-json-schema' or
              self.genCategory == 'json-schema'):
            self._Generator = IFMapGenerator(self, self.genCategory)
        self._Generator.setLanguage(self.genLang)

    def _load_config(self):
        try:
            #print '1. updating NameTable'
            import generateds_config
            NameTable.update(generateds_config.NameTable)
            #print '2. updating NameTable'
        except ImportError, exp:
            pass

    def parseAndGenerate(self):
        self.DelayedElements = []
        self.DelayedElements_subclass = []
        self.AlreadyGenerated = []
        self.AlreadyGenerated_subclass = []
        if self.UserMethodsPath:
            path_list = self.UserMethodsPath.split('.')
            mod_name = path_list[-1]
            mod_path = os.sep.join(path_list[:-1])
            module_spec = imp.find_module(mod_name, [mod_path, ])
            self.UserMethodsModule = imp.load_module(mod_name, *module_spec)

        parser = make_parser()
        dh = XschemaHandler(self)
        parser.setContentHandler(dh)
        if self.xschemaFileName == '-':
            content = StringIO.StringIO(sys.stdin.read())
        else:
            with open(self.xschemaFileName, 'r') as f:
                content = StringIO.StringIO(f.read())

        if self.processIncludes:
            import process_includes
            outfile = StringIO.StringIO()
            process_includes.process_include_files(content, outfile,
                inpath=self.xschemaFileName)
            outfile.seek(0)
            content = outfile

        content_clone = StringIO.StringIO(content.getvalue())
        parser.parse(content_clone)
        root = dh.getRoot()
        root.annotate()

        self._Generator.generate(root, content, self.outFilename)

def showLevel(outfile, level):
    for idx in range(level):
        outfile.write('    ')


class XschemaElementBase:
    def __init__(self):
        pass


class SimpleTypeElement(XschemaElementBase):
    def __init__(self, name):
        XschemaElementBase.__init__(self)
        self.name = name
        self.base = None
        self.collapseWhiteSpace = 0
        # Attribute definitions for the current attributeGroup, if there is one.
        self.attributeGroup = None
        # Attribute definitions for the currect element.
        self.attributeDefs = {}
        self.complexType = 0
        # Enumeration values for the current element.
        self.values = list()
        # The other simple types this is a union of.
        self.unionOf = list()
        self.simpleType = 0
        self.listType = 0
        self.documentation = ''
        self.default = None
        self.restrictionAttrs = None
    def setName(self, name): self.name = name
    def getName(self): return self.name
    def setBase(self, base): self.base = base
    def getBase(self): return self.base
    def getDefault(self): return self.default
    def setDefault(self, default): self.default = default
    def setSimpleType(self, simpleType): self.simpleType = simpleType
    def getSimpleType(self): return self.simpleType
    def getAttributeGroups(self): return self.attributeGroups
    def setAttributeGroup(self, attributeGroup): self.attributeGroup = attributeGroup
    def getAttributeGroup(self): return self.attributeGroup
    def setListType(self, listType): self.listType = listType
    def isListType(self): return self.listType
    def setRestrictionAttrs(self, restrictionAttrs): self.restrictionAttrs = restrictionAttrs
    def getRestrictionAttrs(self): return self.restrictionAttrs
    def __str__(self):
        s1 = '<"%s" SimpleTypeElement instance at 0x%x>' % \
            (self.getName(), id(self))
        return s1

    def __repr__(self):
        s1 = '<"%s" SimpleTypeElement instance at 0x%x>' % \
            (self.getName(), id(self))
        return s1

    def resolve_list_type(self, SimpleTypeDict):
        if self.isListType():
            return 1
        elif self.getBase() in SimpleTypeDict:
            base = SimpleTypeDict[self.getBase()]
            return base.resolve_list_type(SimpleTypeDict)
        else:
            return 0


class XschemaElement(XschemaElementBase):
    def __init__(self, parser_generator, attrs):
        XschemaElementBase.__init__(self)
        self._PGenr = parser_generator
        self.cleanName = ''
        self.attrs = dict(attrs)
        name_val = ''
        type_val = ''
        ref_val = ''
        if 'name' in self.attrs:
            name_val = strip_namespace(self.attrs['name'])
        if 'type' in self.attrs:
            if (len(self._PGenr.XsdNameSpace) > 0 and
                self.attrs['type'].startswith(self._PGenr.XsdNameSpace)):
                type_val = self.attrs['type']
            else:
                type_val = strip_namespace(self.attrs['type'])
        if 'ref' in self.attrs:
            ref_val = strip_namespace(self.attrs['ref'])
        if type_val and not name_val:
            name_val = type_val
        if ref_val and not name_val:
            name_val = ref_val
        if ref_val and not type_val:
            type_val = ref_val
        if name_val:
            self.attrs['name'] = name_val
        if type_val:
            self.attrs['type'] = type_val
        if ref_val:
            self.attrs['ref'] = ref_val
        # fix_abstract
        abstract_type = attrs.get('abstract', 'false').lower()
        self.abstract_type = abstract_type in ('1', 'true')
        self.default = self.attrs.get('default')
        self.name = name_val
        self.children = []
        self.optional = False
        self.minOccurs = 1
        self.maxOccurs = 1
        self.complex = 0
        self.complexType = 0
        self.type = 'NoneType'
        self.mixed = 0
        self.base = None
        self.mixedExtensionError = 0
        self.collapseWhiteSpace = 0
        # Attribute definitions for the currect element.
        self.attributeDefs = {}
        # Attribute definitions for the current attributeGroup, if there is one.
        self.attributeGroup = None
        # List of names of attributes for this element.
        # We will add the attribute defintions in each of these groups
        #   to this element in annotate().
        self.attributeGroupNameList = []
        # similar things as above, for groups of elements
        self.elementGroup = None
        self.topLevel = 0
        # Does this element contain an anyAttribute?
        self.anyAttribute = 0
        self.explicit_define = 0
        self.simpleType = None
        # Enumeration values for the current element.
        self.values = list()
        # The parent choice for the current element.
        self.choice = None
        self.listType = 0
        self.simpleBase = []
        self.required = attrs.get('required')
        self.description = attrs.get('description')
        self.documentation = ''
        self.restrictionBase = None
        self.simpleContent = False
        self.extended = False

    def addChild(self, element):
        self.children.append(element)
    def getChildren(self): return self.children
    def getName(self): return self.name
    def getCleanName(self): return self.cleanName
    def getUnmappedCleanName(self): return self.unmappedCleanName
    def setName(self, name): self.name = name
    def getAttrs(self): return self.attrs
    def setAttrs(self, attrs): self.attrs = attrs
    def getMinOccurs(self): return self.minOccurs
    def getMaxOccurs(self): return self.maxOccurs
    def getOptional(self): return self.optional
    def getRawType(self): return self.type
    def setExplicitDefine(self, explicit_define):
        self.explicit_define = explicit_define
    def isExplicitDefine(self): return self.explicit_define
    def isAbstract(self): return self.abstract_type
    def setListType(self, listType): self.listType = listType
    def isListType(self): return self.listType
    def getType(self):
        returnType = self.type
        if self._PGenr.ElementDict.has_key(self.type):
            typeObj = self._PGenr.ElementDict[self.type]
            typeObjType = typeObj.getRawType()
            if self._PGenr.is_builtin_simple_type(typeObjType):
                returnType = typeObjType
        return returnType
    def getSchemaType(self):
        if self.schema_type:
            return self.schema_type
        return None
    def isComplex(self): return self.complex
    def addAttributeDefs(self, attrs): self.attributeDefs.append(attrs)
    def getAttributeDefs(self): return self.attributeDefs
    def isMixed(self): return self.mixed
    def setMixed(self, mixed): self.mixed = mixed
    def setBase(self, base): self.base = base
    def getBase(self): return self.base
    def getMixedExtensionError(self): return self.mixedExtensionError
    def getAttributeGroups(self): return self.attributeGroups
    def addAttribute(self, name, attribute):
        self.attributeGroups[name] = attribute
    def setAttributeGroup(self, attributeGroup): self.attributeGroup = attributeGroup
    def getAttributeGroup(self): return self.attributeGroup
    def setElementGroup(self, elementGroup): self.elementGroup = elementGroup
    def getElementGroup(self): return self.elementGroup
    def setTopLevel(self, topLevel): self.topLevel = topLevel
    def getTopLevel(self): return self.topLevel
    def setAnyAttribute(self, anyAttribute): self.anyAttribute = anyAttribute
    def getAnyAttribute(self): return self.anyAttribute
    def setSimpleType(self, simpleType): self.simpleType = simpleType
    def getSimpleType(self): return self.simpleType
    def setDefault(self, default): self.default = default
    def getDefault(self): return self.default
    def getSimpleBase(self): return self.simpleBase
    def setSimpleBase(self, simpleBase): self.simpleBase = simpleBase
    def addSimpleBase(self, simpleBase): self.simpleBase.append(simpleBase)
    def getRestrictionBase(self): return self.restrictionBase
    def setRestrictionBase(self, base): self.restrictionBase = base
    def getRestrictionBaseObj(self):
        rBaseObj = None
        rBaseName = self.getRestrictionBase()
        if rBaseName and rBaseName in self._PGenr.ElementDict:
            rBaseObj = self._PGenr.ElementDict[rBaseName]
        return rBaseObj
    def setSimpleContent(self, simpleContent):
        self.simpleContent = simpleContent
    def getSimpleContent(self):
        return self.simpleContent
    def getExtended(self): return self.extended
    def setExtended(self, extended): self.extended = extended

    def show(self, outfile, level):
        if self.name == 'Reference':
            showLevel(outfile, level)
            outfile.write('Name: %s  Type: %s  id: %d\n' % (self.name,
                self.getType(), id(self),))
            showLevel(outfile, level)
            outfile.write('  - Complex: %d  MaxOccurs: %d  MinOccurs: %d\n' % \
                (self.complex, self.maxOccurs, self.minOccurs))
            showLevel(outfile, level)
            outfile.write('  - Attrs: %s\n' % self.attrs)
            showLevel(outfile, level)
            #outfile.write('  - AttributeDefs: %s\n' % self.attributeDefs)
            outfile.write('  - AttributeDefs:\n')
            for key, value in self.getAttributeDefs().items():
                showLevel(outfile, level + 1)
                outfile.write('- key: %s  value: %s\n' % (key, value, ))
        for child in self.children:
            child.show(outfile, level + 1)

    def annotate(self):
        # resolve group references within groups
        for grp in self._PGenr.ElementGroups.values():
            expandGroupReferences(grp)
        # Recursively expand group references
        visited = set()
        self.expandGroupReferences_tree(visited)
        self.collect_element_dict()
        self.annotate_find_type()
        self.annotate_tree()
        self.fix_dup_names()
        self.coerce_attr_types()
        self.checkMixedBases()
        self.markExtendedTypes()

    def markExtendedTypes(self):
        base = self.getBase()
        if base and base in self._PGenr.ElementDict:
            parent = self._PGenr.ElementDict[base]
            parent.setExtended(True)
        for child in self.children:
            child.markExtendedTypes()

    def expandGroupReferences_tree(self, visited):
        if self.getName() in visited:
            return
        visited.add(self.getName())
        expandGroupReferences(self)
        for child in self.children:
            child.expandGroupReferences_tree(visited)

    def collect_element_dict(self):
        base = self.getBase()
        if self.getTopLevel() or len(self.getChildren()) > 0 or \
            len(self.getAttributeDefs()) > 0 or base:
            self._PGenr.ElementDict[self.name] = self
        for child in self.children:
            child.collect_element_dict()

    def build_element_dict(self, elements):
        base = self.getBase()
        if self.getTopLevel() or len(self.getChildren()) > 0 or \
            len(self.getAttributeDefs()) > 0 or base:
            if self.name not in elements:
                elements[self.name] = self
        for child in self.children:
            child.build_element_dict(elements)

    def get_element(self, element_name):
        if self.element_dict is None:
            self.element_dict = dict()
            self.build_element_dict(self.element_dict)
        return self.element_dict.get(element_name)

    # If it is a mixed-content element and it is defined as
    #   an extension, then all of its bases (base, base of base, ...)
    #   must be mixed-content.  Mark it as an error, if not.
    def checkMixedBases(self):
        self.rationalizeMixedBases()
        self.collectSimpleBases()
        self.checkMixedBasesChain(self, self.mixed)
        for child in self.children:
            child.checkMixedBases()

    def collectSimpleBases(self):
        if self.base:
            self.addSimpleBase(self.base.encode('utf-8'))
        if self.simpleBase:
            base1 = self._PGenr.SimpleTypeDict.get(self.simpleBase[0])
            if base1:
                base2 = base1.base or None
            else:
                base2 = None
            while base2:
                self.addSimpleBase(base2.encode('utf-8'))
                base2 = self._PGenr.SimpleTypeDict.get(base2)
                if base2:
                    base2 = base2.getBase()

    def rationalizeMixedBases(self):
        mixed = self.hasMixedInChain()
        if mixed:
            self.equalizeMixedBases()

    def hasMixedInChain(self):
        if self.isMixed():
            return True
        base = self.getBase()
        if base and base in self._PGenr.ElementDict:
            parent = self._PGenr.ElementDict[base]
            return parent.hasMixedInChain()
        else:
            return False

    def equalizeMixedBases(self):
        if not self.isMixed():
            self.setMixed(True)
        base = self.getBase()
        if base and base in self._PGenr.ElementDict:
            parent = self._PGenr.ElementDict[base]
            parent.equalizeMixedBases()

    def checkMixedBasesChain(self, child, childMixed):
        base = self.getBase()
        if base and base in self._PGenr.ElementDict:
            parent = self._PGenr.ElementDict[base]
            if childMixed != parent.isMixed():
                self.mixedExtensionError = 1
                return
            parent.checkMixedBasesChain(child, childMixed)

    def resolve_type(self):
        self.complex = 0
        # If it has any attributes, then it's complex.
        attrDefs = self.getAttributeDefs()
        if len(attrDefs) > 0:
            self.complex = 1
            # type_val = ''
        type_val = self.resolve_type_1()
        if type_val == self._PGenr.AnyType:
            return self._PGenr.AnyType
        if type_val in self._PGenr.SimpleTypeDict:
            self.addSimpleBase(type_val.encode('utf-8'))
            simple_type = self._PGenr.SimpleTypeDict[type_val]
            list_type = simple_type.resolve_list_type(self._PGenr.SimpleTypeDict)
            self.setListType(list_type)
        if type_val:
            if type_val in self._PGenr.ElementDict:
                type_val1 = type_val
                # The following loop handles the case where an Element's
                # reference element has no sub-elements and whose type is
                # another simpleType (potentially of the same name). Its
                # fundamental function is to avoid the incorrect
                # categorization of "complex" to Elements which are not and
                # correctly resolve the Element's type as well as its
                # potential values. It also handles cases where the Element's
                # "simpleType" is so-called "top level" and is only available
                # through the global SimpleTypeDict.
                i = 0
                while True:
                    element = self._PGenr.ElementDict[type_val1]
                    # Resolve our potential values if present
                    self.values = element.values
                    # If the type is available in the SimpleTypeDict, we
                    # know we've gone far enough in the Element hierarchy
                    # and can return the correct base type.
                    t = element.resolve_type_1()
                    if t in self._PGenr.SimpleTypeDict:
                        type_val1 = self._PGenr.SimpleTypeDict[t].getBase()
                        if type_val1 and not self._PGenr.is_builtin_simple_type(type_val1):
                            type_val1 = strip_namespace(type_val1)
                        break
                    # If the type name is the same as the previous type name
                    # then we know we've fully resolved the Element hierarchy
                    # and the Element is well and truely "complex". There is
                    # also a need to handle cases where the Element name and
                    # its type name are the same (ie. this is our first time
                    # through the loop). For example:
                    #   <xsd:element name="ReallyCool" type="ReallyCool"/>
                    #   <xsd:simpleType name="ReallyCool">
                    #     <xsd:restriction base="xsd:string">
                    #       <xsd:enumeration value="MyThing"/>
                    #     </xsd:restriction>
                    #   </xsd:simpleType>
                    if t == type_val1 and i != 0:
                        break
                    if t not in self._PGenr.ElementDict:
                        type_val1 = t
                        break
                    type_val1 = t
                    i += 1
                if self._PGenr.is_builtin_simple_type(type_val1):
                    type_val = type_val1
                else:
                    self.complex = 1
            elif type_val in self._PGenr.SimpleTypeDict:
                count = 0
                type_val1 = type_val
                while True:
                    element = self._PGenr.SimpleTypeDict[type_val1]
                    type_val1 = element.getBase()
                    if type_val1 and not self._PGenr.is_builtin_simple_type(type_val1):
                        type_val1 = strip_namespace(type_val1)
                    if type_val1 is None:
                        # Something seems wrong.  Can't find base simple type.
                        #   Give up and use default.
                        type_val = self._PGenr.StringType[0]
                        break
                    if type_val1 in self._PGenr.SimpleTypeDict:
                        count += 1
                        if count > 10:
                            # Give up.  We're in a loop.  Use default.
                            type_val = self._PGenr.StringType[0]
                            break
                    else:
                        type_val = type_val1
                        break
            else:
                if self._PGenr.is_builtin_simple_type(type_val):
                    pass
                else:
                    type_val = self._PGenr.StringType[0]
        else:
            type_val = self._PGenr.StringType[0]
        return type_val

    def resolve_type_1(self):
        type_val = ''
        if 'type' in self.attrs:
            type_val = self.attrs['type']
            if type_val in self._PGenr.SimpleTypeDict:
                self.simpleType = type_val
        elif 'ref' in self.attrs:
            type_val = strip_namespace(self.attrs['ref'])
        elif 'name' in self.attrs:
            type_val = strip_namespace(self.attrs['name'])
            #type_val = self.attrs['name']
        return type_val

    def annotate_find_type(self):
        self.schema_type = None
        if 'type' in self.attrs:
            self.schema_type = self.attrs['type']
        if self.type == self._PGenr.AnyTypeIdentifier:
            pass
        else:
            type_val = self.resolve_type()
            self.attrs['type'] = type_val
            self.type = type_val
        if not self.complex:
            self._PGenr.SimpleElementDict[self.name] = self
        for child in self.children:
            child.annotate_find_type()

    def annotate_tree(self):
        # If there is a namespace, replace it with an underscore.
        if self.base:
            self.base = strip_namespace(self.base)
        self.unmappedCleanName = self._PGenr.cleanupName(self.name)
        self.cleanName = self._PGenr.mapName(self.unmappedCleanName)
        self.replace_attributeGroup_names()
        # Resolve "maxOccurs" attribute
        if 'maxOccurs' in self.attrs.keys():
            maxOccurs = self.attrs['maxOccurs']
        elif self.choice and 'maxOccurs' in self.choice.attrs.keys():
            maxOccurs = self.choice.attrs['maxOccurs']
        else:
            maxOccurs = 1
        # Resolve "minOccurs" attribute
        if 'minOccurs' in self.attrs.keys():
            minOccurs = self.attrs['minOccurs']
        elif self.choice and 'minOccurs' in self.choice.attrs.keys():
            minOccurs = self.choice.attrs['minOccurs']
        else:
            minOccurs = 1
        # Cleanup "minOccurs" and "maxOccurs" attributes
        try:
            minOccurs = int(minOccurs)
            if minOccurs == 0:
                self.optional = True
        except ValueError:
            err_msg('*** %s  minOccurs must be integer.\n' % self.getName())
            sys.exit(1)
        try:
            if maxOccurs == 'unbounded':
                maxOccurs = 99999
            else:
                maxOccurs = int(maxOccurs)
        except ValueError:
            err_msg('*** %s  maxOccurs must be integer or "unbounded".\n' % (
                self.getName(), ))
            sys.exit(1)
        self.minOccurs = minOccurs
        self.maxOccurs = maxOccurs

        # If it does not have a type, then make the type the same as the name.
        if self.type == 'NoneType' and self.name:
            self.type = self.name
        # Is it a mixed-content element definition?
        if 'mixed' in self.attrs.keys():
            mixed = self.attrs['mixed'].strip()
            if mixed == '1' or mixed.lower() == 'true':
                self.mixed = 1
        # If this element has a base and the base is a simple type and
        #   the simple type is collapseWhiteSpace, then mark this
        #   element as collapseWhiteSpace.
        base = self.getBase()
        if base and base in self._PGenr.SimpleTypeDict:
            parent = self._PGenr.SimpleTypeDict[base]
            if isinstance(parent, SimpleTypeElement) and \
                parent.collapseWhiteSpace:
                self.collapseWhiteSpace = 1
        # Do it recursively for all descendents.
        for child in self.children:
            child.annotate_tree()

    #
    # For each name in the attributeGroupNameList for this element,
    #   add the attributes defined for that name in the global
    #   attributeGroup dictionary.
    def replace_attributeGroup_names(self):
        for groupName in self.attributeGroupNameList:
            key = None
            if self._PGenr.AttributeGroups.has_key(groupName):
                key =groupName
            else:
                # Looking for name space prefix
                keyList = groupName.split(':')
                if len(keyList) > 1:
                    key1 = keyList[1]
                    if self._PGenr.AttributeGroups.has_key(key1):
                        key = key1
            if key is not None:
                attrGroup = self._PGenr.AttributeGroups[key]
                for name in attrGroup.getKeys():
                    attr = attrGroup.get(name)
                    self.attributeDefs[name] = attr
            else:
                logging.debug('attributeGroup %s not defined.\n' % (
                    groupName, ))

    def __str__(self):
        s1 = '<XschemaElement name: "%s" type: "%s">' % \
            (self.getName(), self.getType(), )
        return s1
    __repr__ = __str__

    def fix_dup_names(self):
        # Patch-up names that are used for both a child element and an attribute.
        #
        attrDefs = self.getAttributeDefs()
        # Collect a list of child element names.
        #   Must do this for base (extension) elements also.
        elementNames = []
        self.collectElementNames(elementNames, 0)
        replaced = []
        # Create the needed new attributes.
        keys = attrDefs.keys()
        for key in keys:
            attr = attrDefs[key]
            name = attr.getName()
            if name in elementNames:
                newName = name + '_attr'
                newAttr = XschemaAttribute(self_.PGenr, newName)
                attrDefs[newName] = newAttr
                replaced.append(name)
        # Remove the old (replaced) attributes.
        for name in replaced:
            del attrDefs[name]
        for child in self.children:
            child.fix_dup_names()

    def collectElementNames(self, elementNames, count):
        for child in self.children:
            elementNames.append(self._PGenr.cleanupName(child.cleanName))
        base = self.getBase()
        if base and base in self._PGenr.ElementDict:
            parent = self._PGenr.ElementDict[base]
            count += 1
            if count > 100:
                msg = ('Extension/restriction recursion detected.  ' +
                      'Suggest you check definitions of types ' +
                      '%s and %s.'
                      )
                msg = msg % (self.getName(), parent.getName(), )
                raise RuntimeError(msg)
            parent.collectElementNames(elementNames, count)

    def coerce_attr_types(self):
        replacements = []
        attrDefs = self.getAttributeDefs()
        for idx, name in enumerate(attrDefs):
            attr = attrDefs[name]
            attrType = attr.getData_type()
            if attrType == self._PGenr.IDType or \
                attrType == self._PGenr.IDREFType or \
                attrType == self._PGenr.IDREFSType:
                attr.setData_type(self._PGenr.StringType[0])
        for child in self.children:
            child.coerce_attr_types()
# end class XschemaElement

class XschemaAttributeGroup:
    def __init__(self, name='', group=None):
        self.name = name
        if group:
            self.group = group
        else:
            self.group = {}
    def setName(self, name): self.name = name
    def getName(self): return self.name
    def setGroup(self, group): self.group = group
    def getGroup(self): return self.group
    def get(self, name, default=None):
        if self.group.has_key(name):
            return self.group[name]
        else:
            return default
    def getKeys(self):
        return self.group.keys()
    def add(self, name, attr):
        self.group[name] = attr
    def delete(self, name):
        if has_key(self.group, name):
            del self.group[name]
            return 1
        else:
            return 0
# end class XschemaAttributeGroup

class XschemaGroup:
    def __init__(self, ref):
        self.ref = ref
# end class XschemaGroup

class XschemaAttribute:
    def __init__(self, parser_generator, name, data_type='xs:string', use='optional', default=None):
        self._PGenr = parser_generator
        self.name = name
        self.cleanName = self._PGenr.cleanupName(name)
        self.data_type = data_type
        self.use = use
        self.default = default
        # Enumeration values for the attribute.
        self.values = list()
    def getCleanName(self): return self.cleanName
    def setName(self, name): self.name = name
    def getName(self): return self.name
    def setData_type(self, data_type): self.data_type = data_type
    def getData_type(self): return self.data_type
    def getType(self):
        returnType = self.data_type
        if self._PGenr.SimpleElementDict.has_key(self.data_type):
            typeObj = self._PGenr.SimpleElementDict[self.data_type]
            typeObjType = typeObj.getRawType()
            if typeObjType in StringType or \
                typeObjType == TokenType or \
                typeObjType == DateTimeType or \
                typeObjType == TimeType or \
                typeObjType == DateType or \
                typeObjType in IntegerType or \
                typeObjType == DecimalType or \
                typeObjType == PositiveIntegerType or \
                typeObjType == NegativeIntegerType or \
                typeObjType == NonPositiveIntegerType or \
                typeObjType == NonNegativeIntegerType or \
                typeObjType == BooleanType or \
                typeObjType == FloatType or \
                typeObjType == DoubleType:
                returnType = typeObjType
        return returnType
    def setUse(self, use): self.use = use
    def getUse(self): return self.use
    def setDefault(self, default): self.default = default
    def getDefault(self): return self.default
# end class XschemaAttribute


#
# SAX handler
#
class XschemaHandler(handler.ContentHandler):
    def __init__(self, parser_generator):
        handler.ContentHandler.__init__(self)
        self.stack = []
        self.root = None
        self.inElement = 0
        self.inComplexType = 0
        self.inNonanonymousComplexType = 0
        self.inSequence = 0
        self.inChoice = 1
        self.inAttribute = 0
        self.inAttributeGroup = 0
        self.inSimpleType = 0
        self.inSimpleContent = 0
        self.inRestrictionType = 0
        self.inAnnotationType = 0
        self.inDocumentationType = 0
        # The last attribute we processed.
        self.lastAttribute = None
        # Simple types that exist in the global context and may be used to
        # qualify the type of many elements and/or attributes.
        self.topLevelSimpleTypes = list()
        # The current choice type we're in
        self.currentChoice = None
        self.firstElement = True
        self._PGenr = parser_generator

    def getRoot(self):
        return self.root

    def extractSchemaNamespace(self, attrs):
        schemaUri = 'http://www.w3.org/2001/XMLSchema'
        keys = [ x for x, v in attrs.items() if v == schemaUri ]
        if not keys:
            return None
        keys = [ x[6:] for x in keys if x.startswith('xmlns:') ]
        if not keys:
            return None
        return keys[0]

    def startElement(self, name, attrs):
        logging.debug("Start element: %s %s" % (name, repr(attrs.items())))
        if len(self.stack) == 0 and self.firstElement:
            self.firstElement = False
            schemaNamespace = self.extractSchemaNamespace(attrs)
            if schemaNamespace:
                self._PGenr.XsdNameSpace = schemaNamespace
                self._PGenr.set_type_constants(schemaNamespace + ':')
            else:
                if len(name.split(':')) == 1:
                    self._PGenr.XsdNameSpace = ''
                    self._PGenr.set_type_constants('')

        SchemaType = self._PGenr.SchemaType
        ElementType = self._PGenr.ElementType
        ComplexTypeType = self._PGenr.ComplexTypeType
        AnyType = self._PGenr.AnyType
        GroupType = self._PGenr.GroupType
        SequenceType = self._PGenr.SequenceType
        ChoiceType = self._PGenr.ChoiceType
        AttributeType = self._PGenr.AttributeType
        AttributeGroupType = self._PGenr.AttributeGroupType
        SimpleContentType = self._PGenr.SimpleContentType
        ComplexContentType = self._PGenr.ComplexContentType
        ExtensionType = self._PGenr.ExtensionType
        StringType             = self._PGenr.StringType
        IDTypes                = self._PGenr.IDTypes
        NameTypes              = self._PGenr.NameTypes
        TokenType              = self._PGenr.TokenType
        DateTimeType           = self._PGenr.DateTimeType
        TimeType               = self._PGenr.TimeType
        DateType               = self._PGenr.DateType
        IntegerType            = self._PGenr.IntegerType
        DecimalType            = self._PGenr.DecimalType
        PositiveIntegerType    = self._PGenr.PositiveIntegerType
        NegativeIntegerType    = self._PGenr.NegativeIntegerType
        NonPositiveIntegerType = self._PGenr.NonPositiveIntegerType
        NonNegativeIntegerType = self._PGenr.NonNegativeIntegerType
        BooleanType            = self._PGenr.BooleanType
        FloatType              = self._PGenr.FloatType
        DoubleType             = self._PGenr.DoubleType
        OtherSimpleTypes       = self._PGenr.OtherSimpleTypes
        AnyAttributeType = self._PGenr.AnyAttributeType
        SimpleTypeType = self._PGenr.SimpleTypeType
        RestrictionType = self._PGenr.RestrictionType
        EnumerationType = self._PGenr.EnumerationType
        MinInclusiveType = self._PGenr.MinInclusiveType
        MaxInclusiveType = self._PGenr.MaxInclusiveType
        UnionType = self._PGenr.UnionType
        WhiteSpaceType = self._PGenr.WhiteSpaceType
        ListType = self._PGenr.ListType
        AnnotationType = self._PGenr.AnnotationType
        DocumentationType = self._PGenr.DocumentationType

        if name == SchemaType:
            self.inSchema = 1
            element = XschemaElement(self._PGenr, attrs)
            if len(self.stack) == 1:
                element.setTopLevel(1)
            self.stack.append(element)
            # If there is an attribute "xmlns" and its value is
            #   "http://www.w3.org/2001/XMLSchema", then remember and
            #   use that namespace prefix.
            for name, value in attrs.items():
                if name[:6] == 'xmlns:':
                    nameSpace = name[6:] + ':'
                    self._PGenr.NamespacesDict[value] = nameSpace
                elif name == 'targetNamespace':
                    self.Targetnamespace = value
        elif (name == ElementType or
            ((name == ComplexTypeType) and (len(self.stack) == 1))
            ):
            self.inElement = 1
            self.inNonanonymousComplexType = 1
            element = XschemaElement(self._PGenr, attrs)
            if not 'type' in attrs.keys() and not 'ref' in attrs.keys():
                element.setExplicitDefine(1)
            if len(self.stack) == 1:
                element.setTopLevel(1)
            if 'substitutionGroup' in attrs.keys() and 'name' in attrs.keys():
                substituteName = attrs['name']
                headName = attrs['substitutionGroup']
                if headName not in self.SubstitutionGroups:
                    self.SubstitutionGroups[headName] = []
                self.SubstitutionGroups[headName].append(substituteName)
            if name == ComplexTypeType:
                element.complexType = 1
            if self.inChoice and self.currentChoice:
                element.choice = self.currentChoice
            self.stack.append(element)
        elif name == ComplexTypeType:
            # If it have any attributes and there is something on the stack,
            #   then copy the attributes to the item on top of the stack.
            if len(self.stack) > 1 and len(attrs) > 0:
                parentDict = self.stack[-1].getAttrs()
                for key in attrs.keys():
                    parentDict[key] = attrs[key]
            self.inComplexType = 1
        elif name == AnyType:
            element = XschemaElement(self._PGenr, attrs)
            element.type = AnyTypeIdentifier
            self.stack.append(element)
        elif name == GroupType:
            element = XschemaElement(self._PGenr, attrs)
            if len(self.stack) == 1:
                element.setTopLevel(1)
            self.stack.append(element)
        elif name == SequenceType:
            self.inSequence = 1
        elif name == ChoiceType:
            self.currentChoice = XschemaElement(self._PGenr, attrs)
            self.inChoice = 1
        elif name == AttributeType:
            self.inAttribute = 1
            if 'name' in attrs.keys():
                name = attrs['name']
            elif 'ref' in attrs.keys():
                name = strip_namespace(attrs['ref'])
            else:
                name = 'no_attribute_name'
            if 'type' in attrs.keys():
                data_type = attrs['type']
            else:
                data_type = StringType[0]
            if 'use' in attrs.keys():
                use = attrs['use']
            else:
                use = 'optional'
            if 'default' in attrs.keys():
                default = attrs['default']
            else:
                default = None
            if self.stack[-1].attributeGroup:
                # Add this attribute to a current attributeGroup.
                attribute = XschemaAttribute(self._PGenr, name, data_type, use, default)
                self.stack[-1].attributeGroup.add(name, attribute)
            else:
                # Add this attribute to the element/complexType.
                attribute = XschemaAttribute(self._PGenr, name, data_type, use, default)
                self.stack[-1].attributeDefs[name] = attribute
            self.lastAttribute = attribute
        elif name == AttributeGroupType:
            self.inAttributeGroup = 1
            # If it has attribute 'name', then it's a definition.
            #   Prepare to save it as an attributeGroup.
            if 'name' in attrs.keys():
                name = strip_namespace(attrs['name'])
                attributeGroup = XschemaAttributeGroup(name)
                element = XschemaElement(self._PGenr, attrs)
                if len(self.stack) == 1:
                    element.setTopLevel(1)
                element.setAttributeGroup(attributeGroup)
                self.stack.append(element)
            # If it has attribute 'ref', add it to the list of
            #   attributeGroups for this element/complexType.
            if 'ref' in attrs.keys():
                self.stack[-1].attributeGroupNameList.append(attrs['ref'])
        elif name == SimpleContentType:
            self.inSimpleContent = 1
            if len(self.stack) > 0:
                self.stack[-1].setSimpleContent(True)
        elif name == ComplexContentType:
            pass
        elif name == ExtensionType:
            if 'base' in attrs.keys() and len(self.stack) > 0:
                extensionBase = attrs['base']
                if extensionBase in StringType or \
                    extensionBase in IDTypes or \
                    extensionBase in NameTypes or \
                    extensionBase == TokenType or \
                    extensionBase == DateTimeType or \
                    extensionBase == TimeType or \
                    extensionBase == DateType or \
                    extensionBase in IntegerType or \
                    extensionBase == DecimalType or \
                    extensionBase == PositiveIntegerType or \
                    extensionBase == NegativeIntegerType or \
                    extensionBase == NonPositiveIntegerType or \
                    extensionBase == NonNegativeIntegerType or \
                    extensionBase == BooleanType or \
                    extensionBase == FloatType or \
                    extensionBase == DoubleType or \
                    extensionBase in OtherSimpleTypes:
                    if (len(self.stack) > 0 and
                        isinstance(self.stack[-1], XschemaElement)):
                        self.stack[-1].addSimpleBase(extensionBase.encode('utf-8'))
                else:
                    self.stack[-1].setBase(extensionBase)
        elif name == AnyAttributeType:
            # Mark the current element as containing anyAttribute.
            self.stack[-1].setAnyAttribute(1)
        elif name == SimpleTypeType:
            # fixlist
            if self.inAttribute:
                pass
            elif self.inSimpleType and self.inRestrictionType:
                pass
            else:
                # Save the name of the simpleType, but ignore everything
                #   else about it (for now).
                if 'name' in attrs.keys():
                    stName = self._PGenr.cleanupName(attrs['name'])
                elif len(self.stack) > 0:
                    stName = self._PGenr.cleanupName(self.stack[-1].getName())
                else:
                    stName = None
                # If the parent is an element, mark it as a simpleType.
                if len(self.stack) > 0:
                    self.stack[-1].setSimpleType(1)
                element = SimpleTypeElement(stName)
                element.setDefault(attrs.get('default'))
                self._PGenr.SimpleTypeDict[stName] = element
                self.stack.append(element)
            self.inSimpleType = 1
        elif name == RestrictionType:
            if self.inAttribute:
                if attrs.has_key('base'):
                    self.lastAttribute.setData_type(attrs['base'])
            else:
                # If we are in a simpleType, capture the name of
                #   the restriction base.
                if ((self.inSimpleType or self.inSimpleContent) and
                    'base' in attrs.keys()):
                    self.stack[-1].setBase(attrs['base'])
                else:
                    if 'base' in attrs.keys():
                        self.stack[-1].setRestrictionBase(attrs['base'])
                self.stack[-1].setRestrictionAttrs(dict(attrs))
            self.inRestrictionType = 1
        elif name in [EnumerationType, MinInclusiveType, MaxInclusiveType]:
            if not attrs.has_key('value'):
                return
            if self.inAttribute:
                # We know that the restriction is on an attribute and the
                # attributes of the current element are un-ordered so the
                # instance variable "lastAttribute" will have our attribute.
                values = self.lastAttribute.values
            elif self.inElement and attrs.has_key('value'):
                # We're not in an attribute so the restriction must have
                # been placed on an element and that element will still be
                # in the stack. We search backwards through the stack to
                # find the last element.
                element = None
                if self.stack:
                    for entry in reversed(self.stack):
                        if isinstance(entry, XschemaElement):
                            element = entry
                            break
                if element is None:
                    err_msg('Cannot find element to attach enumeration: %s\n' % (
                            attrs['value']), )
                    sys.exit(1)
                values = element.values
            elif self.inSimpleType and attrs.has_key('value'):
                # We've been defined as a simpleType on our own.
                values = self.stack[-1].values
            if name == EnumerationType:
                values.append(attrs['value'])
            else:
                if len(values) == 0:
                    values.extend([None, None])
                if name == MinInclusiveType:
                    values[0] = {'minimum': int(attrs['value'])}
                else:
                    values[1] = {'maximum': int(attrs['value'])}
        elif name == UnionType:
            # Union types are only used with a parent simpleType and we want
            # the parent to know what it's a union of.
            parentelement = self.stack[-1]
            if (isinstance(parentelement, SimpleTypeElement) and
                attrs.has_key('memberTypes')):
                for member in attrs['memberTypes'].split(" "):
                    self.stack[-1].unionOf.append(member)
        elif name == WhiteSpaceType and self.inRestrictionType:
            if attrs.has_key('value'):
                if attrs.getValue('value') == 'collapse':
                    self.stack[-1].collapseWhiteSpace = 1
        elif name == ListType:
            self.inListType = 1
            # fixlist
            if self.inSimpleType: # and self.inRestrictionType:
                self.stack[-1].setListType(1)
            if self.inSimpleType:
                if attrs.has_key('itemType'):
                    self.stack[-1].setBase(attrs['itemType'])
        elif name == AnnotationType:
            self.inAnnotationType = 1
        elif name == DocumentationType:
            if self.inAnnotationType:
                self.inDocumentationType = 1
        logging.debug("Start element stack: %d" % len(self.stack))

    def endElement(self, name):
        logging.debug("End element: %s" % (name))
        logging.debug("End element stack: %d" % (len(self.stack)))

        SchemaType = self._PGenr.SchemaType
        ElementType = self._PGenr.ElementType
        ComplexTypeType = self._PGenr.ComplexTypeType
        AnyType = self._PGenr.AnyType
        GroupType = self._PGenr.GroupType
        SequenceType = self._PGenr.SequenceType
        ChoiceType = self._PGenr.ChoiceType
        AttributeType = self._PGenr.AttributeType
        AttributeGroupType = self._PGenr.AttributeGroupType
        SimpleContentType = self._PGenr.SimpleContentType
        ComplexContentType = self._PGenr.ComplexContentType
        ExtensionType = self._PGenr.ExtensionType
        StringType             = self._PGenr.StringType
        IDTypes                = self._PGenr.IDTypes
        NameTypes              = self._PGenr.NameTypes
        TokenType              = self._PGenr.TokenType
        DateTimeType           = self._PGenr.DateTimeType
        TimeType               = self._PGenr.TimeType
        DateType               = self._PGenr.DateType
        IntegerType            = self._PGenr.IntegerType
        DecimalType            = self._PGenr.DecimalType
        PositiveIntegerType    = self._PGenr.PositiveIntegerType
        NegativeIntegerType    = self._PGenr.NegativeIntegerType
        NonPositiveIntegerType = self._PGenr.NonPositiveIntegerType
        NonNegativeIntegerType = self._PGenr.NonNegativeIntegerType
        BooleanType            = self._PGenr.BooleanType
        FloatType              = self._PGenr.FloatType
        DoubleType             = self._PGenr.DoubleType
        OtherSimpleTypes       = self._PGenr.OtherSimpleTypes
        AnyAttributeType = self._PGenr.AnyAttributeType
        SimpleTypeType = self._PGenr.SimpleTypeType
        RestrictionType = self._PGenr.RestrictionType
        EnumerationType = self._PGenr.EnumerationType
        MinInclusiveType = self._PGenr.MinInclusiveType
        UnionType = self._PGenr.UnionType
        WhiteSpaceType = self._PGenr.WhiteSpaceType
        ListType = self._PGenr.ListType
        AnnotationType = self._PGenr.AnnotationType
        DocumentationType = self._PGenr.DocumentationType

        if name == SimpleTypeType: # and self.inSimpleType:
            self.inSimpleType = 0
            if self.inAttribute:
                pass
            else:
                # If the simpleType is directly off the root, it may be used to
                # qualify the type of many elements and/or attributes so we
                # don't want to loose it entirely.
                simpleType = self.stack.pop()
                # fixlist
                if len(self.stack) == 1:
                    self.topLevelSimpleTypes.append(simpleType)
                    self.stack[-1].setListType(simpleType.isListType())
        elif name == RestrictionType and self.inRestrictionType:
            self.inRestrictionType = 0
        elif name == ElementType or (name == ComplexTypeType and self.stack[-1].complexType):
            self.inElement = 0
            self.inNonanonymousComplexType = 0
            if len(self.stack) >= 2:
                element = self.stack.pop()
                self.stack[-1].addChild(element)
        elif name == AnyType:
            if len(self.stack) >= 2:
                element = self.stack.pop()
                self.stack[-1].addChild(element)
        elif name == ComplexTypeType:
            self.inComplexType = 0
        elif name == SequenceType:
            self.inSequence = 0
        elif name == ChoiceType:
            self.currentChoice = None
            self.inChoice = 0
        elif name == AttributeType:
            self.inAttribute = 0
        elif name == AttributeGroupType:
            self.inAttributeGroup = 0
            if self.stack[-1].attributeGroup:
                # The top of the stack contains an XschemaElement which
                #   contains the definition of an attributeGroup.
                #   Save this attributeGroup in the
                #   global AttributeGroup dictionary.
                attributeGroup = self.stack[-1].attributeGroup
                name = attributeGroup.getName()
                self.AttributeGroups[name] = attributeGroup
                self.stack[-1].attributeGroup = None
                self.stack.pop()
            else:
                # This is a reference to an attributeGroup.
                # We have already added it to the list of attributeGroup names.
                # Leave it.  We'll fill it in during annotate.
                pass
        elif name == GroupType:
            element = self.stack.pop()
            name = element.getAttrs()['name']
            elementGroup = XschemaGroup(element.name)
            ref = element.getAttrs().get('ref')
            if len(self.stack) == 1 and ref is None:
                # This is the definition
                ElementGroups[name] = element
            elif len(self.stack) > 1 and ref is not None:
                # This is a reference. Add it to the parent's children. We
                # need to preserve the order of elements.
                element.setElementGroup(elementGroup)
                self.stack[-1].addChild(element)
        elif name == SchemaType:
            self.inSchema = 0
            if len(self.stack) != 1:
                # fixlist
                err_msg('*** error stack.  len(self.stack): %d\n' % (
                    len(self.stack), ))
                sys.exit(1)
            if self.root: #change made to avoide logging error
                logging.debug("Previous root: %s" % (self.root.name))
            else:
                logging.debug ("Prvious root:   None")
            self.root = self.stack[0]
            if self.root:
                logging.debug("New root: %s"  % (self.root.name))
            else:
                logging.debug("New root: None")
        elif name == SimpleContentType:
            self.inSimpleContent = 0
        elif name == ComplexContentType:
            pass
        elif name == ExtensionType:
            pass
        elif name == ListType:
            # List types are only used with a parent simpleType and can have a
            # simpleType child. So, if we're in a list type we have to be
            # careful to reset the inSimpleType flag otherwise the handler's
            # internal stack will not be unrolled correctly.
            self.inSimpleType = 1
            self.inListType = 0
        elif name == AnnotationType:
            self.inAnnotationType = 0
        elif name == DocumentationType:
            if self.inAnnotationType:
                self.inDocumentationType = 0

    def characters(self, chrs):
        if self.inDocumentationType:
            # If there is an annotation/documentation element, save it.
            text = ' '.join(chrs.strip().split())
            if len(self.stack) > 1 and len(chrs) > 0:
                self.stack[-1].documentation += chrs
        elif self.inElement:
            pass
        elif self.inComplexType:
            pass
        elif self.inSequence:
            pass
        elif self.inChoice:
            pass

def strip_namespace(val):
    return val.split(':')[-1]


# Function that gets called recursively in order to expand nested references
# to element groups
def _expandGR(grp, visited):
    # visited is used for loop detection
    children = []
    changed = False
    for child in grp.children:
        groupRef = child.getElementGroup()
        if not groupRef:
            children.append(child)
            continue
        ref = groupRef.ref
        referencedGroup = ElementGroups.get(ref, None)
        if referencedGroup is None:
            ref = strip_namespace(ref)
            referencedGroup = ElementGroups.get(ref, None)
        if referencedGroup is None:
            #err_msg('*** Reference to unknown group %s' % groupRef.attrs['ref'])
            err_msg('*** Reference to unknown group %s\n' % groupRef.ref)
            continue
        visited.add(id(grp))
        if id(referencedGroup) in visited:
            #err_msg('*** Circular reference for %s' % groupRef.attrs['ref'])
            err_msg('*** Circular reference for %s\n' % groupRef.ref)
            continue
        changed = True
        _expandGR(referencedGroup, visited)
        children.extend(referencedGroup.children)
    if changed:
        # Avoid replacing the list with a copy of the list
        grp.children = children

def expandGroupReferences(grp):
    visited = set()
    _expandGR(grp, visited)

def err_msg(msg):
    sys.stderr.write(msg)


USAGE_TEXT = __doc__

def usage():
    print USAGE_TEXT
    sys.exit(1)


def main():

    pgenr = XsdParserGenerator()
    pgenr.args_parse()
    pgenr.init_with_args()
    pgenr.parseAndGenerate()

if __name__ == '__main__':
    import cgitb
    cgitb.enable(format='text')
    logging.basicConfig(level=logging.WARN,)
    main()
