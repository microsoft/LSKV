// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#include "index.h"

#include "ccf/app_interface.h"
#include "kvstore.h"

#include <set>

namespace app::index
{
  // Index to handle two types of historical query: (1) range at specific
  // revision, (2) range since specific revision
  //
  // (1): cares about entire state at a set revision, including past things.
  // Perform the range on keys you're interested in then work out the state of
  // those keys at the specified revision
  //
  // (2): cares about changes to state since revision. Run a query over
  // revisions since the specified and have caused changes matching the range
  // and emit those events
  KVIndexer::KVIndexer(const std::string& map_name) : Strategy(map_name)
  {
    CCF_APP_DEBUG("created kvindexer for {}", map_name);
  }

  void KVIndexer::handle_committed_transaction(
    const ccf::TxID& tx_id, const kv::ReadOnlyStorePtr& store_ptr)
  {
    std::unique_lock lock(mutex);

    CCF_APP_DEBUG("index: handling committed transaction {}", tx_id.seqno);
    current_txid = tx_id;
    auto revision = tx_id.seqno;

    auto tx_diff = store_ptr->create_tx_diff();
    auto private_kv_map =
      tx_diff.diff<app::kvstore::KVStore::MT>(app::kvstore::RECORDS);

    private_kv_map->foreach(
      [this, &revision, &private_kv_map](const auto& k, const auto& v) {
        auto key = app::kvstore::KVStore::KSerialiser::from_serialised(k);
        if (v.has_value())
        {
          CCF_APP_DEBUG(
            "index: updating key {} from diff at revision {}", k, revision);

          auto value =
            app::kvstore::KVStore::VSerialiser::from_serialised(v.value());

          value.hydrate(revision);

          revisions_to_key[revision].push_back(key);
          keys_to_values[key].push_back(value);
        }
        else
        {
          CCF_APP_DEBUG(
            "index: deleting key {} from diff at revision {}", k, revision);

          revisions_to_key[revision].push_back(key);

          // make a deleted value
          app::kvstore::Value value;
          value.mod_revision = revision;

          keys_to_values[key].push_back(value);
        }

        return true;
      });
    CCF_APP_DEBUG("finished handling committed transaction {}", tx_id.seqno);
  }

  std::optional<ccf::SeqNo> KVIndexer::next_requested()
  {
    std::shared_lock lock(mutex);
    return current_txid.seqno + 1;
  };

  std::optional<KVIndexer::V> find_value(
    const int64_t at, const std::vector<KVIndexer::V> values)
  {
    std::optional<KVIndexer::V> val;
    for (const auto& value : values)
    {
      if (value.mod_revision > at)
      { // we've gone into the future, stop
        CCF_APP_DEBUG("Found a value in the future");
        break;
      }
      if (value.create_revision == 0)
      { // found a deleted value
        CCF_APP_DEBUG("Found a deleted value");
        val = std::nullopt;
      }
      else
      {
        CCF_APP_DEBUG("Found value with mod revision {}", value.mod_revision);
        val = value;
      }
    }
    return val;
  }

  std::optional<KVIndexer::V> KVIndexer::get(const int64_t at, const K& key)
  {
    std::shared_lock lock(mutex);

    CCF_APP_DEBUG("getting value from index with key {}", key);
    if (keys_to_values.contains(key))
    {
      auto& values = keys_to_values.at(key);
      CCF_APP_DEBUG("index get found values");

      auto value = find_value(at, values);
      return value;
    }
    return std::nullopt;
  }

  void KVIndexer::range(
    const int64_t at,
    const std::function<void(const KVIndexer::K&, KVIndexer::V&)>& fn,
    const KVIndexer::K& from,
    const std::optional<KVIndexer::K>& to)
  {
    std::shared_lock lock(mutex);
    // iterate over the keys in keys_to_values
    auto lb = keys_to_values.lower_bound(from);
    auto ub = keys_to_values.end();
    if (to.has_value())
    {
      ub = keys_to_values.lower_bound(to.value());
    }

    if (to.has_value())
    {
      CCF_APP_DEBUG("ranging over index from {} to {}", from, to.value());
    }
    else
    {
      CCF_APP_DEBUG("ranging over index from {} to the end", from);
    }

    for (auto it = lb; it != ub; ++it)
    {
      CCF_APP_DEBUG("index range found key: {}", it->first);
      // for each key, get the value it had at the revision
      auto& key = it->first;
      auto& values = it->second;

      auto val = find_value(at, values);
      if (val.has_value())
      {
        fn(key, val.value());
      }

      // if it was not present (deleted) skip it, otherwise return it to the
      // user
    }
  }

  void KVIndexer::compact(int64_t at)
  {
    std::shared_lock lock(mutex);

    // get the first revision still in the index
    auto start_revision = revisions_to_key.begin()->first;
    CCF_APP_DEBUG("Compacting index from {} to {}", start_revision, at);

    std::set<K> keys_compacted;

    // for each revision to be removed, remove it and collect the keys that it
    // touches
    auto it = revisions_to_key.begin();
    while (it != revisions_to_key.end())
    {
      if (it->first >= at)
      {
        // don't compact past the requested revision
        break;
      }

      auto keys = it->second;
      for (const auto& key : keys)
      {
        CCF_APP_DEBUG(
          "Adding compacted key from revision {}: {}", it->first, key);
        keys_compacted.insert(key);
      }
      it = revisions_to_key.erase(it);
    }

    CCF_APP_DEBUG("Collected {} keys to remove", keys_compacted.size());

    // go through the compacted keys and remove extra values
    for (const auto& key : keys_compacted)
    {
      CCF_APP_DEBUG(
        "Removing values for key {} for compaction revision {}", key, at);
      auto& values = keys_to_values.at(key);
      // TODO(#204): Should be able to remove multiple values from a key's
      // vector at once to avoid multiple copyings of the elements.
      auto it = values.begin();
      while (it != values.end())
      {
        if (it->mod_revision < at)
        {
          CCF_APP_DEBUG(
            "Removing compacted value for key {} at {}", key, it->mod_revision);
          it = values.erase(it);
        }
        else
        {
          // the values are stored in order of mod revisions so we can stop
          CCF_APP_DEBUG(
            "Finished removing values for key {} for compaction revision {}",
            key,
            at);
          break;
        }
      }
      if (values.empty())
      {
        // nothing left for this key so remove it from being tracked at all
        keys_to_values.erase(key);
      }
    }

    CCF_APP_DEBUG("Finished compacting at revision {}", at);
  }
}; // namespace app::index
