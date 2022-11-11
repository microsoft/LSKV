# Copyright (c) Microsoft Corporation. All rights reserved. Licensed under the
# MIT License.

# get the current version from git
find_package(Git)
execute_process(
  COMMAND ${GIT_EXECUTABLE} describe --tags --dirty
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  OUTPUT_VARIABLE "LSKV_VERSION"
  OUTPUT_STRIP_TRAILING_WHITESPACE
  RESULT_VARIABLE RETURN_CODE)
if(NOT RETURN_CODE STREQUAL "0")
  message(FATAL_ERROR "Error calling git describe")
endif()

# strip 'v' prefix from version
string(REGEX REPLACE "^v" "" LSKV_VERSION ${LSKV_VERSION})

# Convert git description into cmake list, separated at '-'
string(REPLACE "-" ";" LSKV_VERSION_COMPONENTS ${LSKV_VERSION})

message(STATUS "Got long version ${LSKV_VERSION}")
list(GET LSKV_VERSION_COMPONENTS 0 LSKV_VERSION_SHORT)

message(STATUS "Got short version ${LSKV_VERSION_SHORT}")
