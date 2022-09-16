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

#include <nlohmann/json.hpp>

#define FMT_HEADER_ONLY
#include <fmt/format.h>

namespace app
{
  using json = nlohmann::json;

  struct Value
  {
    // the actual value that the client wants written.
    std::string value;
    // the revision that this entry was created (since the last delete).
    uint64_t create_revision;
    // the latest modification of this entry (0 in the serialised field).
    uint64_t mod_revision;
    // the version of this key, reset on delete and incremented every update.
    uint64_t version;

    Value(std::string v)
    {
      value = v;
      create_revision = 0;
      mod_revision = 0;
      version = 1;
    }

    Value()
    {
      Value("");
    }
  };
  DECLARE_JSON_TYPE(Value);
  DECLARE_JSON_REQUIRED_FIELDS(Value, value, create_revision, version);

  static constexpr auto RECORDS = "public:records";

  /// @brief KVStore is a wrapper around a CCF map that handles serialisation as
  /// well as ensuring values have proper revisions when returned.
  class KVStore
  {
  public:
    using K = std::string;
    using V = Value;
    using KSerialiser = kv::serialisers::BlitSerialiser<K>;
    using VSerialiser = kv::serialisers::JsonSerialiser<V>;

    // Use untyped map so we can access the range API.
    using MT = kv::untyped::Map;

    /// @brief Constructs a KVStore
    /// @param ctx
    KVStore(ccf::endpoints::EndpointContext& ctx)
    {
      inner_map = ctx.tx.template rw<KVStore::MT>(RECORDS);
    }
    /// @brief Constructs a KVStore
    /// @param ctx
    KVStore(ccf::endpoints::ReadOnlyEndpointContext& ctx)
    {
      inner_map = ctx.tx.template ro<KVStore::MT>(RECORDS);
    }

    /// @brief get retrieves the value stored for the given key. It hydrates the
    /// value with up-to-date information as values may not store all
    /// information about revisions.
    /// @param key the key to get.
    /// @return The value, if present.
    std::optional<V> get(const K& key)
    {
      // get the value out and deserialise it
      auto res = inner_map->get(KSerialiser::to_serialised(key));
      if (!res.has_value())
      {
        return std::nullopt;
      }
      auto val = VSerialiser::from_serialised(res.value());

      hydrate_value(key, val);

      return val;
    }

    void range(
      const std::function<void(K&, V&)>& fn, const K& from, const K& to)
    {
      inner_map->range(
        [&](auto& key, auto& value) {
          auto k = KSerialiser::from_serialised(key);
          auto v = VSerialiser::from_serialised(value);
          hydrate_value(k, v);
          fn(k, v);
        },
        KSerialiser::to_serialised(from),
        KSerialiser::to_serialised(to));
    }

    /// @brief Associate a value with a key in the store, replacing existing
    /// entries for that key.
    ///
    /// When an entry doesn't exist already this simply writes the data in.
    ///
    /// When an entry does exist already this gets the old value, and uses the
    /// data to build the new version and, if not set, a create revision.
    /// @param key where to insert
    /// @param value data to insert
    /// @return the old value associated with the key, if present.
    std::optional<V> put(K key, V value)
    {
      const auto old = this->get(key);
      if (old.has_value())
      {
        const auto old_val = old.value();
        if (old_val.create_revision == 0)
        {
          // first put after creation of this key so set the revision
          auto version_opt = inner_map->get_version_of_previous_write(
            KSerialiser::to_serialised(key));
          if (version_opt.has_value())
          {
            // can set the creation revision
            value.create_revision = version_opt.value();
          }
        }
        else
        {
          // otherwise just copy it to the new value so that we don't lose it
          value.create_revision = old_val.create_revision;
        }

        value.version = old_val.version + 1;
      }

      inner_map->put(
        KSerialiser::to_serialised(key), VSerialiser::to_serialised(value));

      return old;
    }

    /// @brief remove data associated with the key from the store.
    /// @param key
    /// @return the old value, if present in the store.
    std::optional<V> remove(const K& key)
    {
      auto k = KSerialiser::to_serialised(key);
      auto old = inner_map->get(k);
      inner_map->remove(k);
      if (old.has_value())
      {
        return VSerialiser::from_serialised(old.value());
      }
      else
      {
        return std::nullopt;
      }
    }

  private:
    MT::Handle* inner_map;

    void hydrate_value(const K& key, V& value)
    {
      // the version of the write to this key is our revision
      auto version_opt = inner_map->get_version_of_previous_write(
        KSerialiser::to_serialised(key));
      // if there is no version (somehow) then just default it
      // this shouldn't be nullopt though.
      uint64_t revision = version_opt.value_or(0);

      // if this was the first insert then we need to set the creation revision.
      if (value.create_revision == 0)
      {
        value.create_revision = revision;
      }

      // and always set the mod_revision
      value.mod_revision = revision;
    }
  };

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

      auto records_map = KVStore(ctx);
      auto& key = payload.key();
      auto& range_end = payload.range_end();
      if (range_end.empty())
      {
        // empty range end so just query for a single key
        auto value_option = records_map.get(key);
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
        auto value = value_option.value();
        kv->set_value(value.value);
        kv->set_create_revision(value.create_revision);
        kv->set_mod_revision(value.mod_revision);
        kv->set_version(value.version);

        range_response.set_count(1);
      }
      else
      {
        // range end is non-empty so perform a range scan
        auto& start = payload.key();
        auto& end = payload.range_end();
        auto count = 0;

        records_map.range(
          [&](auto& key, auto& value) {
            count++;

            // add the kv to the response
            auto* kv = range_response.add_kvs();
            kv->set_key(key);
            kv->set_value(value.value);
            kv->set_create_revision(value.create_revision);
            kv->set_mod_revision(value.mod_revision);
            kv->set_version(value.version);
          },
          start,
          end);

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

      auto records_map = KVStore(ctx);
      records_map.put(payload.key(), Value(payload.value()));
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

      auto records_map = KVStore(ctx);
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
            prev_kv->set_value(old_value.value);
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

        CCF_APP_DEBUG(
          "calling range for deletion with [{}]{} -> [{}]{}",
          start.size(),
          start,
          end.size(),
          end);
        records_map.range(
          [&](auto& key, auto& old) {
            records_map.remove(key);
            deleted++;

            if (payload.prev_kv())
            {
              auto* prev_kv = delete_range_response.add_prev_kvs();

              prev_kv->set_key(key);
              prev_kv->set_value(old.value);
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
