// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#include "kvstore.h"

#include "ccf/app_interface.h"
#include "ccf/common_auth_policies.h"
#include "ccf/http_query.h"
#include "ccf/json_handler.h"
#include "kv/untyped_map.h" // TODO(#22): private header

#include <nlohmann/json.hpp>

namespace app::kvstore
{
  using json = nlohmann::json;

  Value::Value(const std::string& v, int64_t lease_id)
  {
    data = std::vector<uint8_t>(v.begin(), v.end());
    create_revision = 0;
    mod_revision = 0;
    version = 1;
    lease = lease_id;
  }

  Value::Value()
  {
    data = std::vector<uint8_t>();
    create_revision = 0;
    mod_revision = 0;
    version = 0;
    lease = 0;
  }

  std::string Value::get_data()
  {
    return std::string(data.begin(), data.end());
  }

  void Value::hydrate(uint64_t revision)
  {
    // if this was the first insert then we need to set the creation revision.
    if (create_revision == 0)
    {
      create_revision = revision;
    }

    // and always set the mod_revision
    mod_revision = revision;
  }

  /// @brief Check whether the given key is public
  /// @param key
  /// @return whether the key is public
  bool KVStore::is_public(const KVStore::K& key)
  {
    CCF_APP_DEBUG("Checking if key is public: {}", key);

    auto key_len = key.size();
    bool is_public = false;

    public_prefixes_map->foreach(
      [&is_public, key_len, key](const auto& prefix, const auto& _) {
        CCF_APP_DEBUG("Checking if key is public against: {}", prefix);
        auto prefix_len = prefix.size();
        if (key_len >= prefix_len)
        {
          KVStore::K key_prefix = {key.begin(), key.begin() + prefix_len};
          if (prefix == key_prefix)
          {
            is_public = true;
            return false;
          }
        }
        return true;
      });
    return is_public;
  }

  /// @brief Constructs a KVStore
  /// @param ctx
  KVStore::KVStore(kv::Tx& tx)
  {
    private_map = tx.template ro<KVStore::MT>(RECORDS);
    public_map = tx.template ro<KVStore::MT>(PUBLIC_RECORDS);
    public_prefixes_map = tx.template ro<KVStore::PP>(PUBLIC_PREFIXES);
  }
  /// @brief Constructs a KVStore
  /// @param ctx
  KVStore::KVStore(kv::ReadOnlyTx& tx)
  {
    private_map = tx.template ro<KVStore::MT>(RECORDS);
    public_map = tx.template ro<KVStore::MT>(PUBLIC_RECORDS);
    public_prefixes_map = tx.template ro<KVStore::PP>(PUBLIC_PREFIXES);
  }

  /// @brief get retrieves the value stored for the given key. It hydrates the
  /// value with up-to-date information as values may not store all
  /// information about revisions.
  /// @param key the key to get.
  /// @return The value, if present.
  std::optional<KVStore::V> KVStore::get(const KVStore::K& key)
  {
    // get the value out and deserialise it
    // TODO(#191): Currently we have to keep all data in private map and some in
    // public. A nicer solution would avoid duplicating the data by using
    // iterators over the CCF map, allowing us to do a range over both public
    // and private at the same time and keeping the items in order.
    auto res = private_map->get(KSerialiser::to_serialised(key));
    if (!res.has_value())
    {
      return std::nullopt;
    }
    auto val = VSerialiser::from_serialised(res.value());

    hydrate_value(key, val);

    return val;
  }

  void KVStore::foreach(
    const std::function<bool(const KVStore::K&, const KVStore::V&)>& fn)
  {
    // TODO(#191): Currently we have to keep all data in private map and some in
    // public. A nicer solution would avoid duplicating the data by using
    // iterators over the CCF map, allowing us to do a range over both public
    // and private at the same time and keeping the items in order.
    private_map->foreach([&](auto& key, auto& value) -> bool {
      auto k = KVStore::KSerialiser::from_serialised(key);
      auto v = KVStore::VSerialiser::from_serialised(value);
      hydrate_value(k, v);
      return fn(k, v);
    });
  }

  void KVStore::range(
    const std::function<void(KVStore::K&, KVStore::V&)>& fn,
    const KVStore::K& from,
    const std::optional<KVStore::K>& to_opt)
  {
    std::optional<kv::serialisers::SerialisedEntry> to = std::nullopt;
    if (to_opt.has_value())
    {
      to = KVStore::KSerialiser::to_serialised(to_opt.value());
    }
    // TODO(#191): Currently we have to keep all data in private map and some in
    // public. A nicer solution would avoid duplicating the data by using
    // iterators over the CCF map, allowing us to do a range over both public
    // and private at the same time and keeping the items in order.
    private_map->range(
      [&](auto& key, auto& value) {
        auto k = KVStore::KSerialiser::from_serialised(key);
        auto v = KVStore::VSerialiser::from_serialised(value);
        hydrate_value(k, v);
        fn(k, v);
      },
      KVStore::KSerialiser::to_serialised(from),
      to);
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
        auto version_opt = private_map->get_version_of_previous_write(
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

    auto key_ser = KVStore::KSerialiser::to_serialised(key);
    auto value_ser = KVStore::VSerialiser::to_serialised(value);

    private_map->put(key_ser, value_ser);

    // TODO(#191): Currently we have to keep all data in private map and some in
    // public. A nicer solution would avoid duplicating the data by using
    // iterators over the CCF map, allowing us to do a range over both public
    // and private at the same time and keeping the items in order.
    if (is_public(key))
    {
      public_map->put(key_ser, value_ser);
    }

    return old;
  }

  /// @brief remove data associated with the key from the store.
  /// @param key
  /// @return the old value, if present in the store.
  std::optional<KVStore::V> KVStore::remove(const KVStore::K& key)
  {
    auto k = KVStore::KSerialiser::to_serialised(key);
    auto old = private_map->get(k);
    private_map->remove(k);
    // TODO(#191): Currently we have to keep all data in private map and some in
    // public. A nicer solution would avoid duplicating the data by using
    // iterators over the CCF map, allowing us to do a range over both public
    // and private at the same time and keeping the items in order.
    if (is_public(key))
    {
      public_map->remove(k);
    }

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
    auto version_opt = private_map->get_version_of_previous_write(
      KSerialiser::to_serialised(key));
    // if there is no version (somehow) then just default it
    // this shouldn't be nullopt though.
    uint64_t revision = version_opt.value_or(0);

    value.hydrate(revision);
  }
}; // namespace app::kvstore
