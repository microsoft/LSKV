// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#define VERBOSE_LOGGING

#include "ccf/app_interface.h"
#include "ccf/common_auth_policies.h"
#include "ccf/ds/hex.h"
#include "ccf/http_query.h"
#include "ccf/json_handler.h"
#include "endpoints/grpc.h" // TODO(#22): private header
#include "etcd.pb.h"
#include "index.h"
#include "json_grpc.h"
#include "kvstore.h"
#include "leases.h"

#define FMT_HEADER_ONLY
#include <fmt/format.h>

namespace app
{
  class AppHandlers : public ccf::UserEndpointRegistry
  {
  private:
    using IndexStrategy = app::index::KVIndexer;
    std::shared_ptr<IndexStrategy> kvindex = nullptr;

  public:
    explicit AppHandlers(ccfapp::AbstractNodeContext& context) :
      ccf::UserEndpointRegistry(context)
    {
      openapi_info.title = "CCF Sample C++ Key-Value Store";
      openapi_info.description = "Sample Key-Value store built on CCF";
      openapi_info.document_version = "0.0.1";

      kvindex = std::make_shared<IndexStrategy>(app::kvstore::RECORDS);
      context.get_indexing_strategies().install_strategy(kvindex);

      const auto etcdserverpb = "etcdserverpb";
      const auto kv = "KV";
      const auto lease = "Lease";

      auto range = [this](
                     ccf::endpoints::ReadOnlyEndpointContext& ctx,
                     etcdserverpb::RangeRequest&& payload) {
        auto kvs = kvstore::KVStore(ctx.tx);
        auto lstore = leasestore::ReadOnlyLeaseStore(ctx.tx);
        return this->range(kvs, lstore, std::move(payload));
      };

      install_endpoint_with_header_ro<
        etcdserverpb::RangeRequest,
        etcdserverpb::RangeResponse>(
        etcdserverpb, kv, "Range", "/v3/kv/range", range);

      auto put = [this](
                   ccf::endpoints::EndpointContext& ctx,
                   etcdserverpb::PutRequest&& payload) {
        return this->put(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::PutRequest,
        etcdserverpb::PutResponse>(etcdserverpb, kv, "Put", "/v3/kv/put", put);

      auto delete_range = [this](
                            ccf::endpoints::EndpointContext& ctx,
                            etcdserverpb::DeleteRangeRequest&& payload) {
        return this->delete_range(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::DeleteRangeRequest,
        etcdserverpb::DeleteRangeResponse>(
        etcdserverpb, kv, "DeleteRange", "/v3/kv/delete_range", delete_range);

      auto txn = [this](
                   ccf::endpoints::EndpointContext& ctx,
                   etcdserverpb::TxnRequest&& payload) {
        return this->txn(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::TxnRequest,
        etcdserverpb::TxnResponse>(etcdserverpb, kv, "Txn", "/v3/kv/txn", txn);

      auto compact = [this](
                       ccf::endpoints::EndpointContext& ctx,
                       etcdserverpb::CompactionRequest&& payload) {
        return this->compact(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::CompactionRequest,
        etcdserverpb::CompactionResponse>(
        etcdserverpb, kv, "Compact", "/v3/kv/compact", compact);

      auto lease_grant = [this](
                           ccf::endpoints::EndpointContext& ctx,
                           etcdserverpb::LeaseGrantRequest&& payload) {
        return this->lease_grant(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::LeaseGrantRequest,
        etcdserverpb::LeaseGrantResponse>(
        etcdserverpb, lease, "LeaseGrant", "/v3/lease/grant", lease_grant);

      auto lease_revoke = [this](
                            ccf::endpoints::EndpointContext& ctx,
                            etcdserverpb::LeaseRevokeRequest&& payload) {
        return this->lease_revoke(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::LeaseRevokeRequest,
        etcdserverpb::LeaseRevokeResponse>(
        etcdserverpb, lease, "LeaseRevoke", "/v3/lease/revoke", lease_revoke);

      auto lease_time_to_live =
        [this](
          ccf::endpoints::ReadOnlyEndpointContext& ctx,
          etcdserverpb::LeaseTimeToLiveRequest&& payload) {
          return this->lease_time_to_live(ctx, std::move(payload));
        };

      install_endpoint_with_header_ro<
        etcdserverpb::LeaseTimeToLiveRequest,
        etcdserverpb::LeaseTimeToLiveResponse>(
        etcdserverpb,
        lease,
        "LeaseTimeToLive",
        "/v3/lease/timetolive",
        lease_time_to_live);

      auto lease_leases = [this](
                            ccf::endpoints::ReadOnlyEndpointContext& ctx,
                            etcdserverpb::LeaseLeasesRequest&& payload) {
        return this->lease_leases(ctx, std::move(payload));
      };

      install_endpoint_with_header_ro<
        etcdserverpb::LeaseLeasesRequest,
        etcdserverpb::LeaseLeasesResponse>(
        etcdserverpb, lease, "LeaseLeases", "/v3/lease/leases", lease_leases);

      auto lease_keep_alive = [this](
                                ccf::endpoints::EndpointContext& ctx,
                                etcdserverpb::LeaseKeepAliveRequest&& payload) {
        return this->lease_keep_alive(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::LeaseKeepAliveRequest,
        etcdserverpb::LeaseKeepAliveResponse>(
        etcdserverpb,
        lease,
        "LeaseKeepAlive",
        "/v3/lease/keepalive",
        lease_keep_alive);
    }

    template <typename In, typename Out>
    void install_endpoint_with_header_ro(
      const std::string& package,
      const std::string& service,
      const std::string& rpc,
      const std::string& path,
      const ccf::GrpcReadOnlyEndpoint<In, Out>& f)
    {
      auto grpc_path = fmt::format("/{}.{}/{}", package, service, rpc);
      make_read_only_endpoint_with_local_commit_handler(
        grpc_path,
        HTTP_POST,
        ccf::grpc_read_only_adapter<In, Out>([f](auto& ctx, In&& payload) {
          auto res = f(ctx, std::move(payload));
          auto res_p =
            std::make_shared<ccf::grpc::GrpcAdapterResponse<Out>>(res);
          ctx.rpc_ctx->set_user_data(res_p);
          return res;
        }),
        [this](auto& ctx, const auto& tx_id) {
          auto res = static_cast<ccf::grpc::GrpcAdapterResponse<Out>*>(
            ctx.rpc_ctx->get_user_data());
          if (res == nullptr)
          {
            throw std::runtime_error("user data was null");
          }
          if (
            auto success = std::get_if<ccf::grpc::SuccessResponse<Out>>(&*res))
          {
            auto* header = success->body.mutable_header();
            fill_header(*header);
          } // else just leave the response
          ccf::grpc::set_grpc_response(*res, ctx.rpc_ctx);
        },
        ccf::no_auth_required)
        .install();
      make_read_only_endpoint_with_local_commit_handler(
        path,
        HTTP_POST,
        app::json_grpc::json_grpc_adapter_in_only_ro<In>(
          [f](auto& ctx, In&& payload) {
            auto res = f(ctx, std::move(payload));
            auto res_p =
              std::make_shared<ccf::grpc::GrpcAdapterResponse<Out>>(res);
            ctx.rpc_ctx->set_user_data(res_p);
          }),
        [this](auto& ctx, const auto& tx_id) {
          auto res = static_cast<ccf::grpc::GrpcAdapterResponse<Out>*>(
            ctx.rpc_ctx->get_user_data());
          if (res == nullptr)
          {
            throw std::runtime_error("user data was null");
          }
          if (
            auto success = std::get_if<ccf::grpc::SuccessResponse<Out>>(&*res))
          {
            auto* header = success->body.mutable_header();
            fill_header(*header);
          } // else just leave the response
          app::json_grpc::set_json_grpc_response(*res, ctx.rpc_ctx);
        },
        ccf::no_auth_required)
        .install();
    }

    template <typename In, typename Out>
    void install_endpoint_with_header(
      const std::string& package,
      const std::string& service,
      const std::string& rpc,
      const std::string& path,
      const ccf::GrpcEndpoint<In, Out>& f)
    {
      auto grpc_path = fmt::format("/{}.{}/{}", package, service, rpc);
      make_endpoint_with_local_commit_handler(
        grpc_path,
        HTTP_POST,
        ccf::grpc_adapter<In, Out>([f](auto& ctx, In&& payload) {
          auto res = f(ctx, std::move(payload));
          auto res_p =
            std::make_shared<ccf::grpc::GrpcAdapterResponse<Out>>(res);
          ctx.rpc_ctx->set_user_data(res_p);
          return res;
        }),
        [this](auto& ctx, const auto& tx_id) {
          auto res = static_cast<ccf::grpc::GrpcAdapterResponse<Out>*>(
            ctx.rpc_ctx->get_user_data());
          if (res == nullptr)
          {
            throw std::runtime_error("user data was null");
          }
          if (
            auto success = std::get_if<ccf::grpc::SuccessResponse<Out>>(&*res))
          {
            auto* header = success->body.mutable_header();
            fill_header(*header);
          } // else just leave the response
          ccf::grpc::set_grpc_response(*res, ctx.rpc_ctx);
        },
        ccf::no_auth_required)
        .install();
      make_endpoint_with_local_commit_handler(
        path,
        HTTP_POST,
        app::json_grpc::json_grpc_adapter_in_only<In>(
          [f](auto& ctx, In&& payload) {
            auto res = f(ctx, std::move(payload));
            auto res_p =
              std::make_shared<ccf::grpc::GrpcAdapterResponse<Out>>(res);
            ctx.rpc_ctx->set_user_data(res_p);
          }),
        [this](auto& ctx, const auto& tx_id) {
          auto res = static_cast<ccf::grpc::GrpcAdapterResponse<Out>*>(
            ctx.rpc_ctx->get_user_data());
          if (res == nullptr)
          {
            throw std::runtime_error("user data was null");
          }
          if (
            auto success = std::get_if<ccf::grpc::SuccessResponse<Out>>(&*res))
          {
            auto* header = success->body.mutable_header();
            fill_header(*header);
          } // else just leave the response
          app::json_grpc::set_json_grpc_response(*res, ctx.rpc_ctx);
        },
        ccf::no_auth_required)
        .install();
    }

    ccf::grpc::GrpcAdapterResponse<etcdserverpb::RangeResponse> range(
      kvstore::KVStore records_map,
      leasestore::ReadOnlyLeaseStore lstore,
      etcdserverpb::RangeRequest&& payload)
    {
      etcdserverpb::RangeResponse range_response;
      CCF_APP_DEBUG(
        "Range = [{}]{}:[{}]{}",
        payload.key().size(),
        payload.key(),
        payload.range_end().size(),
        payload.range_end());

      if (payload.limit() != 0)
      {
        return ccf::grpc::make_error<etcdserverpb::RangeResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format("limit {} not yet supported", payload.limit()));
      }
      if (payload.sort_order() != etcdserverpb::RangeRequest_SortOrder_NONE)
      {
        return ccf::grpc::make_error<etcdserverpb::RangeResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format("sort order {} not yet supported", payload.sort_order()));
      }
      if (payload.keys_only())
      {
        return ccf::grpc::make_error<etcdserverpb::RangeResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format("keys only not yet supported"));
      }
      if (payload.count_only())
      {
        return ccf::grpc::make_error<etcdserverpb::RangeResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format("count only not yet supported"));
      }
      if (payload.min_mod_revision() != 0)
      {
        return ccf::grpc::make_error<etcdserverpb::RangeResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format(
            "min mod revision {} not yet supported",
            payload.min_mod_revision()));
      }
      if (payload.max_mod_revision() != 0)
      {
        return ccf::grpc::make_error<etcdserverpb::RangeResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format(
            "max mod revision {} not yet supported",
            payload.max_mod_revision()));
      }
      if (payload.min_create_revision() != 0)
      {
        return ccf::grpc::make_error<etcdserverpb::RangeResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format(
            "min create revision {} not yet supported",
            payload.min_create_revision()));
      }
      if (payload.max_create_revision() != 0)
      {
        return ccf::grpc::make_error<etcdserverpb::RangeResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format(
            "max create revision {} not yet supported",
            payload.max_create_revision()));
      }

      auto count = 0;
      auto now_s = get_time_s();
      auto add_kv = [&](auto& key, auto& value) {
        // check that the lease for this value has not expired
        // NOTE: contains checks the expiration of the lease too.
        if (value.lease != 0 && !lstore.contains(value.lease, now_s))
        {
          // it had a lease and that lease is no longer (logically) in the store
          // we can't remove it since this is a read-only endpoint but we can
          // mimick the behaviour
          CCF_APP_DEBUG(
            "filtering out kv from range return as lease {} is missing or "
            "expired",
            value.lease);
          return;
        }

        count++;

        // add the kv to the response
        auto* kv = range_response.add_kvs();
        kv->set_key(key);
        kv->set_value(value.get_data());
        kv->set_create_revision(value.create_revision);
        kv->set_mod_revision(value.mod_revision);
        kv->set_version(value.version);
        kv->set_lease(value.lease);
      };

      if (payload.range_end().empty())
      {
        // empty range end so just query for a single key
        std::optional<app::kvstore::KVStore::V> value_option;
        if (payload.revision() > 0)
        {
          // historical, use the index of commited values
          value_option = kvindex->get(payload.revision(), payload.key());
        }
        else
        {
          // current, use the local map
          value_option = records_map.get(payload.key());
        }

        if (value_option.has_value())
        {
          add_kv(payload.key(), value_option.value());
        }
      }
      else
      {
        auto end = std::make_optional(payload.range_end());
        // If range_end is '\0', the range is all keys greater than or equal
        // to the key argument.
        if (*end == std::string(1, '\0'))
        {
          CCF_APP_DEBUG("found empty end, making it work with range");
          // make sure we get all keys greater than the start
          end = std::nullopt;
        }

        // range end is non-empty so perform a range scan
        if (payload.revision() > 0)
        {
          // historical, use the index of commited values
          kvindex->range(payload.revision(), add_kv, payload.key(), end);
        }
        else
        {
          // current, use the local map
          records_map.range(add_kv, payload.key(), end);
        }
      }

      range_response.set_count(count);

      return ccf::grpc::make_success(range_response);
    }

    ccf::grpc::GrpcAdapterResponse<etcdserverpb::PutResponse> put(
      ccf::endpoints::EndpointContext& ctx, etcdserverpb::PutRequest&& payload)
    {
      etcdserverpb::PutResponse put_response;
      CCF_APP_DEBUG(
        "Put = [{}]{}:[{}]{} lease:{}",
        payload.key().size(),
        payload.key(),
        payload.value().size(),
        payload.value(),
        payload.lease());

      if (payload.ignore_value())
      {
        return ccf::grpc::make_error<etcdserverpb::PutResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format("ignore value not yet supported"));
      }
      if (payload.ignore_lease())
      {
        return ccf::grpc::make_error<etcdserverpb::PutResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format("ignore lease not yet supported"));
      }

      auto now_s = get_time_s();

      auto lease = payload.lease();
      if (lease != 0)
      {
        // check lease exists, error if missing
        auto lstore = leasestore::LeaseStore(ctx.tx);
        auto exists = lstore.contains(lease, now_s);
        if (!exists)
        {
          return ccf::grpc::make_error<etcdserverpb::PutResponse>(
            GRPC_STATUS_FAILED_PRECONDITION,
            fmt::format(
              "invalid lease {}: hasn't been granted or has expired", lease));
        }
        // continue with normal flow, recording the lease in the kvstore
      }

      auto records_map = kvstore::KVStore(ctx.tx);

      auto old =
        records_map.put(payload.key(), kvstore::Value(payload.value(), lease));
      if (payload.prev_kv() && old.has_value())
      {
        auto* prev_kv = put_response.mutable_prev_kv();
        auto& value = old.value();
        prev_kv->set_key(payload.key());
        prev_kv->set_value(value.get_data());
        prev_kv->set_create_revision(value.create_revision);
        prev_kv->set_mod_revision(value.mod_revision);
        prev_kv->set_version(value.version);
        prev_kv->set_lease(value.lease);
      }

      return ccf::grpc::make_success(put_response);
    }

    ccf::grpc::GrpcAdapterResponse<etcdserverpb::DeleteRangeResponse>
    delete_range(
      ccf::endpoints::EndpointContext& ctx,
      etcdserverpb::DeleteRangeRequest&& payload)
    {
      CCF_APP_DEBUG(
        "DeleteRange = [{}]{} -> [{}]{} prevkv:{}",
        payload.key().size(),
        payload.key(),
        payload.range_end().size(),
        payload.range_end(),
        payload.prev_kv());
      etcdserverpb::DeleteRangeResponse delete_range_response;

      auto records_map = kvstore::KVStore(ctx.tx);
      auto& key = payload.key();

      if (payload.range_end().empty())
      {
        // just delete a single key

        // try to get the current value, if there isn't one then skip,
        // otherwise remove it and maybe plug the old value in to the
        // response.

        auto old_option = records_map.remove(key);
        if (old_option.has_value())
        {
          delete_range_response.set_deleted(1);

          if (payload.prev_kv())
          {
            auto* prev_kv = delete_range_response.add_prev_kvs();
            prev_kv->set_key(payload.key());
            auto old_value = old_option.value();
            prev_kv->set_value(old_value.get_data());
            prev_kv->set_create_revision(old_value.create_revision);
            prev_kv->set_mod_revision(old_value.mod_revision);
            prev_kv->set_version(old_value.version);
          }
        }
      }
      else
      {
        // operating over a range
        // find the keys to delete and remove them after collecting them

        auto deleted = 0;

        auto& start = payload.key();
        auto end = std::make_optional(payload.range_end());

        // If range_end is '\0', the range is all keys greater than or equal
        // to the key argument.
        if (*end == std::string(1, '\0'))
        {
          CCF_APP_DEBUG("found empty end, making it work with range");
          // make sure we get all keys greater than the start
          end = std::nullopt;
        }

        if (end.has_value())
        {
          CCF_APP_DEBUG(
            "calling range for deletion with [{}]{} -> [{}]{}",
            start.size(),
            start,
            end.value().size(),
            end.value());
        }
        else
        {
          CCF_APP_DEBUG(
            "calling range for deletion with [{}]{} to the end",
            start.size(),
            start);
        }
        records_map.range(
          [&](auto& key, auto& old) {
            records_map.remove(key);
            deleted++;

            if (payload.prev_kv())
            {
              auto* prev_kv = delete_range_response.add_prev_kvs();

              prev_kv->set_key(key);
              prev_kv->set_value(old.get_data());
              prev_kv->set_create_revision(old.create_revision);
              prev_kv->set_mod_revision(old.mod_revision);
              prev_kv->set_version(old.version);
            }
          },
          start,
          end);

        delete_range_response.set_deleted(deleted);
      }

      return ccf::grpc::make_success(delete_range_response);
    }

    ccf::grpc::GrpcAdapterResponse<etcdserverpb::TxnResponse> txn(
      ccf::endpoints::EndpointContext& ctx, etcdserverpb::TxnRequest&& payload)
    {
      CCF_APP_DEBUG(
        "Txn = compare:{} success:{} failure:{}",
        payload.compare().size(),
        payload.success().size(),
        payload.failure().size());

      bool success = true;
      auto records_map = kvstore::KVStore(ctx.tx);
      auto lstore = leasestore::ReadOnlyLeaseStore(ctx.tx);
      // evaluate each comparison in the transaction and report the success
      for (auto const& cmp : payload.compare())
      {
        CCF_APP_DEBUG(
          "Cmp = [{}]{}:[{}]{}",
          cmp.key().size(),
          cmp.key(),
          cmp.range_end().size(),
          cmp.range_end());

        if (!cmp.range_end().empty())
        {
          return ccf::grpc::make_error(
            GRPC_STATUS_FAILED_PRECONDITION,
            fmt::format("range_end in comparison not yet supported"));
        }

        // fetch the key from the store
        auto key = cmp.key();
        auto value_option = records_map.get(key);
        // get the value if there was one, otherwise use a default entry to
        // compare against
        auto value = value_option.value_or(kvstore::Value());

        // got the key to check against, now do the check
        std::optional<bool> outcome = std::nullopt;
        if (
          cmp.target() == etcdserverpb::Compare_CompareTarget_VALUE &&
          cmp.has_value())
        {
          outcome = txn_compare(cmp.result(), value.get_data(), cmp.value());
        }
        else if (
          cmp.target() == etcdserverpb::Compare_CompareTarget_VERSION &&
          cmp.has_version())
        {
          outcome = txn_compare(cmp.result(), value.version, cmp.version());
        }
        else if (
          cmp.target() == etcdserverpb::Compare_CompareTarget_CREATE &&
          cmp.has_create_revision())
        {
          outcome = txn_compare(
            cmp.result(), value.create_revision, cmp.create_revision());
        }
        else if (
          cmp.target() == etcdserverpb::Compare_CompareTarget_MOD &&
          cmp.has_mod_revision())
        {
          outcome =
            txn_compare(cmp.result(), value.mod_revision, cmp.mod_revision());
        }
        else if (
          cmp.target() == etcdserverpb::Compare_CompareTarget_LEASE &&
          cmp.has_lease())
        {
          outcome = txn_compare(cmp.result(), value.lease, cmp.lease());
        }
        else
        {
          return ccf::grpc::make_error<etcdserverpb::TxnResponse>(
            GRPC_STATUS_INVALID_ARGUMENT,
            fmt::format("unknown target in comparison: {}", cmp.target()));
        }

        if (!outcome.has_value())
        {
          return ccf::grpc::make_error<etcdserverpb::TxnResponse>(
            GRPC_STATUS_INVALID_ARGUMENT,
            fmt::format("unknown result in comparison: {}", cmp.result()));
        }

        success = success && outcome.value();
      }

      etcdserverpb::TxnResponse txn_response;

      txn_response.set_succeeded(success);
      google::protobuf::RepeatedPtrField<etcdserverpb::RequestOp> requests;
      if (success)
      {
        requests = payload.success();
      }
      else
      {
        requests = payload.failure();
      }

      for (auto const& req : requests)
      {
        if (req.has_request_range())
        {
          auto request = req.request_range();
          auto response = range(records_map, lstore, std::move(request));
          auto success_response = std::get_if<
            ccf::grpc::SuccessResponse<etcdserverpb::RangeResponse>>(&response);
          if (success_response == nullptr)
          {
            return std::get<ccf::grpc::ErrorResponse>(response);
          }
          auto* resp_op = txn_response.add_responses();
          auto* resp = resp_op->mutable_response_range();
          *resp = success_response->body;
        }
        else if (req.has_request_put())
        {
          auto request = req.request_put();
          auto response = put(ctx, std::move(request));
          auto success_response =
            std::get_if<ccf::grpc::SuccessResponse<etcdserverpb::PutResponse>>(
              &response);
          if (success_response == nullptr)
          {
            return std::get<ccf::grpc::ErrorResponse>(response);
          }
          auto* resp_op = txn_response.add_responses();
          auto* resp = resp_op->mutable_response_put();
          *resp = success_response->body;
        }
        else if (req.has_request_delete_range())
        {
          auto request = req.request_delete_range();
          auto response = delete_range(ctx, std::move(request));
          auto success_response = std::get_if<
            ccf::grpc::SuccessResponse<etcdserverpb::DeleteRangeResponse>>(
            &response);
          if (success_response == nullptr)
          {
            return std::get<ccf::grpc::ErrorResponse>(response);
          }
          auto* resp_op = txn_response.add_responses();
          auto* resp = resp_op->mutable_response_delete_range();
          *resp = success_response->body;
        }
        else if (req.has_request_txn())
        {
          auto request = req.request_txn();
          auto response = txn(ctx, std::move(request));
          auto success_response =
            std::get_if<ccf::grpc::SuccessResponse<etcdserverpb::TxnResponse>>(
              &response);
          if (success_response == nullptr)
          {
            return std::get<ccf::grpc::ErrorResponse>(response);
          }
          auto* resp_op = txn_response.add_responses();
          auto* resp = resp_op->mutable_response_txn();
          *resp = success_response->body;
        }
        else
        {
          return ccf::grpc::make_error<etcdserverpb::TxnResponse>(
            GRPC_STATUS_INVALID_ARGUMENT, "unknown request op");
        }
      }

      return ccf::grpc::make_success(txn_response);
    }

    /// @brief Compare a stored value with the given target using the result
    /// operator.
    /// @tparam T the type of the values to compare
    /// @param result the method to compare them with
    /// @param stored the stored value to compare
    /// @param target the given value to use in comparison
    /// @return nullopt if the result is invalid, true if the result is valid
    /// and the comparison succeeds, false if the result is valid and the
    /// comparison fails
    template <typename T>
    static std::optional<bool> txn_compare(
      etcdserverpb::Compare_CompareResult result,
      const T stored,
      const T target)
    {
      if (result == etcdserverpb::Compare_CompareResult_EQUAL)
      {
        return stored == target;
      }
      else if (result == etcdserverpb::Compare_CompareResult_GREATER)
      {
        return stored > target;
      }
      else if (result == etcdserverpb::Compare_CompareResult_LESS)
      {
        return stored < target;
      }
      else if (result == etcdserverpb::Compare_CompareResult_NOT_EQUAL)
      {
        return stored != target;
      }
      else
      {
        return std::nullopt;
      }
    }

    ccf::grpc::GrpcAdapterResponse<etcdserverpb::CompactionResponse> compact(
      ccf::endpoints::EndpointContext& ctx,
      etcdserverpb::CompactionRequest&& payload)
    {
      CCF_APP_DEBUG(
        "COMPACT = revision:{} physical:{}",
        payload.revision(),
        payload.physical());

      if (payload.physical())
      {
        return ccf::grpc::make_error(
          GRPC_STATUS_FAILED_PRECONDITION, "physical is not yet supported");
      }

      etcdserverpb::CompactionResponse response;

      revoke_expired_leases(ctx.tx);
      kvindex->compact(payload.revision());

      return ccf::grpc::make_success(response);
    }

    ccf::grpc::GrpcAdapterResponse<etcdserverpb::LeaseGrantResponse>
    lease_grant(
      ccf::endpoints::EndpointContext& ctx,
      etcdserverpb::LeaseGrantRequest&& payload)
    {
      etcdserverpb::LeaseGrantResponse response;
      CCF_APP_DEBUG("LEASE GRANT = {} {}", payload.id(), payload.ttl());

      auto now_s = get_time_s();

      auto lstore = leasestore::LeaseStore(ctx.tx);
      auto res = lstore.grant(payload.ttl(), now_s);

      auto id = res.first;
      auto ttl = res.second.ttl;

      CCF_APP_DEBUG("granted lease with id {} and ttl {}", id, ttl);

      response.set_id(id);
      response.set_ttl(ttl);

      return ccf::grpc::make_success(response);
    }

    ccf::grpc::GrpcAdapterResponse<etcdserverpb::LeaseRevokeResponse>
    lease_revoke(
      ccf::endpoints::EndpointContext& ctx,
      etcdserverpb::LeaseRevokeRequest&& payload)
    {
      etcdserverpb::LeaseRevokeResponse response;
      auto id = payload.id();
      CCF_APP_DEBUG("LEASE REVOKE = {}", id);

      auto lstore = leasestore::LeaseStore(ctx.tx);
      lstore.revoke(id);

      auto kvs = kvstore::KVStore(ctx.tx);
      kvs.foreach([&id, &kvs](auto key, auto value) {
        if (value.lease == id)
        {
          // remove this key
          CCF_APP_DEBUG(
            "removing key due to revoke lease {}: {}", value.lease, key);
          kvs.remove(key);
        }
        return true;
      });

      return ccf::grpc::make_success(response);
    }

    ccf::grpc::GrpcAdapterResponse<etcdserverpb::LeaseTimeToLiveResponse>
    lease_time_to_live(
      ccf::endpoints::ReadOnlyEndpointContext& ctx,
      etcdserverpb::LeaseTimeToLiveRequest&& payload)
    {
      etcdserverpb::LeaseTimeToLiveResponse response;
      auto id = payload.id();
      CCF_APP_DEBUG("LEASE TIMETOLIVE = {}", id);

      if (payload.keys())
      {
        return ccf::grpc::make_error(
          GRPC_STATUS_FAILED_PRECONDITION, "keys is not yet supported");
      }

      auto now_s = get_time_s();
      auto lstore = leasestore::ReadOnlyLeaseStore(ctx.tx);

      auto lease = lstore.get(id, now_s);

      response.set_id(id);
      response.set_ttl(lease.ttl_remaining(now_s));
      response.set_grantedttl(lease.ttl);

      return ccf::grpc::make_success(response);
    }

    ccf::grpc::GrpcAdapterResponse<etcdserverpb::LeaseLeasesResponse>
    lease_leases(
      ccf::endpoints::ReadOnlyEndpointContext& ctx,
      etcdserverpb::LeaseLeasesRequest&& payload)
    {
      etcdserverpb::LeaseLeasesResponse response;
      CCF_APP_DEBUG("LEASE LEASES");

      auto now_s = get_time_s();
      auto lstore = leasestore::ReadOnlyLeaseStore(ctx.tx);

      lstore.foreach([&response, &now_s](auto id, auto lease) {
        if (!lease.has_expired(now_s))
        {
          auto* lease = response.add_leases();
          lease->set_id(id);
        }
        return true;
      });

      return ccf::grpc::make_success(response);
    }

    ccf::grpc::GrpcAdapterResponse<etcdserverpb::LeaseKeepAliveResponse>
    lease_keep_alive(
      ccf::endpoints::EndpointContext& ctx,
      etcdserverpb::LeaseKeepAliveRequest&& payload)
    {
      etcdserverpb::LeaseKeepAliveResponse response;
      auto id = payload.id();
      CCF_APP_DEBUG("LEASE KEEPALIVE = {}", id);

      auto now_s = get_time_s();
      auto lstore = leasestore::LeaseStore(ctx.tx);
      auto ttl = lstore.keep_alive(id, now_s);

      response.set_id(id);
      response.set_ttl(ttl);

      return ccf::grpc::make_success(response);
    }

    void revoke_expired_leases(kv::Tx& tx)
    {
      CCF_APP_DEBUG("revoking any expired leases");
      std::set<int64_t> expired_leases;

      auto now_s = get_time_s();
      auto lstore = leasestore::LeaseStore(tx);

      // go through all leases in the leasestore
      lstore.foreach([&expired_leases, &lstore, &now_s](auto id, auto lease) {
        if (lease.has_expired(now_s))
        {
          // if the lease has expired then revoke it in the lease store (remove
          // the entry)
          CCF_APP_DEBUG("found expired lease {}", id);
          expired_leases.insert(id);
          lstore.revoke(id);
        }
        return true;
      });

      // and remove all keys associated with it in the kvstore
      auto kvs = kvstore::KVStore(tx);
      kvs.foreach([&expired_leases, &kvs](auto key, auto value) {
        if (value.lease > 0 && expired_leases.contains(value.lease))
        {
          // remove this key
          CCF_APP_DEBUG(
            "removing key due to expired lease {}: {}", value.lease, key);
          kvs.remove(key);
        }
        return true;
      });

      CCF_APP_DEBUG("finished revoking leases");
    }

    int64_t get_time_s()
    {
      ::timespec time;
      get_untrusted_host_time_v1(time);
      return time.tv_sec;
    }

    void fill_header(etcdserverpb::ResponseHeader& header)
    {
      header.set_member_id(member_id());
    }

    int64_t member_id()
    {
      // get the node id
      ccf::NodeId node_id;
      auto result = get_id_for_this_node_v1(node_id);
      if (result != ccf::ApiResult::OK)
      {
        // leave the node_id as default value
        CCF_APP_FAIL(
          "Failed to get id for node: {}", ccf::api_result_to_str(result));
        return 0;
      }

      // it is a hex encoded string by default so unhex it
      auto bytes = ds::from_hex(node_id.value());

      // and convert the first 8 bytes to the int64_t
      return bytes_to_int64_t(bytes);
    }

    int64_t bytes_to_int64_t(std::vector<uint8_t> bytes)
    {
      int64_t out;
      // we don't care about endianness here, it will always be the same for
      // this machine.
      memcpy(&out, bytes.data(), sizeof out);
      return out;
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
