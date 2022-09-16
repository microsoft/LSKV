#include "ccf/app_interface.h"
#include "ccf/common_auth_policies.h"
#include "ccf/http_query.h"
#include "ccf/json_handler.h"
#include "kv/untyped_map.h" // TODO(#22): private header

namespace app::store
{

  struct Value
  {
    // the actual value that the client wants written.
    std::string value;
    // the revision that this entry was created (since the last delete).
    uint64_t create_revision;
    // the latest modification of this entry (0 in the serialised field).
    uint64_t mod_revision;
    // the version of this key, reset on delete and incremented every update.
    uint64_t version;

    Value(std::string v);
    Value();
  };

  class KVStore
  {
  public:
    using K = std::string;
    using V = Value;
    using KSerialiser = kv::serialisers::BlitSerialiser<K>;
    using VSerialiser = kv::serialisers::JsonSerialiser<V>;
    using MT = kv::untyped::Map;
    KVStore(kv::Tx& tx);
    KVStore(kv::ReadOnlyTx& tx);
    /// @brief get retrieves the value stored for the given key. It hydrates the
    /// value with up-to-date information as values may not store all
    /// information about revisions.
    /// @param key the key to get.
    /// @return The value, if present.
    std::optional<V> get(const K& key);

    void range(
      const std::function<void(K&, V&)>& fn, const K& from, const K& to);

    /// @brief Associate a value with a key in the store, replacing existing
    /// entries for that key.
    ///
    /// When an entry doesn't exist already this simply writes the data in.
    ///
    /// When an entry does exist already this gets the old value, and uses the
    /// data to build the new version and, if not set, a create revision.
    /// @param key where to insert
    /// @param value data to insert
    /// @return the old value associated with the key, if present.
    std::optional<V> put(K key, V value);

    /// @brief remove data associated with the key from the store.
    /// @param key
    /// @return the old value, if present in the store.
    std::optional<V> remove(const K& key);

  private:
    MT::Handle* inner_map;
    void hydrate_value(const K& key, V& value);
  };
};