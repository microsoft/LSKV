# Copyright (c) Microsoft Corporation. All rights reserved. Licensed under the
# MIT License.

# protoc should be installed under /opt/protoc
set(PROTOC_BINARY_PATH "/opt/protoc/bin/protoc")

if(EXISTS ${PROTOC_BINARY_PATH})
  message(STATUS "Found protobuf compiler: ${PROTOC_BINARY_PATH}")
else()
  message(FATAL_ERROR "Cannot find protobuf compiler: ${PROTOC_BINARY_PATH}")
endif()

set(PROTOBUF_INCLUDE_DIR ${CCF_DIR}/include/3rdparty/protobuf/src/)

set(PROTO_FILES
    ${CMAKE_CURRENT_SOURCE_DIR}/etcd.proto
    ${CMAKE_CURRENT_SOURCE_DIR}/lskvserver.proto
    ${CMAKE_CURRENT_SOURCE_DIR}/status.proto)

option(GENERATE_PYTHON "generate python protobuf and grpc bindings" OFF)

foreach(proto_file ${PROTO_FILES})
  get_filename_component(PROTO_NAME ${proto_file} NAME)
  get_filename_component(PROTO_NAME_WE ${proto_file} NAME_WE)
  message(TRACE "Generating source files from proto file ${PROTO_NAME}")

  add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_NAME_WE}.pb.h
           ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_NAME_WE}.pb.cc
    COMMAND ${PROTOC_BINARY_PATH} --proto_path=${CMAKE_CURRENT_SOURCE_DIR}
            --cpp_out=${CMAKE_CURRENT_BINARY_DIR} ${proto_file}
    COMMENT "Generate C++ source files from protobuf file ${PROTO_NAME}"
    DEPENDS ${proto_file})

  if(${PROTO_NAME_WE} STREQUAL "lskvserver")
    set(EXTRA_INCLUDES ${CMAKE_CURRENT_BINARY_DIR}/etcd.pb.h)
  endif()

  if(${GENERATE_PYTHON})
    add_custom_command(
      OUTPUT ${CMAKE_SOURCE_DIR}/tests/${PROTO_NAME_WE}_pb2.py
      COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/build.sh ${proto_file}
              ${CMAKE_SOURCE_DIR}/tests/
      COMMENT "Generate Python source file from protobuf file ${PROTO_NAME}"
      DEPENDS ${proto_file})
    add_custom_target(${PROTO_NAME_WE}_proto_python ALL
                      DEPENDS ${CMAKE_SOURCE_DIR}/tests/${PROTO_NAME_WE}_pb2.py)
  endif()

  if(${COMPILE_TARGET} STREQUAL "virtual")
    add_host_library(
      ${PROTO_NAME_WE}.virtual
      ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_NAME_WE}.pb.cc
      ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_NAME_WE}.pb.h ${EXTRA_INCLUDES})
    target_include_directories(
      ${PROTO_NAME_WE}.virtual PUBLIC ${PROTOBUF_INCLUDE_DIR}
                                      ${CMAKE_CURRENT_BINARY_DIR})
  else()
    add_enclave_library(
      ${PROTO_NAME_WE}.enclave
      ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_NAME_WE}.pb.cc
      ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_NAME_WE}.pb.h ${EXTRA_INCLUDES})
    target_include_directories(
      ${PROTO_NAME_WE}.enclave PUBLIC ${PROTOBUF_INCLUDE_DIR}
                                      ${CMAKE_CURRENT_BINARY_DIR})
  endif()
endforeach()
