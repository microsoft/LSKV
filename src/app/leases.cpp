#include "leases.h"

#include <string>
#include <chrono>

namespace app::leases
{
  Value::Value(int64_t ttl_, int64_t start_time_)
  {
    ttl = ttl_;
    start_time = start_time_;
  }

  Value::Value() = default;

  DECLARE_JSON_TYPE(Value);
  DECLARE_JSON_REQUIRED_FIELDS(Value, ttl, start_time);

  LeaseStore::LeaseStore(kv::Tx& tx) : rng(rand()), dist(1, INT64_MAX)
  {
    inner_map = tx.template rw<LeaseStore::MT>(LEASES);
  }

  int64_t LeaseStore::rand_id()
  {
    return dist(rng);
  }

  // create and store a new lease with default ttl.
  std::pair<LeaseStore::K, LeaseStore::V> LeaseStore::grant()
  {
    // randomly generate an id value and write it to a leases map
    // (ignore their lease id for now)
    int64_t id = rand_id();
    // decide whether to use the given ttl or one chosen by us
    int64_t ttl = DEFAULT_TTL_S;
    auto start_time = std::chrono::system_clock::now();
    auto start_time_s = std::chrono::duration_cast<std::chrono::seconds>(start_time.time_since_epoch()).count();
    auto value = Value(ttl, start_time_s);
    inner_map->put(id, value);

    return std::make_pair(id, value);
  }

  // remove a lease with the given id.
  // This just removes the id from the map, not removing any keys.
  void LeaseStore::revoke(K id) {
    inner_map->remove(id);
  }
}