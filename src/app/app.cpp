// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT license.

#include "ccf/app_interface.h"
#include "ccf/common_auth_policies.h"
#include "ccf/http_query.h"
#include "ccf/json_handler.h"
#include "etcd.pb.h"
#include "grpc.h"

#define FMT_HEADER_ONLY
#include <fmt/format.h>

namespace app
{
  // Key-value store types
  using Map = kv::Map<std::string, std::string>; // TODO: Use
                                                 // kv::untyped::Map?
  static constexpr auto RECORDS = "public:records";

  // API types
  struct Write
  {
    struct In
    {
      std::string msg;
    };

    using Out = void;
  };
  DECLARE_JSON_TYPE(Write::In);
  DECLARE_JSON_REQUIRED_FIELDS(Write::In, msg);

  class AppHandlers : public ccf::UserEndpointRegistry
  {
  public:
    AppHandlers(ccfapp::AbstractNodeContext& context) :
      ccf::UserEndpointRegistry(context)
    {
      openapi_info.title = "CCF Sample C++ Key-Value Store";
      openapi_info.description = "Sample Key-Value store built on CCF";
      openapi_info.document_version = "0.0.1";

      auto write = [this](auto& ctx, etcdserverpb::PutRequest&& payload) {
        etcdserverpb::PutResponse put_response;
        CCF_APP_DEBUG(
          "Put = [{}]{}:[{}]{}",
          payload.key().size(),
          payload.key(),
          payload.value().size(),
          payload.value());

        auto records_handle = ctx.tx.template rw<Map>(RECORDS);
        records_handle->put(payload.key(), payload.value());
        ctx.rpc_ctx->set_response_status(HTTP_STATUS_OK);

        return ccf::grpc::make_success(put_response);
      };

      make_endpoint(
        "/etcdserverpb.KV/Put",
        HTTP_POST,
        ccf::grpc_adapter<etcdserverpb::PutRequest, etcdserverpb::PutResponse>(
          write),
        ccf::no_auth_required)
        .install();

      auto read = [this](auto& ctx, etcdserverpb::RangeRequest&& payload)
        -> ccf::grpc::GrpcAdapterResponse<etcdserverpb::RangeResponse> {
        etcdserverpb::RangeResponse range_response;

        auto records_handle = ctx.tx.template ro<Map>(RECORDS);
        auto value = records_handle->get(payload.key());
        if (!value.has_value())
        {
          ctx.rpc_ctx->set_response_status(HTTP_STATUS_NOT_FOUND);
          range_response.set_count(0);
          return ccf::grpc::make_error(
            GRPC_STATUS_NOT_FOUND,
            fmt::format("Key {} not found", payload.key()));
        }

        auto* kv = range_response.add_kvs();
        kv->set_key(payload.key());
        kv->set_value(value.value());

        range_response.set_count(1);

        return ccf::grpc::make_success(range_response);
      };

      make_read_only_endpoint(
        "/etcdserverpb.KV/Range",
        HTTP_POST,
        ccf::grpc_read_only_adapter<
          etcdserverpb::RangeRequest,
          etcdserverpb::RangeResponse>(read),
        ccf::no_auth_required)
        .install();
    }
  };
} // namespace app

namespace ccfapp
{
  std::unique_ptr<ccf::endpoints::EndpointRegistry> make_user_endpoints(
    ccfapp::AbstractNodeContext& context)
  {
    return std::make_unique<app::AppHandlers>(context);
  }
} // namespace ccfapp