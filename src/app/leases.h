// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#pragma once

#include "ccf/app_interface.h"

#include <random>
#include <string>
#include <utility>

namespace app::leasestore
{
  static constexpr auto LEASES = "leases";

  struct Lease
  {
    int64_t ttl;
    int64_t start_time;

    Lease();
    Lease(int64_t ttl, int64_t start_time);

    bool has_expired();
    int64_t ttl_remaining();
  };

  class ReadOnlyLeaseStore
  {
  public:
    using K = int64_t;
    using V = Lease;
    using KSerialiser = kv::serialisers::BlitSerialiser<K>;
    using VSerialiser = kv::serialisers::JsonSerialiser<V>;
    using MT = kv::TypedMap<K, V, KSerialiser, VSerialiser>;

    explicit ReadOnlyLeaseStore(kv::ReadOnlyTx& tx);

    // check whether this lease exists in this store.
    bool contains(K id);

    V get(const K& id);

    void foreach(const std::function<bool(const K&, const V&)>& fn);

  private:
    MT::ReadOnlyHandle* inner_map;
  };

  class WriteOnlyLeaseStore
  {
  public:
    using K = int64_t;
    using V = Lease;
    using KSerialiser = kv::serialisers::BlitSerialiser<K>;
    using VSerialiser = kv::serialisers::JsonSerialiser<V>;
    using MT = kv::TypedMap<K, V, KSerialiser, VSerialiser>;

    explicit WriteOnlyLeaseStore(kv::Tx& tx);

    // create and store a new lease with default ttl.
    std::pair<K, V> grant(int64_t ttl);

    // remove a lease with the given id.
    // This just removes the id from the map, not removing any keys.
    void revoke(K id);

    // refresh a lease to keep it alive.
    int64_t keep_alive(K id);

  private:
    // random number generation for lease ids
    std::random_device rand_dev;
    std::mt19937 rng;
    std::uniform_int_distribution<int64_t> dist;

    MT::Handle* inner_map;

    // default time to live (seconds) for leases.
    // Clients can request a ttl but server can ignore it and use whatever.
    int64_t DEFAULT_TTL_S = 60;

    int64_t rand_id();
  };

  class LeaseStore : public ReadOnlyLeaseStore, public WriteOnlyLeaseStore
  {
  public:
    explicit LeaseStore(kv::Tx& tx) :
      ReadOnlyLeaseStore(tx),
      WriteOnlyLeaseStore(tx)
    {}
  };
} // namespace app::leasestore
