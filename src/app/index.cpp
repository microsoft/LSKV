// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#include "index.h"

#include "ccf/app_interface.h"
#include "kvstore.h"

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

    // TODO(#47): handle deleted kvs
    CCF_APP_DEBUG("index: handling committed transaction {}", tx_id.seqno);
    current_txid = tx_id;
    auto tx = store_ptr->create_read_only_tx();
    const std::vector<kvstore::KVStore::K> dummy_public_prefixes;
    auto kvs = kvstore::KVStore(tx, dummy_public_prefixes);
    auto revision = tx_id.seqno;

    kvs.foreach([this, &revision](const auto& k, const auto& v) {
      CCF_APP_DEBUG("index: updating key {}", k);
      revisions_to_key[revision].push_back(k);

      keys_to_values[k].push_back(v);

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
        break;
      }
      val = value;
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
    // TODO(#63): compact entries before `at`
  }
}; // namespace app::index
