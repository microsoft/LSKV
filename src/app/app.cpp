// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#define VERBOSE_LOGGING

#include "ccf/app_interface.h"
#include "ccf/common_auth_policies.h"
#include "ccf/http_query.h"
#include "ccf/json_handler.h"
#include "etcd.pb.h"
#include "grpc.h" // TODO(#25): use grpc from ccf
#include "kv/untyped_map.h" // TODO(#22): private header

#define FMT_HEADER_ONLY
#include <fmt/format.h>

namespace app
{
  // Key-value store types

  // Use untyped map so we can access the range API.
  using Map = kv::untyped::Map;

  static constexpr auto RECORDS = "public:records";

  class AppHandlers : public ccf::UserEndpointRegistry
  {
  public:
    AppHandlers(ccfapp::AbstractNodeContext& context) :
      ccf::UserEndpointRegistry(context)
    {
      openapi_info.title = "CCF Sample C++ Key-Value Store";
      openapi_info.description = "Sample Key-Value store built on CCF";
      openapi_info.document_version = "0.0.1";

      const auto etcdserverpb = "etcdserverpb";
      const auto kv = "KV";

      make_grpc_ro<etcdserverpb::RangeRequest, etcdserverpb::RangeResponse>(
        etcdserverpb, kv, "Range", this->range, ccf::no_auth_required)
        .install();

      make_grpc<etcdserverpb::PutRequest, etcdserverpb::PutResponse>(
        etcdserverpb, kv, "Put", this->put, ccf::no_auth_required)
        .install();

      make_grpc<
        etcdserverpb::DeleteRangeRequest,
        etcdserverpb::DeleteRangeResponse>(
        etcdserverpb,
        kv,
        "DeleteRange",
        this->delete_range,
        ccf::no_auth_required)
        .install();
    }

    static ccf::grpc::GrpcAdapterResponse<etcdserverpb::RangeResponse> range(
      ccf::endpoints::ReadOnlyEndpointContext& ctx,
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
      if (payload.revision() > 0)
      {
        return ccf::grpc::make_error<etcdserverpb::RangeResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format(
            "revision {} not yet supported (no historical ranges)",
            payload.revision()));
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

      auto records_handle = ctx.tx.template ro<Map>(RECORDS);
      auto key = payload.key();
      auto range_end = payload.range_end();
      if (range_end.empty())
      {
        // empty range end so just query for a single key
        auto value_option =
          records_handle->get(ccf::ByteVector(key.begin(), key.end()));
        if (!value_option.has_value())
        {
          ctx.rpc_ctx->set_response_status(HTTP_STATUS_NOT_FOUND);
          range_response.set_count(0);
          return ccf::grpc::make_error<etcdserverpb::RangeResponse>(
            GRPC_STATUS_NOT_FOUND,
            fmt::format("Key {} not found", payload.key()));
        }

        auto* kv = range_response.add_kvs();
        kv->set_key(payload.key());
        auto value_bytes = value_option.value();
        auto value = std::string(value_bytes.begin(), value_bytes.end());
        kv->set_value(value);

        range_response.set_count(1);
      }
      else
      {
        // range end is non-empty so perform a range scan
        auto start = payload.key();
        auto start_bytes = ccf::ByteVector(start.begin(), start.end());
        auto end = payload.range_end();
        auto end_bytes = ccf::ByteVector(end.begin(), end.end());
        auto count = 0;

        records_handle->range(
          [&](auto& key_bytes, auto& value_bytes) {
            CCF_APP_DEBUG(
              "range over key {} value {} with ({}, {})",
              start,
              end,
              key_bytes,
              value_bytes);
            count++;

            // add the kv to the response
            auto* kv = range_response.add_kvs();
            auto key = std::string(key_bytes.begin(), key_bytes.end());
            kv->set_key(key);
            auto value = std::string(value_bytes.begin(), value_bytes.end());
            kv->set_value(value);
          },
          start_bytes,
          end_bytes);

        range_response.set_count(count);
      }

      return ccf::grpc::make_success(range_response);
    }

    static ccf::grpc::GrpcAdapterResponse<etcdserverpb::PutResponse> put(
      ccf::endpoints::EndpointContext& ctx, etcdserverpb::PutRequest&& payload)
    {
      etcdserverpb::PutResponse put_response;
      CCF_APP_DEBUG(
        "Put = [{}]{}:[{}]{}",
        payload.key().size(),
        payload.key(),
        payload.value().size(),
        payload.value());

      if (payload.lease() != 0)
      {
        return ccf::grpc::make_error<etcdserverpb::PutResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format("lease {} not yet supported", payload.lease()));
      }
      if (payload.prev_kv())
      {
        return ccf::grpc::make_error<etcdserverpb::PutResponse>(
          GRPC_STATUS_FAILED_PRECONDITION,
          fmt::format("prev_kv not yet supported"));
      }
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

      auto records_handle = ctx.tx.template rw<Map>(RECORDS);
      auto key = payload.key();
      auto value = payload.value();
      records_handle->put(
        ccf::ByteVector(key.begin(), key.end()),
        ccf::ByteVector(value.begin(), value.end()));
      ctx.rpc_ctx->set_response_status(HTTP_STATUS_OK);

      return ccf::grpc::make_success(put_response);
    }

    static ccf::grpc::GrpcAdapterResponse<etcdserverpb::DeleteRangeResponse>
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

      auto records_handle = ctx.tx.template rw<Map>(RECORDS);
      auto key = payload.key();

      if (payload.range_end().empty())
      {
        // just delete a single key

        // try to get the current value, if there isn't one then skip,
        // otherwise remove it and maybe plug the old value in to the
        // response.

        auto old_option =
          records_handle->get(ccf::ByteVector(key.begin(), key.end()));
        if (old_option.has_value())
        {
          records_handle->remove(ccf::ByteVector(key.begin(), key.end()));
          delete_range_response.set_deleted(1);

          if (payload.prev_kv())
          {
            auto* prev_kv = delete_range_response.add_prev_kvs();
            prev_kv->set_key(payload.key());
            auto old_value = old_option.value();
            auto old = std::string(old_value.begin(), old_value.end());
            prev_kv->set_value(old);
          }
        }
      }
      else
      {
        // operating over a range
        // find the keys to delete and remove them after collecting them

        auto deleted = 0;

        auto start = payload.key();
        auto start_bytes = ccf::ByteVector(start.begin(), start.end());
        auto end = payload.range_end();

        // If range_end is '\0', the range is all keys greater than or equal
        // to the key argument.
        if (end == std::string(1, '\0'))
        {
          CCF_APP_DEBUG("found empty end, making it work with range");
          // TODO(#23): should change the range to make sure we get all keys
          // greater than the start but this works for enough cases now
          end = std::string(16, '\255');
        }

        auto end_bytes = ccf::ByteVector(end.begin(), end.end());

        CCF_APP_DEBUG(
          "calling range for deletion with [{}]{} -> [{}]{}",
          start_bytes.size(),
          start_bytes,
          end_bytes.size(),
          end_bytes);
        records_handle->range(
          [&](auto& key_bytes, auto& value_bytes) {
            records_handle->remove(key_bytes);
            deleted++;

            if (payload.prev_kv())
            {
              auto* prev_kv = delete_range_response.add_prev_kvs();
              auto key = std::string(key_bytes.begin(), key_bytes.end());

              prev_kv->set_key(key);
              auto old = std::string(value_bytes.begin(), value_bytes.end());
              prev_kv->set_value(old);
            }
          },
          start_bytes,
          end_bytes);

        delete_range_response.set_deleted(deleted);
      }

      return ccf::grpc::make_success(delete_range_response);
    }

    template <typename In, typename Out>
    ccf::endpoints::Endpoint make_grpc_ro(
      const std::string& package,
      const std::string& service,
      const std::string& method,
      const ccf::GrpcReadOnlyEndpoint<In, Out>& f,
      const ccf::AuthnPolicies& ap)
    {
      auto path = fmt::format("/{}.{}/{}", package, service, method);
      return make_read_only_endpoint(
        path, HTTP_POST, ccf::grpc_read_only_adapter(f), ap);
    }

    template <typename In, typename Out>
    ccf::endpoints::Endpoint make_grpc(
      const std::string& package,
      const std::string& service,
      const std::string& method,
      const ccf::GrpcEndpoint<In, Out>& f,
      const ccf::AuthnPolicies& ap)
    {
      auto path = fmt::format("/{}.{}/{}", package, service, method);
      return make_endpoint(path, HTTP_POST, ccf::grpc_adapter(f), ap);
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
