// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#pragma once

#include "ccf/indexing/strategy.h"
#include "endpoints/grpc/grpc.h" // TODO(#22): private header
#include "endpoints/grpc/stream.h" // TODO(#22): private header
#include "etcd.pb.h"
#include "kvstore.h"

#include <map>
#include <shared_mutex>
#include <string>
#include <vector>

namespace app::watches
{
  struct Watch
  {
    int64_t id;
    ccf::grpc::DetachedStreamPtr<etcdserverpb::WatchResponse> stream;

    // start of the watched range
    std::string start;
    // end of the watched range
    std::optional<std::string> end;

    bool contains(std::string const& key);
  };

  class WatchIndexer : public ccf::indexing::Strategy
  {
  public:
    using K = app::kvstore::KVStore::K;
    using V = app::kvstore::KVStore::V;

  protected:
    ccf::TxID current_txid = {};

  private:
    // Mapping of start of the range for a watch to a list of the watch structs.
    std::map<std::string, std::vector<Watch>> watches;
    int64_t next_watch_id = 0;

    int64_t cluster_id;
    int64_t member_id;

    ccf::pal::Mutex mutex;

    void fill_header(etcdserverpb::ResponseHeader& header);

  public:
    explicit WatchIndexer(const std::string& map_name);

    void handle_committed_transaction(
      const ccf::TxID& tx_id, const kv::ReadOnlyStorePtr& store) override;

    std::optional<ccf::SeqNo> next_requested() override;

    void set_cluster_id(int64_t new_cluster_id);
    void set_member_id(int64_t new_member_id);

    // Register a new watch for a key.
    int64_t add_watch(
      etcdserverpb::WatchCreateRequest const& create_payload,
      std::shared_ptr<ccf::RpcContext> rpc_ctx,
      ccf::grpc::StreamPtr<etcdserverpb::WatchResponse>&& out_stream);

    void remove_watch( int64_t watch_id);
  };
}; // namespace app::index
