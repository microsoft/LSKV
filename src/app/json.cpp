#include "json.h"

#include "etcd.pb.h"
#include "nlohmann/json.hpp"

namespace etcdserverpb
{
  using json = nlohmann::json;
  void from_json(const json& j, RangeRequest& req)
  {
    j.at("key").get_to(*req.mutable_key());
    if (j.contains("range_end"))
    {
      j.at("range_end").get_to(*req.mutable_range_end());
    }

    if (j.contains("limit"))
    {
      int64_t limit;
      j.at("limit").get_to(limit);
      req.set_limit(limit);
    }

    if (j.contains("revision"))
    {
      int64_t revision;
      j.at("revision").get_to(revision);
      req.set_revision(revision);
    }

    if (j.contains("serializable"))
    {
      bool serializable;
      j.at("serializable").get_to(serializable);
      req.set_serializable(serializable);
    }

    // sort_order
    // sort_target

    if (j.contains("keys_only"))
    {
      bool keys_only;
      j.at("keys_only").get_to(keys_only);
      req.set_keys_only(keys_only);
    }

    if (j.contains("count_only"))
    {
      bool count_only;
      j.at("count_only").get_to(count_only);
      req.set_count_only(count_only);
    }

    if (j.contains("min_mod_revision"))
    {
      int64_t min_mod_revision;
      j.at("min_mod_revision").get_to(min_mod_revision);
      req.set_min_mod_revision(min_mod_revision);
    }

    if (j.contains("max_mod_revision"))
    {
      int64_t max_mod_revision;
      j.at("max_mod_revision").get_to(max_mod_revision);
      req.set_max_mod_revision(max_mod_revision);
    }

    if (j.contains("min_create_revision"))
    {
      int64_t min_create_revision;
      j.at("min_create_revision").get_to(min_create_revision);
      req.set_min_create_revision(min_create_revision);
    }

    if (j.contains("max_create_revision"))
    {
      int64_t max_create_revision;
      j.at("max_create_revision").get_to(max_create_revision);
      req.set_max_create_revision(max_create_revision);
    }
  }

  void to_json(json& j, const KeyValue& kv)
  {
    j["key"] = kv.key();
    j["create_revision"] = kv.create_revision();
    j["mod_revision"] = kv.mod_revision();
    j["version"] = kv.version();
    j["value"] = kv.value();
    j["lease"] = kv.lease();
  }

  void to_json(json& j, const RangeResponse& res)
  {
    auto kvs = json::array();
    for (const auto& kv : res.kvs())
    {
      json jkv = json{};
      to_json(jkv, kv);
      kvs.push_back(jkv);
    }
    j["kvs"] = kvs;
    j["more"] = false;
    j["count"] = res.count();
  }

  void from_json(const json& j, PutRequest& req)
  {
    j.at("key").get_to(*req.mutable_key());
    j.at("value").get_to(*req.mutable_value());

    if (j.contains("lease"))
    {
      int64_t lease;
      j.at("lease").get_to(lease);
      req.set_lease(lease);
    }

    if (j.contains("prev_kv"))
    {
      bool prev_kv;
      j.at("prev_kv").get_to(prev_kv);
      req.set_prev_kv(prev_kv);
    }

    if (j.contains("ignore_value"))
    {
      bool ignore_value;
      j.at("ignore_value").get_to(ignore_value);
      req.set_ignore_value(ignore_value);
    }

    if (j.contains("ignore_lease"))
    {
      bool ignore_lease;
      j.at("ignore_lease").get_to(ignore_lease);
      req.set_ignore_lease(ignore_lease);
    }
  }

  void to_json(json& j, const PutResponse& res)
  {
    json jkv = json{};
    to_json(jkv, res.prev_kv());
    j["prev_kv"] = jkv;
  }

  void from_json(const json& j, DeleteRangeRequest& req)
  {
    j.at("key").get_to(*req.mutable_key());

    if (j.contains("range_end"))
    {
      j.at("range_end").get_to(*req.mutable_range_end());
    }

    if (j.contains("prev_kv"))
    {
      bool prev_kv;
      j.at("prev_kv").get_to(prev_kv);
      req.set_prev_kv(prev_kv);
    }
  }

  void to_json(json& j, const DeleteRangeResponse& res)
  {
    j["deleted"] = res.deleted();

    auto kvs = json::array();
    for (const auto& kv : res.prev_kvs())
    {
      json jkv = json{};
      to_json(jkv, kv);
      kvs.push_back(jkv);
    }
    j["prev_kvs"] = kvs;
  }
}