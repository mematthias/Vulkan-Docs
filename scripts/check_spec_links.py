#!/usr/bin/env python3
#
# Copyright (c) 2018-2019 Collabora, Ltd.
#
# SPDX-License-Identifier: Apache-2.0
#
# Author(s):    Rylie Pavlik <rylie.pavlik@collabora.com>
#
# Purpose:      This file performs some basic checks of the custom macros
#               used in the AsciiDoctor source for the spec, especially
#               related to the validity of the entities linked-to.

from pathlib import Path

from reg import Registry
from spec_tools.entity_db import EntityDatabase
from spec_tools.macro_checker import MacroChecker
from spec_tools.macro_checker_file import MacroCheckerFile
from spec_tools.main import checkerMain
from spec_tools.shared import (AUTO_FIX_STRING, EXTENSION_CATEGORY, MessageId,
                               MessageType)
from apiconventions import APIConventions

###
# "Configuration" constants

FREEFORM_CATEGORY = 'freeform'

# defines mentioned in spec but not needed in registry
EXTRA_DEFINES = (
    'VKAPI_ATTR',
    'VKAPI_CALL',
    'VKAPI_PTR',
    'VK_NO_STDDEF_H',
    'VK_NO_STDINT_H',
    'VK_NO_PROTOTYPES',
    'VK_ONLY_EXPORTED_PROTOTYPES',
    )

# Extra freeform refpages in addition to EXTRA_DEFINES
EXTRA_REFPAGES = (
    'VK_VERSION_1_0',
    'VK_VERSION_1_1',
    'VK_VERSION_1_2',
    'VK_VERSION_1_3',
    'VK_VERSION_1_4',
    'WSIheaders',
    'provisional-headers',
    'Required_Limits',
    )

# These are marked with the code: macro
SYSTEM_TYPES = set(('void', 'char', 'float', 'size_t', 'uintptr_t',
                    'int8_t', 'uint8_t',
                    'int32_t', 'uint32_t',
                    'int64_t', 'uint64_t'))

# Exceptions to:
# error: Definition of link target {} with macro etext (used for category enums) does not exist. (-Wwrong_macro)
# typically caused by using Vulkan-only enums in Vulkan SC blocks with "etext", or because they
# are suffixed differently.
CHECK_UNRECOGNIZED_ETEXT_EXCEPTIONS = (
    "VK_COLORSPACE_SRGB_NONLINEAR_KHR",
    "VK_COLOR_SPACE_DCI_P3_LINEAR_EXT",
    "VK_PIPELINE_CACHE_CREATE_READ_ONLY_BIT",
    "VK_STENCIL_FRONT_AND_BACK",
    "VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_DRAW_PARAMETER_FEATURES",
    "VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VARIABLE_POINTER_FEATURES",
    "VK_STRUCTURE_TYPE_SURFACE_CAPABILITIES2_EXT",
)

# Exceptions to:
# warning: Definition of link target {} with macro ename (used for category enums) does not exist. (-Wbad_enumerant)
# typically caused by Vulkan SC enums not being recognized in Vulkan build
CHECK_UNRECOGNIZED_ENAME_EXCEPTIONS = (
    "VK_ERROR_INVALID_PIPELINE_CACHE_DATA",
    "VK_ERROR_NO_PIPELINE_MATCH",
    "VK_ERROR_VALIDATION_FAILED",
    "VK_MEMORY_HEAP_SEU_SAFE_BIT",
    "VK_PIPELINE_CACHE_CREATE_READ_ONLY_BIT",
    "VK_PIPELINE_CACHE_CREATE_USE_APPLICATION_STORAGE_BIT",
    "VK_PIPELINE_CACHE_HEADER_VERSION_SAFETY_CRITICAL_ONE",
    "VK_PIPELINE_CREATE_RENDERING_FRAGMENT_SHADING_RATE_ATTACHMENT_BIT_KHR",
    "VK_PIPELINE_RASTERIZATION_STATE_CREATE_FRAGMENT_SHADING_RATE_ATTACHMENT_BIT_KHR",
    "VK_ACCESS_2_COMMAND_PREPROCESS_WRITE_BIT_EXT",
    "VK_ACCESS_2_COMMAND_PREPROCESS_READ_BIT_EXT",
    "VK_PIPELINE_STAGE_2_COMMAND_PREPROCESS_BIT_EXT",
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DISABLED_MESSAGES = set((
    MessageId.LEGACY,
    MessageId.REFPAGE_MISSING,
    MessageId.MISSING_MACRO,
    MessageId.EXTENSION,
    # TODO *text macro checking actually needs fixing for Vulkan
    MessageId.MISUSED_TEXT,
    MessageId.MISSING_TEXT
))

CWD = Path('.').resolve()


class VulkanEntityDatabase(EntityDatabase):
    """Vulkan-specific subclass of EntityDatabase."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._conditionally_recognized = set(('fname', 'sname'))

    def makeRegistry(self):
        registryFile = str(ROOT / 'xml/vk.xml')
        registry = Registry()
        registry.loadFile(registryFile)
        return registry

    def getNamePrefix(self):
        return "vk"

    def getPlatformRequires(self):
        return 'vk_platform'

    def getSystemTypes(self):
        return SYSTEM_TYPES

    def populateMacros(self):
        self.addMacros('t', ['link', 'name'], ['funcpointers', 'flags'])

    def populateEntities(self):
        # These are not mentioned in the XML
        for name in EXTRA_DEFINES:
            self.addEntity(name, 'dlink',
                           category=FREEFORM_CATEGORY, generates=False)
        for name in EXTRA_REFPAGES:
            self.addEntity(name, 'code',
                           category=FREEFORM_CATEGORY, generates=False)

    def shouldBeRecognized(self, macro, entity_name):
        """Determine, based on the macro and the name provided, if we should expect to recognize the entity."""
        if super().shouldBeRecognized(macro, entity_name):
            return True

        # The *name: macros in Vulkan should also be recognized if the entity name matches the pattern.
        if macro in self._conditionally_recognized and self.likelyRecognizedEntity(entity_name):
            return True
        return False


class VulkanMacroCheckerFile(MacroCheckerFile):
    """Vulkan-specific subclass of MacroCheckerFile."""

    def perform_entity_check(self, type):
        """Returns True if an entity check should be performed on this
           refpage type.

           Overrides base class definition for Vulkan, since we have refpage
           types which do not correspond to entities in the API."""

        return type != 'builtins' and type != 'spirv'

    def shouldSkipUnrecognizedEntity(self, macro, entity_name):
        """Return True if we should not warn about not recognizing a macro invocation for entity_name."""
        if macro == "ename":
            return entity_name in CHECK_UNRECOGNIZED_ENAME_EXCEPTIONS
        return entity_name in CHECK_UNRECOGNIZED_ETEXT_EXCEPTIONS

    def handleWrongMacro(self, msg, data):
        """Report an appropriate message when we found that the macro used is incorrect.

        May be overridden depending on each API's behavior regarding macro misuse:
        e.g. in some cases, it may be considered a MessageId.LEGACY warning rather than
        a MessageId.WRONG_MACRO or MessageId.EXTENSION.
        """
        message_type = MessageType.WARNING
        message_id = MessageId.WRONG_MACRO
        group = 'macro'

        if data.category == EXTENSION_CATEGORY:
            # Ah, this is an extension
            msg.append(
                'This is apparently an extension name, which should be marked up as a link.')
            message_id = MessageId.EXTENSION
            group = None  # replace the whole thing
        else:
            # Non-extension, we found the macro though.
            if data.macro[0] == self.macro[0] and data.macro[1:] == 'link' and self.macro[1:] == 'name':
                # First letter matches, old is 'name', new is 'link':
                # This is legacy markup
                msg.append(
                    'This is legacy markup that has not been updated yet.')
                message_id = MessageId.LEGACY
            else:
                # Not legacy, just wrong.
                message_type = MessageType.ERROR

        msg.append(AUTO_FIX_STRING)
        self.diag(message_type, message_id, msg,
                  group=group, replacement=self.makeMacroMarkup(data=data), fix=self.makeFix(data=data))

    def allowEnumXrefs(self):
        """Returns True if enums can be specified in the 'xrefs' attribute
        of a refpage.
        """
        return True

def makeMacroChecker(enabled_messages):
    """Create a correctly-configured MacroChecker instance."""
    entity_db = VulkanEntityDatabase()
    return MacroChecker(enabled_messages, entity_db, VulkanMacroCheckerFile, ROOT, APIConventions)


if __name__ == '__main__':
    default_enabled_messages = set(MessageId).difference(
        DEFAULT_DISABLED_MESSAGES)

    all_docs = [str(fn)
                for fn in sorted((ROOT / 'chapters/').glob('**/[A-Za-z]*.adoc'))]
    all_docs.extend([str(fn)
                     for fn in sorted((ROOT / 'appendices/').glob('**/[A-Za-z]*.adoc'))])
    all_docs.append(str(ROOT / 'vkspec.adoc'))

    checkerMain(default_enabled_messages, makeMacroChecker,
                all_docs)
