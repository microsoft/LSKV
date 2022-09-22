// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#pragma once

#include "ccf/indexing/strategy.h"
#include "kvstore.h"

namespace app::index
{

  class KVIndexer : public ccf::indexing::Strategy
  {
  private:
    using K = app::store::KVStore::K;

    // a map from revisions to the keys they changed.
    // Each revision may have changed multiple keys (txn) so we keep a vector of
    // them.
    std::map<int64_t, std::vector<K>> revisions_to_key;

    // a mapping from keys to the values those keys had at certain points.
    std::map<K, std::vector<app::store::KVStore::V>> keys_to_values;

  protected:
    ccf::TxID current_txid = {};

  public:
    KVIndexer(const std::string& map_name);

    void handle_committed_transaction(
      const ccf::TxID& tx_id, const kv::ReadOnlyStorePtr& store) override;

    std::optional<ccf::SeqNo> next_requested() override;
  };
}; // namespace app
