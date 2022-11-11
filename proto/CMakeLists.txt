# Copyright (c) Microsoft Corporation. All rights reserved. Licensed under the
# MIT License.

# protoc should be installed under /opt/protoc
set(PROTOC_BINARY_PATH "/opt/protoc/bin/protoc")

if(EXISTS ${PROTOC_BINARY_PATH})
  message(STATUS "Found protobuf compiler: ${PROTOC_BINARY_PATH}")
else()
  message(FATAL_ERROR "Cannot find protobuf compiler: ${PROTOC_BINARY_PATH}")
endif()

include(${CMAKE_SOURCE_DIR}/cmake/protobuf.cmake)

build_proto(google/api/http.proto ${CMAKE_SOURCE_DIR}/3rdparty/googleapis)
build_proto(google/api/annotations.proto
            ${CMAKE_SOURCE_DIR}/3rdparty/googleapis)
build_proto(etcd.proto ${CMAKE_CURRENT_SOURCE_DIR})
build_proto(status.proto ${CMAKE_CURRENT_SOURCE_DIR})
build_proto(lskvserver.proto ${CMAKE_CURRENT_SOURCE_DIR})

option(GENERATE_OPENAPI "generate openapi protobuf spec" OFF)
if(${GENERATE_OPENAPI})
  file(GLOB PROTO_FILES *.proto)

  add_custom_command(
    OUTPUT ${CMAKE_SOURCE_DIR}/openapi.yaml
    COMMAND
      ${PROTOC_BINARY_PATH} --proto_path=${CMAKE_CURRENT_SOURCE_DIR}
      --proto_path=${CMAKE_SOURCE_DIR}/3rdparty/googleapis
      --openapi_out=version=0.0.1:${CMAKE_SOURCE_DIR}
      ${CMAKE_CURRENT_SOURCE_DIR}/lskvserver.proto
      ${CMAKE_CURRENT_SOURCE_DIR}/etcd.proto
    COMMENT
      "Generate OpenAPI source file from protobuf files in ${CMAKE_CURRENT_SOURCE_DIR}"
    DEPENDS ${PROTO_FILES})
  add_custom_target(openapi ALL DEPENDS ${CMAKE_SOURCE_DIR}/openapi.yaml)
endif()
