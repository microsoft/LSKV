// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#pragma once

#include "ccf/app_interface.h"

#include <google/protobuf/util/json_util.h>

namespace app::json_grpc
{
  template <typename In>
  In get_json_grpc_payload(const std::shared_ptr<ccf::RpcContext>& ctx)
  {
    auto& request_body = ctx->get_request_body();
    auto request_content_type =
      ctx->get_request_header(http::headers::CONTENT_TYPE);

    if (request_content_type != http::headervalues::contenttype::JSON)
    {
      throw std::logic_error(fmt::format(
        "Unsupported content type. Only {} is supported ",
        http::headervalues::contenttype::JSON));
    }

    std::string input(request_body.begin(), request_body.end());
    In in;
    google::protobuf::util::JsonStringToMessage(input, &in);

    return in;
  }

  template <typename Out>
  void set_json_grpc_response(
    const ccf::grpc::GrpcAdapterResponse<Out>& r,
    const std::shared_ptr<ccf::RpcContext>& ctx)
  {
    auto success_response = std::get_if<ccf::grpc::SuccessResponse<Out>>(&r);
    if (success_response != nullptr)
    {
      const auto& resp = success_response->body;
      ctx->set_response_status(HTTP_STATUS_OK);
      if constexpr (!std::is_same_v<Out, ccf::grpc::EmptyResponse>)
      {
        ctx->set_response_header(
          http::headers::CONTENT_TYPE, http::headervalues::contenttype::JSON);

        std::string json_out;
        google::protobuf::util::MessageToJsonString(resp, &json_out);

        ctx->set_response_body(
          std::vector<uint8_t>(json_out.begin(), json_out.end()));
      }
    }
    else
    {
      auto error_response = std::get<ccf::grpc::ErrorResponse>(r);
      ctx->set_response_status(HTTP_STATUS_BAD_REQUEST);
      ctx->set_response_header(
        http::headers::CONTENT_TYPE, http::headervalues::contenttype::JSON);

      std::string json_out;
      google::protobuf::util::MessageToJsonString(
        error_response.status, &json_out);

      ctx->set_response_body(
        std::vector<uint8_t>(json_out.begin(), json_out.end()));
    }
  }

  template <typename In, typename Out>
  using JsonGrpcReadOnlyEndpoint =
    std::function<ccf::grpc::GrpcAdapterResponse<Out>(
      ccf::endpoints::ReadOnlyEndpointContext& ctx, In&& payload)>;

  template <typename In, typename Out>
  using JsonGrpcEndpoint = std::function<ccf::grpc::GrpcAdapterResponse<Out>(
    ccf::endpoints::EndpointContext& ctx, In&& payload)>;

  template <typename In, typename Out>
  ccf::endpoints::EndpointFunction json_grpc_adapter(
    const JsonGrpcEndpoint<In, Out>& f)
  {
    return [f](ccf::endpoints::EndpointContext& ctx) {
      set_json_grpc_response<Out>(
        f(ctx, get_json_grpc_payload<In>(ctx.rpc_ctx)), ctx.rpc_ctx);
    };
  }

  template <typename In, typename Out>
  ccf::endpoints::ReadOnlyEndpointFunction json_grpc_adapter_ro(
    const JsonGrpcReadOnlyEndpoint<In, Out>& f)
  {
    return [f](ccf::endpoints::ReadOnlyEndpointContext& ctx) {
      set_json_grpc_response<Out>(
        f(ctx, get_json_grpc_payload<In>(ctx.rpc_ctx)), ctx.rpc_ctx);
    };
  }
}; // namespace app::json_grpc