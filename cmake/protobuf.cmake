# Copyright (c) Microsoft Corporation. All rights reserved. Licensed under the
# MIT License.

function(build_proto proto_file src_dir)
  message(STATUS "Generating source files from proto file ${proto_file}")
  get_filename_component(PROTO_DIR ${proto_file} DIRECTORY)
  get_filename_component(PROTO_NAME ${proto_file} NAME)
  get_filename_component(PROTO_NAME_WE ${proto_file} NAME_WE)

  # generate cpp protoc files
  add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_DIR}/${PROTO_NAME_WE}.pb.h
           ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_DIR}/${PROTO_NAME_WE}.pb.cc
    COMMAND
      ${PROTOC_BINARY_PATH} --proto_path=${CMAKE_CURRENT_SOURCE_DIR}
      --proto_path=${CMAKE_SOURCE_DIR}/3rdparty/googleapis
      --cpp_out=${CMAKE_CURRENT_BINARY_DIR} ${src_dir}/${proto_file}
    COMMENT "Generate C++ source files from protobuf file ${PROTO_NAME}"
    DEPENDS ${src_dir}/${proto_file})

  # generate python grpc and protobuf files
  add_custom_command(
    OUTPUT
      ${CMAKE_SOURCE_DIR}/python/lskv/${PROTO_DIR}/${PROTO_NAME_WE}_pb2.py
      ${CMAKE_SOURCE_DIR}/python/lskv/${PROTO_DIR}/${PROTO_NAME_WE}_pb2.pyi
      ${CMAKE_SOURCE_DIR}/python/lskv/${PROTO_DIR}/${PROTO_NAME_WE}_pb2_grpc.py
    COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/build.sh ${src_dir}/${proto_file}
            ${CMAKE_SOURCE_DIR}/python/lskv/
    COMMENT "Generate Python source files from protobuf file ${PROTO_NAME}"
    DEPENDS ${src_dir}/${proto_file} ${CMAKE_CURRENT_SOURCE_DIR}/build.sh)
  add_custom_target(
    ${PROTO_NAME_WE}_proto_python ALL
    DEPENDS
      ${CMAKE_SOURCE_DIR}/python/lskv/${PROTO_DIR}/${PROTO_NAME_WE}_pb2.py
      ${CMAKE_SOURCE_DIR}/python/lskv/${PROTO_DIR}/${PROTO_NAME_WE}_pb2.pyi
      ${CMAKE_SOURCE_DIR}/python/lskv/${PROTO_DIR}/${PROTO_NAME_WE}_pb2_grpc.py)

  set(PROTOBUF_INCLUDE_DIR ${CCF_DIR}/include/3rdparty/protobuf/src/)

  if(${COMPILE_TARGET} STREQUAL "virtual")
    add_host_library(
      ${PROTO_NAME_WE}.virtual
      ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_DIR}/${PROTO_NAME_WE}.pb.cc
      ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_DIR}/${PROTO_NAME_WE}.pb.h)
    target_include_directories(
      ${PROTO_NAME_WE}.virtual PUBLIC ${PROTOBUF_INCLUDE_DIR}
                                      ${CMAKE_CURRENT_BINARY_DIR})
  else()
    add_enclave_library(
      ${PROTO_NAME_WE}.enclave
      ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_DIR}/${PROTO_NAME_WE}.pb.cc
      ${CMAKE_CURRENT_BINARY_DIR}/${PROTO_DIR}/${PROTO_NAME_WE}.pb.h)
    target_include_directories(
      ${PROTO_NAME_WE}.enclave PUBLIC ${PROTOBUF_INCLUDE_DIR}
                                      ${CMAKE_CURRENT_BINARY_DIR})
  endif()
endfunction()
