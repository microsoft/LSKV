// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#include "leases.h"

#include <chrono> // NOLINT(build/c++11)
#include <string>

namespace app::leasestore
{
  Lease::Lease(int64_t ttl_, int64_t start_time_)
  {
    ttl = ttl_;
    start_time = start_time_;
  }

  static Lease EXPIRED_LEASE = Lease(0, 0);

  Lease::Lease() = default;

  DECLARE_JSON_TYPE(Lease);
  DECLARE_JSON_REQUIRED_FIELDS(Lease, ttl, start_time);

  int64_t Lease::ttl_remaining(int64_t now_s)
  {
    auto remaining = (start_time + ttl) - now_s;
    if (remaining <= 0)
    {
      // expired leases don't indicate how old they are
      return -1;
    }
    else
    {
      return remaining;
    }
  }

  bool Lease::has_expired(int64_t now_s)
  {
    return ttl_remaining(now_s) <= 0;
  }

  WriteOnlyLeaseStore::WriteOnlyLeaseStore(kv::Tx& tx) :
    rng(rand_dev()),
    dist(1, INT64_MAX)
  {
    inner_map = tx.template rw<WriteOnlyLeaseStore::MT>(LEASES);
  }

  ReadOnlyLeaseStore::ReadOnlyLeaseStore(kv::ReadOnlyTx& tx)
  {
    inner_map = tx.template ro<ReadOnlyLeaseStore::MT>(LEASES);
  }

  int64_t WriteOnlyLeaseStore::rand_id()
  {
    return dist(rng);
  }

  bool ReadOnlyLeaseStore::contains(K id, int64_t now_s)
  {
    return !get(id, now_s).has_expired(now_s);
  }

  ReadOnlyLeaseStore::V ReadOnlyLeaseStore::get(const K& id, int64_t now_s)
  {
    auto lease_opt = inner_map->get(id);
    if (!lease_opt.has_value())
    {
      CCF_APP_DEBUG("actually missing the lease");
      return EXPIRED_LEASE;
    }
    CCF_APP_DEBUG("found lease id");
    auto lease = lease_opt.value();
    if (lease.has_expired(now_s))
    {
      return EXPIRED_LEASE;
    }
    return lease;
  }

  // create and store a new lease with default ttl.
  std::pair<WriteOnlyLeaseStore::K, WriteOnlyLeaseStore::V>
  WriteOnlyLeaseStore::grant(int64_t ttl, int64_t now_s)
  {
    // randomly generate an id value and write it to a leases map
    // (ignore their lease id for now)
    int64_t id = rand_id();
    auto lease = Lease(ttl, now_s);
    inner_map->put(id, lease);

    return std::make_pair(id, lease);
  }

  // remove a lease with the given id.
  // This just removes the id from the map, not removing any keys.
  void WriteOnlyLeaseStore::revoke(K id)
  {
    inner_map->remove(id);
  }

  int64_t WriteOnlyLeaseStore::keep_alive(K id, int64_t now_s)
  {
    auto lease_opt = inner_map->get(id);
    if (lease_opt.has_value())
    {
      auto lease = lease_opt.value();
      lease.start_time = now_s;
      auto ttl = lease.ttl;
      inner_map->put(id, lease);
      return ttl;
    }
    return 0;
  }

  void ReadOnlyLeaseStore::foreach(
    const std::function<
      bool(const ReadOnlyLeaseStore::K&, const ReadOnlyLeaseStore::V&)>& fn)
  {
    inner_map->foreach(fn);
  }
} // namespace app::leasestore
