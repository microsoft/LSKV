// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#define VERBOSE_LOGGING

#include "index.h"

#include "ccf/app_interface.h"
#include "kvstore.h"

namespace app::index
{
  KVIndexer::KVIndexer(const std::string& map_name) : Strategy(map_name)
  {
    CCF_APP_DEBUG("created kvindexer for {}", map_name);
  }

  void KVIndexer::handle_committed_transaction(
    const ccf::TxID& tx_id, const kv::ReadOnlyStorePtr& store_ptr)
  {
    CCF_APP_DEBUG("handling committed transaction {}", tx_id.seqno);
    current_txid = tx_id;
    auto tx = store_ptr->create_read_only_tx();
    auto kvs = store::KVStore(tx);
    auto revision = tx_id.seqno;

    kvs.foreach([this, &revision](const auto& k, const auto& v) {
      CCF_APP_DEBUG("updating index with key {}", k);
      revisions_to_key[revision].push_back(k);

      keys_to_values[k].push_back(v);

      return true;
    });
  }

  std::optional<ccf::SeqNo> KVIndexer::next_requested()
  {
    return current_txid.seqno + 1;
  };

  // two types of historical query: (1) range at specific revision, (2) range
  // since specific revision
  //
  // (1): cares about entire state at a set revision, including past things.
  // Perform the range on keys you're interested in then work out the state of
  // those keys at the specified revision
  //
  // (2): cares about changes to state since revision. Run a query over
  // revisions since the specified and have caused changes matching the range
  // and emit those events
}; // namespace app
