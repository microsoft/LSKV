# Copyright (c) Microsoft Corporation. All rights reserved. Licensed under the
# MIT license.

cmake_minimum_required(VERSION 3.16)

project(ccf_kvs LANGUAGES C CXX)

if(NOT TARGET ccf)
  find_package(ccf REQUIRED)
endif()

add_subdirectory(3rdparty)
add_subdirectory(proto)

option(
  PUBLIC_MAPS
  "If enabled, all keys and values are recorded in plaintext in the ledger (insecure!)"
  OFF)

add_ccf_app(
  ccf_kvs
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
  status.enclave
  protobuf.enclave
  LINK_LIBS_VIRTUAL
  etcd.virtual
  status.virtual
  protobuf.virtual)

# Generate an ephemeral signing key
add_custom_command(
  OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/signing_key.pem
  COMMAND openssl genrsa -out ${CMAKE_CURRENT_BINARY_DIR}/signing_key.pem -3
          3072)
add_custom_target(app_signing_key ALL
                  DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/signing_key.pem)

sign_app_library(ccf_kvs.enclave ${CMAKE_CURRENT_SOURCE_DIR}/oe_sign.conf
                 ${CMAKE_CURRENT_BINARY_DIR}/signing_key.pem)
