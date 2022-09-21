// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#include "kvstore.h"

#include "ccf/app_interface.h"
#include "ccf/common_auth_policies.h"
#include "ccf/ds/hex.h"
#include "ccf/http_query.h"
#include "ccf/json_handler.h"
#include "kv/untyped_map.h" // TODO(#22): private header

#include <nlohmann/json.hpp>

namespace app::store
{
  using json = nlohmann::json;

  static constexpr auto RECORDS = "records";

  Value::Value(const std::string& v)
  {
    data = std::vector<uint8_t>(v.begin(), v.end());
    create_revision = 0;
    mod_revision = 0;
    version = 1;
    lease = 0;
  }

  Value::Value() = default;

  std::string Value::get_data()
  {
    return std::string(data.begin(), data.end());
  }

  DECLARE_JSON_TYPE(Value);
  DECLARE_JSON_REQUIRED_FIELDS(Value, data, create_revision, version);

  // using K = std::string;
  // using V = Value;
  // using KSerialiser = kv::serialisers::BlitSerialiser<K>;
  // using VSerialiser = kv::serialisers::JsonSerialiser<V>;

  // Use untyped map so we can access the range API.
  // using MT = kv::untyped::Map;

  /// @brief Constructs a KVStore
  /// @param ctx
  KVStore::KVStore(kv::Tx& tx)
  {
    inner_map = tx.template rw<KVStore::MT>(RECORDS);
  }
  /// @brief Constructs a KVStore
  /// @param ctx
  KVStore::KVStore(kv::ReadOnlyTx& tx)
  {
    inner_map = tx.template ro<KVStore::MT>(RECORDS);
  }

  /// @brief get retrieves the value stored for the given key. It hydrates the
  /// value with up-to-date information as values may not store all
  /// information about revisions.
  /// @param key the key to get.
  /// @return The value, if present.
  std::optional<KVStore::V> KVStore::get(const KVStore::K& key)
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

  void KVStore::range(
    const std::function<void(KVStore::K&, KVStore::V&)>& fn,
    const KVStore::K& from,
    const KVStore::K& to)
  {
    inner_map->range(
      [&](auto& key, auto& value) {
        auto k = KVStore::KSerialiser::from_serialised(key);
        auto v = KVStore::VSerialiser::from_serialised(value);
        hydrate_value(k, v);
        fn(k, v);
      },
      KVStore::KSerialiser::to_serialised(from),
      KVStore::KSerialiser::to_serialised(to));
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
  std::optional<KVStore::V> KVStore::put(KVStore::K key, KVStore::V value)
  {
    const auto old = this->get(key);
    if (old.has_value())
    {
      const auto old_val = old.value();
      if (old_val.create_revision == 0)
      {
        // first put after creation of this key so set the revision
        auto version_opt = inner_map->get_version_of_previous_write(
          KVStore::KSerialiser::to_serialised(key));
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
      KVStore::KSerialiser::to_serialised(key),
      KVStore::VSerialiser::to_serialised(value));

    return old;
  }

  /// @brief remove data associated with the key from the store.
  /// @param key
  /// @return the old value, if present in the store.
  std::optional<KVStore::V> KVStore::remove(const KVStore::K& key)
  {
    auto k = KVStore::KSerialiser::to_serialised(key);
    auto old = inner_map->get(k);
    inner_map->remove(k);
    if (old.has_value())
    {
      return KVStore::VSerialiser::from_serialised(old.value());
    }
    else
    {
      return std::nullopt;
    }
  }

  void KVStore::hydrate_value(const K& key, V& value)
  {
    // the version of the write to this key is our revision
    auto version_opt =
      inner_map->get_version_of_previous_write(KSerialiser::to_serialised(key));
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
}; // namespace app::store
