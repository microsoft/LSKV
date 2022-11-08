// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#pragma once

namespace app::grpc
{
  template <typename In>
  using GrpcReadOnlyEndpointInOnly = std::function<void(
    ccf::endpoints::ReadOnlyEndpointContext& ctx, In&& payload)>;

  template <typename In>
  ccf::endpoints::ReadOnlyEndpointFunction grpc_read_only_adapter_in_only(
    const GrpcReadOnlyEndpointInOnly<In>& f)
  {
    return [f](ccf::endpoints::ReadOnlyEndpointContext& ctx) {
      f(ctx, ccf::grpc::get_grpc_payload<In>(ctx.rpc_ctx));
    };
  }

  template <typename In>
  using GrpcEndpointInOnly =
    std::function<void(ccf::endpoints::EndpointContext& ctx, In&& payload)>;

  template <typename In>
  ccf::endpoints::EndpointFunction grpc_adapter_in_only(
    const GrpcEndpointInOnly<In>& f)
  {
    return [f](ccf::endpoints::EndpointContext& ctx) {
      f(ctx, ccf::grpc::get_grpc_payload<In>(ctx.rpc_ctx));
    };
  }

  template <typename In, typename Out>
  using HistoricalGrpcReadOnlyEndpoint =
    std::function<ccf::grpc::GrpcAdapterResponse<Out>(
      ccf::endpoints::ReadOnlyEndpointContext& ctx,
      ccf::historical::StatePtr historical_state,
      In&& payload)>;

  template <typename In, typename Out>
  ccf::historical::HandleReadOnlyHistoricalQuery
  historical_grpc_read_only_adapter(
    const HistoricalGrpcReadOnlyEndpoint<In, Out>& f)
  {
    return [f](
             ccf::endpoints::ReadOnlyEndpointContext& ctx,
             ccf::historical::StatePtr historical_state) {
      ccf::grpc::set_grpc_response(
        f(ctx, historical_state, ccf::grpc::get_grpc_payload<In>(ctx.rpc_ctx)),
        ctx.rpc_ctx);
    };
  }

}; // namespace app::grpc
