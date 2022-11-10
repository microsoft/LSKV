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
