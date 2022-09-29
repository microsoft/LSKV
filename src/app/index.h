// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#pragma once

#include "ccf/indexing/strategy.h"
#include "kvstore.h"

#include <map>
#include <string>
#include <vector>

namespace app::index
{
  class KVIndexer : public ccf::indexing::Strategy
  {
  public:
    using K = app::store::KVStore::K;
    using V = app::store::KVStore::V;

  protected:
    ccf::TxID current_txid = {};

  private:
    // a map from revisions to the keys they changed.
    // Each revision may have changed multiple keys (txn) so we keep a vector of
    // them.
    std::map<int64_t, std::vector<K>> revisions_to_key;

    // a mapping from keys to the values those keys had at certain points.
    std::map<K, std::vector<V>> keys_to_values;

  public:
    explicit KVIndexer(const std::string& map_name);

    void handle_committed_transaction(
      const ccf::TxID& tx_id, const kv::ReadOnlyStorePtr& store) override;

    std::optional<ccf::SeqNo> next_requested() override;

    std::optional<V> get(const int64_t at, const K& key);

    void range(
      const int64_t at,
      const std::function<void(const K&, V&)>& fn,
      const K& from,
      const K& to);
  };
}; // namespace app::index
