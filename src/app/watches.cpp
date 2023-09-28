// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#include "watches.h"

#include "ccf/app_interface.h"
#include "kvstore.h"

#include <set>

namespace app::watches
{
  bool Watch::contains(std::string const& key)
  {
    if (key == start)
    {
      // watch for a single key
      return true;
    }
    else if (end.has_value() && start <= key && key < end.value())
    {
      // watch for a range
      return true;
    }
    else
    {
      // not matched this key
      return false;
    }
  }

  WatchIndexer::WatchIndexer(const std::string& map_name) : Strategy(map_name)
  {
    CCF_APP_DEBUG("created watchindexer for {}", map_name);
  }

  void WatchIndexer::set_cluster_id(int64_t new_cluster_id)
  {
    std::lock_guard<ccf::pal::Mutex> guard(mutex);
    cluster_id = new_cluster_id;
  }
  void WatchIndexer::set_member_id(int64_t new_member_id)
  {
    std::lock_guard<ccf::pal::Mutex> guard(mutex);
    member_id = new_member_id;
  }

  void WatchIndexer::handle_committed_transaction(
    const ccf::TxID& tx_id, const kv::ReadOnlyStorePtr& store_ptr)
  {
    std::lock_guard<ccf::pal::Mutex> guard(mutex);

    CCF_APP_DEBUG("watches: handling committed transaction {}", tx_id.seqno);
    current_txid = tx_id;
    auto revision = tx_id.seqno;

    auto tx_diff = store_ptr->create_tx_diff();
    auto private_kv_map =
      tx_diff.diff<app::kvstore::KVStore::MT>(app::kvstore::RECORDS);

    private_kv_map->foreach([this, &revision, &private_kv_map](
                              const auto& k, const auto& v) {
      auto key = app::kvstore::KVStore::KSerialiser::from_serialised(k);
      CCF_APP_DEBUG("watches: handling diff for key {}", key);

      // get the watches for this key
      auto start = watches.begin();
      auto end = watches.upper_bound(key);

      for (auto watch_it = start; watch_it != end; ++watch_it)
      {
        for (auto watch = watch_it->second.begin();
             watch != watch_it->second.end();
             ++watch)
        {
          CCF_APP_DEBUG(
            "watches: found watch with start {} and end {}",
            watch->start,
            watch->end);
          if (watch->contains(key))
          {
            if (v.has_value())
            {
              CCF_APP_DEBUG(
                "watches: handling key {} from diff at revision {}",
                key,
                revision);

              auto value =
                app::kvstore::KVStore::VSerialiser::from_serialised(v.value());

              value.hydrate(revision);

              etcdserverpb::WatchResponse response;
              response.set_watch_id(watch->id);
              CCF_APP_DEBUG(
                "Sending watch event to {} for PUT event for key {}",
                watch->id,
                key);
              auto* event = response.add_events();
              event->set_type(etcdserverpb::Event::PUT);
              auto* kv = event->mutable_kv();
              kv->set_key(key);
              kv->set_value(value.get_data());
              kv->set_create_revision(value.create_revision);
              kv->set_mod_revision(value.mod_revision);
              kv->set_version(value.version);
              kv->set_lease(value.lease);

              fill_header(*response.mutable_header());
              watch->stream->stream_msg(response);
            }
            else
            {
              CCF_APP_DEBUG(
                "watches: deleting key {} from diff at revision {}",
                key,
                revision);

              // make a deleted value
              app::kvstore::Value value;
              value.mod_revision = revision;

              etcdserverpb::WatchResponse response;
              response.set_watch_id(watch->id);
              CCF_APP_DEBUG(
                "Sending watch event to {} for DELETE event for key {}",
                watch->id,
                key);
              auto* event = response.add_events();
              event->set_type(etcdserverpb::Event::DELETE);
              auto* kv = event->mutable_kv();
              kv->set_key(key);
              kv->set_value(value.get_data());

              fill_header(*response.mutable_header());
              watch->stream->stream_msg(response);
            }
          }
        }
      }

      return true;
    });
    CCF_APP_DEBUG("finished handling committed transaction {}", tx_id.seqno);
  }

  std::optional<ccf::SeqNo> WatchIndexer::next_requested()
  {
    std::lock_guard<ccf::pal::Mutex> guard(mutex);
    return current_txid.seqno + 1;
  };

  int64_t WatchIndexer::add_watch(
    etcdserverpb::WatchCreateRequest const& create_payload,
    std::shared_ptr<ccf::RpcContext> rpc_ctx,
    ccf::grpc::StreamPtr<etcdserverpb::WatchResponse>&& out_stream)
  {
    std::lock_guard<ccf::pal::Mutex> guard(mutex);

    // get the new watch id
    auto watch_id = next_watch_id++;
    CCF_APP_DEBUG("Adding watch", watch_id);

    auto detached_stream = ccf::grpc::detach_stream(
      rpc_ctx, std::move(out_stream), [this, watch_id]() mutable {
        CCF_APP_DEBUG("Closing watch response stream {}", watch_id);
        remove_watch(watch_id);
      });

    Watch watch = {
      watch_id,
      std::move(detached_stream),
      create_payload.key(),
      create_payload.range_end()};
    // store the watch stream
    auto vec_it = watches.find(create_payload.key());
    if (vec_it != watches.end())
    {
      vec_it->second.push_back(std::move(watch));
    }
    else
    {
      std::vector<Watch> vec;
      vec.push_back(std::move(watch));
      watches.emplace(std::make_pair(create_payload.key(), std::move(vec)));
    }

    // notify the client of creation
    {
      etcdserverpb::WatchResponse response;
      response.set_watch_id(watch_id);
      response.set_created(true);

      CCF_APP_DEBUG(
        "Notifying client of created watch for key {} with id {}",
        create_payload.key(),
        watch_id);

      fill_header(*response.mutable_header());
      // we just pushed it in so we can get it from the back of the vector
      watches[create_payload.key()].back().stream->stream_msg(response);
    }

    return watch_id;
  }

  void WatchIndexer::remove_watch(int64_t watch_id)
  {
    std::lock_guard<ccf::pal::Mutex> guard(mutex);
    for (auto it = watches.begin(); it != watches.end(); ++it)
    {
      for (auto watch = it->second.begin(); watch != it->second.end(); ++watch)
      {
        if (watch->id == watch_id)
        {
          it->second.erase(watch);
          break;
        }
      }
    }
  }

  void WatchIndexer::fill_header(etcdserverpb::ResponseHeader& header)
  {
    header.set_cluster_id(cluster_id);
    header.set_member_id(member_id);
    const auto tx_id = current_txid;
    header.set_revision(tx_id.seqno);
    header.set_raft_term(tx_id.view);

    const auto committed = current_txid;
    header.set_committed_revision(committed.seqno);
    header.set_committed_raft_term(committed.view);
  }

}; // nam
