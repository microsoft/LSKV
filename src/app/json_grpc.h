// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#pragma once

#include "ccf/app_interface.h"
#include "exceptions.h"

#include <google/protobuf/empty.pb.h>
#include <google/protobuf/util/json_util.h>
#include <memory>
#include <string>
#include <utility>
#include <vector>

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
      throw app::exceptions::WrongMediaType(fmt::format(
        "Unsupported content type {}. Only {} is supported.",
        request_content_type.value_or(""),
        http::headervalues::contenttype::JSON));
    }

    std::string input(request_body.begin(), request_body.end());
    In in;
    auto status = google::protobuf::util::JsonStringToMessage(input, &in);
    if (!status.ok())
    {
      throw app::exceptions::BadRequest(status.ToString());
    }

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
      if constexpr (!std::is_same_v<Out, google::protobuf::Empty>)
      {
        ctx->set_response_header(
          http::headers::CONTENT_TYPE, http::headervalues::contenttype::JSON);

        std::string json_out;
        auto status =
          google::protobuf::util::MessageToJsonString(resp, &json_out);
        if (!status.ok())
        {
          throw app::exceptions::BadRequest(status.ToString());
        }

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

  template <typename In>
  using GrpcEndpointInOnlyReadOnly = std::function<void(
    ccf::endpoints::ReadOnlyEndpointContext& ctx, In&& payload)>;

  template <typename In>
  ccf::endpoints::ReadOnlyEndpointFunction json_grpc_adapter_in_only_ro(
    const GrpcEndpointInOnlyReadOnly<In>& f)
  {
    return [f](ccf::endpoints::ReadOnlyEndpointContext& ctx) {
      try
      {
        f(ctx, get_json_grpc_payload<In>(ctx.rpc_ctx)), ctx.rpc_ctx;
      }
      catch (app::exceptions::BadRequest& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
      catch (app::exceptions::WrongMediaType& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
    };
  }

  template <typename In>
  using GrpcEndpointInOnly =
    std::function<void(ccf::endpoints::EndpointContext& ctx, In&& payload)>;

  template <typename In>
  ccf::endpoints::EndpointFunction json_grpc_adapter_in_only(
    const GrpcEndpointInOnly<In>& f)
  {
    return [f](ccf::endpoints::EndpointContext& ctx) {
      try
      {
        f(ctx, get_json_grpc_payload<In>(ctx.rpc_ctx)), ctx.rpc_ctx;
      }
      catch (app::exceptions::BadRequest& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
      catch (app::exceptions::WrongMediaType& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
    };
  }

  template <typename In, typename Out>
  ccf::endpoints::EndpointFunction json_grpc_adapter(
    const ccf::GrpcEndpoint<In, Out>& f)
  {
    return [f](ccf::endpoints::EndpointContext& ctx) {
      try
      {
        set_json_grpc_response<Out>(
          f(ctx, get_json_grpc_payload<In>(ctx.rpc_ctx)), ctx.rpc_ctx);
      }
      catch (app::exceptions::BadRequest& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
      catch (app::exceptions::WrongMediaType& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
    };
  }

  template <typename In, typename Out>
  ccf::endpoints::ReadOnlyEndpointFunction json_grpc_adapter_ro(
    const ccf::GrpcReadOnlyEndpoint<In, Out>& f)
  {
    return [f](ccf::endpoints::ReadOnlyEndpointContext& ctx) {
      try
      {
        set_json_grpc_response<Out>(
          f(ctx, get_json_grpc_payload<In>(ctx.rpc_ctx)), ctx.rpc_ctx);
      }
      catch (app::exceptions::BadRequest& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
      catch (app::exceptions::WrongMediaType& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
    };
  }

  template <typename In, typename Out>
  ccf::endpoints::CommandEndpointFunction json_grpc_command_adapter(
    const ccf::GrpcCommandEndpoint<In, Out>& f)
  {
    return [f](ccf::endpoints::CommandEndpointContext& ctx) {
      try
      {
        set_json_grpc_response<Out>(
          f(ctx, get_json_grpc_payload<In>(ctx.rpc_ctx)), ctx.rpc_ctx);
      }
      catch (app::exceptions::BadRequest& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
      catch (app::exceptions::WrongMediaType& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
    };
  }


  template <typename In, typename Out>
  ccf::historical::HandleReadOnlyHistoricalQuery historical_json_grpc_adapter(
    const app::grpc::HistoricalGrpcReadOnlyEndpoint<In, Out>& f)
  {
    return [f](
             ccf::endpoints::ReadOnlyEndpointContext& ctx,
             ccf::historical::StatePtr historical_state) {
      try
      {
        set_json_grpc_response<Out>(
          f(ctx, historical_state, get_json_grpc_payload<In>(ctx.rpc_ctx)),
          ctx.rpc_ctx);
      }
      catch (app::exceptions::BadRequest& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
      catch (app::exceptions::WrongMediaType& e)
      {
        ctx.rpc_ctx->set_error(std::move(e.error));
      }
    };
  }
}; // namespace app::json_grpc
