// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#include "ccf/app_interface.h"
#include "ccf/common_auth_policies.h"
#include "ccf/crypto/sha256.h"
#include "ccf/crypto/verifier.h"
#include "ccf/ds/hex.h"
#include "ccf/historical_queries_adapter.h"
#include "ccf/http_query.h"
#include "ccf/json_handler.h"
#include "ccf/service/tables/nodes.h"
#include "ccf/service/tables/service.h"
#include "endpoints/grpc.h" // TODO(#22): private header
#include "etcd.pb.h"
#include "grpc.h"
#include "index.h"
#include "json_grpc.h"
#include "kvstore.h"
#include "leases.h"
#include "lskvserver.pb.h"
#include "node_data.h"

#define FMT_HEADER_ONLY
#include <fmt/format.h>

#define SET_CUSTOM_CLAIMS(rpc) \
  { \
    CCF_APP_DEBUG("building custom claims for " #rpc); \
    lskvserverpb::ReceiptClaims claims; \
    auto* request_##rpc = claims.mutable_request_##rpc(); \
    *request_##rpc = payload; \
    auto* response_##rpc = claims.mutable_response_##rpc(); \
    *response_##rpc = rpc##_response; \
    CCF_APP_DEBUG("serializing custom claims for " #rpc); \
    auto claims_data = claims.SerializeAsString(); \
    CCF_APP_DEBUG("registering custom claims for " #rpc); \
    ctx.rpc_ctx->set_claims_digest(ccf::ClaimsDigest::Digest(claims_data)); \
  }

namespace app
{
  class AppHandlers : public ccf::UserEndpointRegistry
  {
  private:
    using IndexStrategy = app::index::KVIndexer;
    std::shared_ptr<IndexStrategy> kvindex = nullptr;

    int64_t cluster_id;

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
      const auto lskvserverpb = "lskvserverpb";
      const auto kv = "KV";
      const auto lease = "Lease";
      const auto cluster = "Cluster";
      const auto receipt = "Receipt";

      auto range = [this](
                     ccf::endpoints::ReadOnlyEndpointContext& ctx,
                     etcdserverpb::RangeRequest&& payload) {
        populate_cluster_id(ctx.tx);
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
        populate_cluster_id(ctx.tx);
        return this->put(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::PutRequest,
        etcdserverpb::PutResponse>(etcdserverpb, kv, "Put", "/v3/kv/put", put);

      auto delete_range = [this](
                            ccf::endpoints::EndpointContext& ctx,
                            etcdserverpb::DeleteRangeRequest&& payload) {
        populate_cluster_id(ctx.tx);
        return this->delete_range(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::DeleteRangeRequest,
        etcdserverpb::DeleteRangeResponse>(
        etcdserverpb, kv, "DeleteRange", "/v3/kv/delete_range", delete_range);

      auto txn = [this](
                   ccf::endpoints::EndpointContext& ctx,
                   etcdserverpb::TxnRequest&& payload) {
        populate_cluster_id(ctx.tx);
        return this->txn(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::TxnRequest,
        etcdserverpb::TxnResponse>(etcdserverpb, kv, "Txn", "/v3/kv/txn", txn);

      auto compact = [this](
                       ccf::endpoints::EndpointContext& ctx,
                       etcdserverpb::CompactionRequest&& payload) {
        populate_cluster_id(ctx.tx);
        return this->compact(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::CompactionRequest,
        etcdserverpb::CompactionResponse>(
        etcdserverpb, kv, "Compact", "/v3/kv/compact", compact);

      auto lease_grant = [this](
                           ccf::endpoints::EndpointContext& ctx,
                           etcdserverpb::LeaseGrantRequest&& payload) {
        populate_cluster_id(ctx.tx);
        return this->lease_grant(ctx, std::move(payload));
      };

      install_endpoint_with_header<
        etcdserverpb::LeaseGrantRequest,
        etcdserverpb::LeaseGrantResponse>(
        etcdserverpb, lease, "LeaseGrant", "/v3/lease/grant", lease_grant);

      auto lease_revoke = [this](
                            ccf::endpoints::EndpointContext& ctx,
                            etcdserverpb::LeaseRevokeRequest&& payload) {
        populate_cluster_id(ctx.tx);
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
          populate_cluster_id(ctx.tx);
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
        populate_cluster_id(ctx.tx);
        return this->lease_leases(ctx, std::move(payload));
      };

      install_endpoint_with_header_ro<
        etcdserverpb::LeaseLeasesRequest,
        etcdserverpb::LeaseLeasesResponse>(
        etcdserverpb, lease, "LeaseLeases", "/v3/lease/leases", lease_leases);

      auto lease_keep_alive = [this](
                                ccf::endpoints::EndpointContext& ctx,
                                etcdserverpb::LeaseKeepAliveRequest&& payload) {
        populate_cluster_id(ctx.tx);
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

      auto member_list = [this](
                           ccf::endpoints::ReadOnlyEndpointContext& ctx,
                           etcdserverpb::MemberListRequest&& payload) {
        return this->member_list(ctx, std::move(payload));
      };

      install_endpoint_with_header_ro<
        etcdserverpb::MemberListRequest,
        etcdserverpb::MemberListResponse>(
        etcdserverpb,
        cluster,
        "MemberList",
        "/v3/cluster/member/list",
        member_list);

      auto get_receipt = [this](
                           ccf::endpoints::ReadOnlyEndpointContext& ctx,
                           ccf::historical::StatePtr historical_state,
                           lskvserverpb::GetReceiptRequest&& payload) {
        assert(historical_state->receipt);
        lskvserverpb::GetReceiptResponse response;
        auto* receipt = response.mutable_receipt();
        ccf::ReceiptPtr receipt_ptr =
          ccf::describe_receipt_v2(*historical_state->receipt);
        receipt->set_cert(receipt_ptr->cert.str());
        receipt->set_signature(std::string(
          receipt_ptr->signature.begin(), receipt_ptr->signature.end()));
        receipt->set_node_id(receipt_ptr->node_id);
        if (receipt_ptr->is_signature_transaction())
        {
          auto sr =
            std::dynamic_pointer_cast<ccf::SignatureReceipt>(receipt_ptr);
          auto* sig_receipt = receipt->mutable_signature_receipt();

          sig_receipt->set_leaf(sr->signed_root.hex_str());
        }
        else
        {
          auto tr = std::dynamic_pointer_cast<ccf::ProofReceipt>(receipt_ptr);
          auto* tx_receipt = receipt->mutable_tx_receipt();

          auto* leaf_components = tx_receipt->mutable_leaf_components();
          // set the claims digest on the receipt so that the client can always
          // just validate the receipt itself, without checking it against the
          // original claims. clients that want to verify the claims themselves
          // can do so by checking the claims digest against the claims they
          // have and then verifying the receipt in full.
          leaf_components->set_claims_digest(
            tr->leaf_components.claims_digest.value().hex_str());
          leaf_components->set_commit_evidence(
            tr->leaf_components.commit_evidence);
          leaf_components->set_write_set_digest(
            tr->leaf_components.write_set_digest.hex_str());

          for (const auto& proof : tr->proof)
          {
            auto* proof_entry = tx_receipt->add_proof();
            if (proof.direction == ccf::ProofReceipt::ProofStep::Left)
            {
              proof_entry->set_left(proof.hash.hex_str());
            }
            else
            {
              proof_entry->set_right(proof.hash.hex_str());
            }
          }
        }

        populate_cluster_id(ctx.tx);

        auto* header = response.mutable_header();
        ccf::View view;
        ccf::SeqNo seqno;
        get_last_committed_txid_v1(view, seqno);
        ccf::TxID tx_id{view, seqno};
        fill_header(*header, tx_id);

        return ccf::grpc::make_success(response);
      };

      install_historical_endpoint_with_header_ro<
        lskvserverpb::GetReceiptRequest,
        lskvserverpb::GetReceiptResponse>(
        etcdserverpb,
        receipt,
        "GetReceipt",
        "/v3/receipt/get_receipt",
        get_receipt,
        context);
    }

    template <typename Out>
    ccf::grpc::GrpcAdapterResponse<Out>& post_commit(
      ccf::endpoints::CommandEndpointContext& ctx, const ccf::TxID& tx_id)
    {
      auto res = static_cast<ccf::grpc::GrpcAdapterResponse<Out>*>(
        ctx.rpc_ctx->get_user_data());
      if (res == nullptr)
      {
        throw std::runtime_error("user data was null");
      }
      if (auto success = std::get_if<ccf::grpc::SuccessResponse<Out>>(&*res))
      {
        auto* header = success->body.mutable_header();
        fill_header(*header, tx_id);
      } // else just leave the response
      return *res;
    }

    static ccf::AuthnPolicies auth_policies()
    {
      ccf::AuthnPolicies policies;
      policies.push_back(ccf::user_cert_auth_policy);
      return policies;
    }

    template <typename In, typename Out>
    void install_endpoint_with_header_ro(
      const std::string& package,
      const std::string& service,
      const std::string& rpc,
      const std::string& path,
      const ccf::GrpcReadOnlyEndpoint<In, Out>& f)
    {
      auto g = [f](ccf::endpoints::ReadOnlyEndpointContext& ctx, In&& payload) {
        auto res = f(ctx, std::move(payload));
        auto res_p = std::make_shared<ccf::grpc::GrpcAdapterResponse<Out>>(res);
        ctx.rpc_ctx->set_user_data(res_p);
      };
      auto grpc_path = fmt::format("/{}.{}/{}", package, service, rpc);
      make_read_only_endpoint_with_local_commit_handler(
        grpc_path,
        HTTP_POST,
        app::grpc::grpc_read_only_adapter_in_only<In>(g),
        [this](auto& ctx, const auto& tx_id) {
          auto res = post_commit<Out>(ctx, tx_id);
          ccf::grpc::set_grpc_response(res, ctx.rpc_ctx);
        },
        auth_policies())
        .install();
      make_read_only_endpoint_with_local_commit_handler(
        path,
        HTTP_POST,
        app::json_grpc::json_grpc_adapter_in_only_ro<In>(g),
        [this](auto& ctx, const auto& tx_id) {
          auto res = post_commit<Out>(ctx, tx_id);
          app::json_grpc::set_json_grpc_response(res, ctx.rpc_ctx);
        },
        auth_policies())
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
      auto g = [f](ccf::endpoints::EndpointContext& ctx, In&& payload) {
        auto res = f(ctx, std::move(payload));
        auto res_p = std::make_shared<ccf::grpc::GrpcAdapterResponse<Out>>(res);
        ctx.rpc_ctx->set_user_data(res_p);
      };
      auto grpc_path = fmt::format("/{}.{}/{}", package, service, rpc);
      make_endpoint_with_local_commit_handler(
        grpc_path,
        HTTP_POST,
        app::grpc::grpc_adapter_in_only<In>(g),
        [this](auto& ctx, const auto& tx_id) {
          auto res = post_commit<Out>(ctx, tx_id);
          ccf::grpc::set_grpc_response(res, ctx.rpc_ctx);
        },
        auth_policies())
        .install();
      make_endpoint_with_local_commit_handler(
        path,
        HTTP_POST,
        app::json_grpc::json_grpc_adapter_in_only<In>(g),
        [this](auto& ctx, const auto& tx_id) {
          auto res = post_commit<Out>(ctx, tx_id);
          app::json_grpc::set_json_grpc_response(res, ctx.rpc_ctx);
        },
        auth_policies())
        .install();
    }

    static ccf::TxID txid_from_body(lskvserverpb::GetReceiptRequest&& payload)
    {
      auto revision = static_cast<uint64_t>(payload.revision());
      return ccf::TxID{payload.raft_term(), revision};
    }

    template <typename In, typename Out>
    void install_historical_endpoint_with_header_ro(
      const std::string& package,
      const std::string& service,
      const std::string& rpc,
      const std::string& json_path,
      const app::grpc::HistoricalGrpcReadOnlyEndpoint<In, Out>& f,
      ccfapp::AbstractNodeContext& context)
    {
      auto grpc_path = fmt::format("/{}.{}/{}", package, service, rpc);
      auto is_tx_committed =
        [this](ccf::View view, ccf::SeqNo seqno, std::string& error_reason) {
          return ccf::historical::is_tx_committed_v2(
            consensus, view, seqno, error_reason);
        };
      make_read_only_endpoint(
        grpc_path,
        HTTP_POST,
        ccf::historical::read_only_adapter_v3(
          app::grpc::historical_grpc_read_only_adapter<In>(f),
          context,
          is_tx_committed,
          [](ccf::endpoints::ReadOnlyEndpointContext& ctx) {
            return txid_from_body(ccf::grpc::get_grpc_payload<In>(ctx.rpc_ctx));
          }),
        auth_policies())
        .set_forwarding_required(ccf::endpoints::ForwardingRequired::Never)
        .install();
      make_read_only_endpoint(
        json_path,
        HTTP_POST,
        ccf::historical::read_only_adapter_v3(
          app::json_grpc::historical_json_grpc_adapter<In>(f),
          context,
          is_tx_committed,
          [](ccf::endpoints::ReadOnlyEndpointContext& ctx) {
            return txid_from_body(
              app::json_grpc::get_json_grpc_payload<In>(ctx.rpc_ctx));
          }),
        auth_policies())
        .set_forwarding_required(ccf::endpoints::ForwardingRequired::Never)
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

      SET_CUSTOM_CLAIMS(put)

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

      SET_CUSTOM_CLAIMS(delete_range)

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

      SET_CUSTOM_CLAIMS(txn)

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
      if (ttl == 0)
      {
        return ccf::grpc::make_error(
          GRPC_STATUS_NOT_FOUND,
          fmt::format(
            "the lease with the given id '{}' has expired or has been revoked",
            id));
      }

      response.set_id(id);
      response.set_ttl(ttl);

      return ccf::grpc::make_success(response);
    }

    static std::string net_interface_to_url(
      const ccf::NodeInfo::NetInterface& netint)
    {
      return fmt::format("https://{}", netint.published_address);
    }

    ccf::grpc::GrpcAdapterResponse<etcdserverpb::MemberListResponse>
    member_list(
      ccf::endpoints::ReadOnlyEndpointContext& ctx,
      etcdserverpb::MemberListRequest&& payload)
    {
      etcdserverpb::MemberListResponse response;
      CCF_APP_DEBUG("MEMBER LIST");

      auto ccf_governance_map_nodes =
        ctx.tx.template ro<ccf::Nodes>(ccf::Tables::NODES);

      std::map<std::string, etcdserverpb::Member> nodes;
      ccf_governance_map_nodes->foreach(
        [&response](const auto& nid, const auto& n) {
          auto* m = response.add_members();
          m->set_id(node_id_to_member_id(nid));

          auto peer_interface = n.node_to_node_interface;
          auto* peer_url = m->add_peerurls();
          *peer_url = net_interface_to_url(peer_interface);

          for (auto& client_interface : n.rpc_interfaces)
          {
            auto* client_url = m->add_clienturls();
            *client_url = net_interface_to_url(client_interface.second);
          }

          try
          {
            nlohmann::json node_data_js = n.node_data;
            app::nodes::NodeData node_data =
              node_data_js.get<app::nodes::NodeData>();

            m->set_name(node_data.name);
          }
          catch (const JsonParseError& e)
          {
            m->set_name("default");
            CCF_APP_FAIL(
              "failed to convert node data json to struct with name, peer_urls "
              "and client_urls (try setting node_data_json_file in the "
              "configuration for this node): {} at {}",
              e.what(),
              e.pointer());
          }

          m->set_islearner(false);

          return true;
        });

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

    void fill_header(
      etcdserverpb::ResponseHeader& header, const ccf::TxID& tx_id)
    {
      header.set_cluster_id(cluster_id);
      header.set_member_id(member_id());
      header.set_revision(tx_id.seqno);
      header.set_raft_term(tx_id.view);
      ccf::View committed_view;
      ccf::SeqNo committed_seqno;
      auto res = get_last_committed_txid_v1(committed_view, committed_seqno);
      if (res == ccf::ApiResult::OK)
      {
        header.set_committed_revision(committed_seqno);
        header.set_committed_raft_term(committed_view);
      }
      else
      {
        CCF_APP_FAIL("failed to get last committed txid: {}", res);
      }
    }

    void populate_cluster_id(kv::ReadOnlyTx& tx)
    {
      cluster_id = get_cluster_id(tx);
    }

    int64_t get_cluster_id(kv::ReadOnlyTx& tx)
    {
      auto ccf_governance_map =
        tx.template ro<ccf::Service>(ccf::Tables::SERVICE);
      auto service_info = ccf_governance_map->get();

      if (!service_info.has_value())
      {
        // shouldn't but just in case
        CCF_APP_FAIL("Failed to get id for cluster");
        return 0;
      }

      auto cert = service_info.value().cert;
      auto public_key = crypto::make_verifier(cert)->public_key_der();
      auto sha = crypto::sha256(public_key);

      // take first few bytes (like node id)
      // and convert those 8 bytes to the int64_t
      return bytes_to_int64_t(sha);
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

      return node_id_to_member_id(node_id);
    }

    static int64_t node_id_to_member_id(const ccf::NodeId& node_id)
    {
      // it is a hex encoded string by default so unhex it
      auto bytes = ds::from_hex(node_id.value());

      // and convert the first 8 bytes to the int64_t
      return bytes_to_int64_t(bytes);
    }

    static int64_t bytes_to_int64_t(std::vector<uint8_t> bytes)
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
