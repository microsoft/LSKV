# Copyright (c) Microsoft Corporation. All rights reserved. Licensed under the
# MIT license.

cmake_minimum_required(VERSION 3.16)

project(lskv LANGUAGES C CXX)

option(CCF_UNSAFE "build with unsafe options" OFF)
if(CCF_UNSAFE)
  message(WARNING "Building with unsafe options")
  find_package(ccf_unsafe REQUIRED)
else()
  find_package(ccf REQUIRED)
endif()

add_subdirectory(proto)

option(
  PUBLIC_MAPS
  "If enabled, all keys and values are recorded in plaintext in the ledger (insecure!)"
  OFF)

option(VERBOSE_LOGGING "enable verbose logging" OFF)

add_ccf_app(
  lskv
  SRCS
  src/app/app.cpp
  src/app/kvstore.cpp
  src/app/index.cpp
  src/app/leases.cpp
  INCLUDE_DIRS
  "${CMAKE_BINARY_DIR}/proto"
  "${CCF_DIR}/include/ccf/_private"
  LINK_LIBS_ENCLAVE
  etcd.enclave
  lskvserver.enclave
  status.enclave
  protobuf.enclave
  LINK_LIBS_VIRTUAL
  etcd.virtual
  lskvserver.virtual
  status.virtual
  protobuf.virtual)

if(PUBLIC_MAPS)
  message(STATUS "Using public maps")
  add_compile_definitions(PUBLIC_MAPS)
else()
  message(STATUS "Using private maps")
endif()

if(VERBOSE_LOGGING)
  message(STATUS "Using verbose logging")
  add_compile_definitions(VERBOSE_LOGGING)
else()
  message(STATUS "Using terse logging")
endif()

# Generate an ephemeral signing key
add_custom_command(
  OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/signing_key.pem
  COMMAND openssl genrsa -out ${CMAKE_CURRENT_BINARY_DIR}/signing_key.pem -3
          3072)
add_custom_target(app_signing_key ALL
                  DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/signing_key.pem)

sign_app_library(lskv.enclave ${CMAKE_CURRENT_SOURCE_DIR}/oe_sign.conf
                 ${CMAKE_CURRENT_BINARY_DIR}/signing_key.pem)
