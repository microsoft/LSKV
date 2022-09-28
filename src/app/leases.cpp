// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

#define VERBOSE_LOGGING

#include "leases.h"

#include <chrono>
#include <string>

namespace app::leases
{
  Value::Value(int64_t ttl_, int64_t start_time_)
  {
    ttl = ttl_;
    start_time = start_time_;
  }

  static Value EXPIRED_LEASE = Value(0, 0);

  Value::Value() = default;

  DECLARE_JSON_TYPE(Value);
  DECLARE_JSON_REQUIRED_FIELDS(Value, ttl, start_time);

  int64_t now_seconds()
  {
    auto start_time = std::chrono::system_clock::now();
    auto start_time_s = std::chrono::duration_cast<std::chrono::seconds>(
                          start_time.time_since_epoch())
                          .count();
    return start_time_s;
  }

  int64_t Value::ttl_remaining()
  {
    auto remaining = (start_time + ttl) - now_seconds();
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

  bool Value::has_expired()
  {
    return ttl_remaining() <= 0;
  }

  WriteOnlyLeaseStore::WriteOnlyLeaseStore(kv::Tx& tx) :
    rng(rand()),
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

  bool ReadOnlyLeaseStore::contains(K id)
  {
    return !get(id).has_expired();
  }

  ReadOnlyLeaseStore::V ReadOnlyLeaseStore::get(const K& id)
  {
    auto value_opt = inner_map->get(id);
    if (!value_opt.has_value())
    {
      CCF_APP_DEBUG("actually missing the lease");
      return EXPIRED_LEASE;
    }
    CCF_APP_DEBUG("found lease id");
    auto value = value_opt.value();
    if (value.has_expired())
    {
      return EXPIRED_LEASE;
    }
    return value;
  }

  // create and store a new lease with default ttl.
  std::pair<WriteOnlyLeaseStore::K, WriteOnlyLeaseStore::V>
  WriteOnlyLeaseStore::grant(int64_t ttl)
  {
    // randomly generate an id value and write it to a leases map
    // (ignore their lease id for now)
    int64_t id = rand_id();
    auto value = Value(ttl, now_seconds());
    inner_map->put(id, value);

    return std::make_pair(id, value);
  }

  // remove a lease with the given id.
  // This just removes the id from the map, not removing any keys.
  void WriteOnlyLeaseStore::revoke(K id)
  {
    inner_map->remove(id);
  }

  int64_t WriteOnlyLeaseStore::keep_alive(K id)
  {
    auto value_opt = inner_map->get(id);
    if (value_opt.has_value())
    {
      auto value = value_opt.value();
      value.start_time = now_seconds();
      auto ttl = value.ttl;
      inner_map->put(id, value);
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
}
