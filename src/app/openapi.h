#include "ccf/app_interface.h"

namespace app::openapi
{
  using bytes = std::vector<uint8_t>;

  struct ResponseHeader
  {
    uint64_t cluster_id;
    uint64_t member_id;
    int64_t revision;
    uint64_t raft_term;
    int64_t committed_revision;
    uint64_t committed_raft_term;
  };
  DECLARE_JSON_TYPE(ResponseHeader)
  DECLARE_JSON_REQUIRED_FIELDS(
    ResponseHeader,
    cluster_id,
    member_id,
    revision,
    raft_term,
    committed_revision,
    committed_raft_term)

  struct KeyValue
  {
    bytes key;
    int64_t create_revision;
    int64_t mod_revision;
    int64_t version;
    bytes value;
    int64_t lease;
  };
  DECLARE_JSON_TYPE_WITH_OPTIONAL_FIELDS(KeyValue)
  DECLARE_JSON_REQUIRED_FIELDS(
    KeyValue, key, value, create_revision, mod_revision, version)
  DECLARE_JSON_OPTIONAL_FIELDS(KeyValue, lease)

  struct Put
  {
    struct In
    {
      bytes key;
      bytes value;
      int64_t lease;
      bool prev_kv;
      bool ignore_value;
      bool ignore_lease;
    };
    struct Out
    {
      ResponseHeader header;
      KeyValue prev_kv;
    };
  };
  DECLARE_JSON_TYPE_WITH_OPTIONAL_FIELDS(Put::In)
  DECLARE_JSON_REQUIRED_FIELDS(Put::In, key, value)
  DECLARE_JSON_OPTIONAL_FIELDS(
    Put::In, lease, prev_kv, ignore_value, ignore_lease)
  DECLARE_JSON_TYPE(Put::Out)
  DECLARE_JSON_REQUIRED_FIELDS(Put::Out, header, prev_kv)

  struct Range
  {
    struct In
    {
      bytes key;
    };
    struct Out
    {};
  };
  DECLARE_JSON_TYPE(Range::In)
  DECLARE_JSON_REQUIRED_FIELDS(Range::In, key)
  DECLARE_JSON_TYPE(Range::Out)
  DECLARE_JSON_REQUIRED_FIELDS(Range::Out)

  struct DeleteRange
  {
    struct In
    {
      bytes key;
      bytes range_end;
      bool prev_kv;
    };
    struct Out
    {
      ResponseHeader header;
      int64_t deleted;
      std::vector<KeyValue> prev_kvs;
    };
  };
  DECLARE_JSON_TYPE_WITH_OPTIONAL_FIELDS(DeleteRange::In)
  DECLARE_JSON_REQUIRED_FIELDS(DeleteRange::In, key)
  DECLARE_JSON_OPTIONAL_FIELDS(DeleteRange::In, range_end, prev_kv)
  DECLARE_JSON_TYPE(DeleteRange::Out)
  DECLARE_JSON_REQUIRED_FIELDS(DeleteRange::Out, header, deleted, prev_kvs)

  struct Txn
  {
    struct In
    {};
    struct Out
    {};
  };
  DECLARE_JSON_TYPE(Txn::In)
  DECLARE_JSON_REQUIRED_FIELDS(Txn::In)
  DECLARE_JSON_TYPE(Txn::Out)
  DECLARE_JSON_REQUIRED_FIELDS(Txn::Out)

  struct Compaction
  {
    struct In
    {};
    struct Out
    {};
  };
  DECLARE_JSON_TYPE(Compaction::In)
  DECLARE_JSON_REQUIRED_FIELDS(Compaction::In)
  DECLARE_JSON_TYPE(Compaction::Out)
  DECLARE_JSON_REQUIRED_FIELDS(Compaction::Out)

  struct LeaseGrant
  {
    struct In
    {};
    struct Out
    {};
  };
  DECLARE_JSON_TYPE(LeaseGrant::In)
  DECLARE_JSON_REQUIRED_FIELDS(LeaseGrant::In)
  DECLARE_JSON_TYPE(LeaseGrant::Out)
  DECLARE_JSON_REQUIRED_FIELDS(LeaseGrant::Out)

  struct LeaseRevoke
  {
    struct In
    {};
    struct Out
    {};
  };
  DECLARE_JSON_TYPE(LeaseRevoke::In)
  DECLARE_JSON_REQUIRED_FIELDS(LeaseRevoke::In)
  DECLARE_JSON_TYPE(LeaseRevoke::Out)
  DECLARE_JSON_REQUIRED_FIELDS(LeaseRevoke::Out)

  struct LeaseKeepAlive
  {
    struct In
    {};
    struct Out
    {};
  };
  DECLARE_JSON_TYPE(LeaseKeepAlive::In)
  DECLARE_JSON_REQUIRED_FIELDS(LeaseKeepAlive::In)
  DECLARE_JSON_TYPE(LeaseKeepAlive::Out)
  DECLARE_JSON_REQUIRED_FIELDS(LeaseKeepAlive::Out)
}
